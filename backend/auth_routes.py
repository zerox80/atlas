"""Authentication, session, CSRF token, and two-factor routes."""

import io
import os
from datetime import timedelta
from typing import Annotated

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from api_core import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    CSRF_COOKIE_NAME,
    RATE_LIMIT_LOGIN,
    get_current_user,
    limiter,
    request_is_https,
    set_csrf_cookie,
)
from auth import TOKEN_VERSION_CLAIM, create_access_token, verify_password
from database import get_session
from models import User
from schemas import OTPVerify, TwoFactorSetup
from security_utils import log_audit

router = APIRouter()


def _reject_cross_site_login(request: Request) -> None:
    """Prevent browsers from replacing a user's session through login CSRF."""
    origin = request.headers.get("origin")
    normalized_origin = origin.rstrip("/").lower() if origin else None
    request_origin = str(request.base_url).rstrip("/").lower()
    configured_origins = {
        value.strip().rstrip("/").lower()
        for value in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
        if value.strip()
    }
    allowed_origins = configured_origins | {request_origin}

    if normalized_origin and normalized_origin not in allowed_origins:
        raise HTTPException(
            status_code=403,
            detail="Cross-site login is not allowed",
        )
    if not origin and request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise HTTPException(
            status_code=403,
            detail="Cross-site login is not allowed",
        )


@router.post("/token")
@limiter.limit(RATE_LIMIT_LOGIN)
def login_for_access_token(
    response: Response,
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], 
    session: Session = Depends(get_session)
):
    _reject_cross_site_login(request)
    user = session.exec(select(User).where(User.username == form_data.username)).first()
    
    # Mitigation against Timing Attacks:
    # Always perform a password verification to simulate workload, even if user is not found.
    if user:
        is_valid = verify_password(form_data.password, user.hashed_password)
    else:
        # Verify against a dummy hash to consume roughly same time
        verify_password(form_data.password, "$2b$12$MA8m9iq9ZqTVSzMjoAVSQu9AGRa5IYuE3zn/C2.qvYpPJc1y4vIR.")
        is_valid = False

    if not is_valid or not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    assert user is not None # Ensure mypy knows user exists
        
    # Check 2FA if enabled
    if user.totp_secret:
        # Require OTP
        # otp_code = form_data.client_secret # Removed unused assignment
        # NOTE: OAuth2PasswordRequestForm has client_secret but it is optional.
        # Alternatively, we can parse it from body if we extend the form or use a separate param.
        # For strict compliance, let's assume the frontend sends it or we fail.
        
        # Checking if 'otp' is passed in the request body (FastAPI form parsing workaround)
        # Since OAuth2PasswordRequestForm is strict, we might need a custom dependency or use client_uuid/secret.
        # Let's check if the user provided the OTP in the 'client_secret' field for now, 
        # OR require a separate 2FA verify step (2-step login).
        
        # STRATEGY: 2-Step Login is safer but complex to refactor frontend entirely.
        # Return a temporary "PRE-AUTH" token or 403 with "2FA Required".
        # SIMPLIFIED SECURE APPROACH: Use 'client_secret' field of the form for OTP code.
        
        otp = form_data.client_secret
        if not otp:
             raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="2FA Required",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(otp, valid_window=1):
             raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid 2FA Code",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    # Add role to token claims
    access_token = create_access_token(
        data={
            "sub": user.auth_subject,
            "role": user.role,
            TOKEN_VERSION_CLAIM: user.token_version,
        },
        expires_delta=access_token_expires,
    )
    
    # Set HttpOnly Cookie
    # Secure flag only when request comes via HTTPS (check X-Forwarded-Proto from nginx)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=request_is_https(request),  # Only secure if actually using HTTPS
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    set_csrf_cookie(response, request)
    
    client_host = request.client.host if request.client else "unknown"
    log_audit(session, user.id, "LOGIN", "User logged in", client_host, request.headers.get("user-agent"))
    return {"token_type": "bearer"}


@router.post("/logout")
def logout(response: Response, request: Request):
    """Clear the access_token cookie to log out"""
    secure = request_is_https(request)
    response.delete_cookie(key="access_token", secure=secure, samesite="lax", path="/")
    response.delete_cookie(key=CSRF_COOKIE_NAME, secure=secure, samesite="lax", path="/")
    return {"message": "Logged out"}


@router.get("/csrf-token")
def refresh_csrf_token(request: Request, response: Response):
    """Refresh the CSRF cookie for existing authenticated browser sessions."""
    set_csrf_cookie(response, request)
    return {"csrf_token": "set"}


# --- 2FA Endpoints ---
@router.post("/2fa/setup")
@limiter.limit("5/minute")
def setup_2fa(
    request: Request,
    setup_data: TwoFactorSetup,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Start TOTP enrollment after a fresh password (and, if enabled, TOTP) check."""
    if not verify_password(setup_data.password, current_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid password")

    if current_user.totp_secret:
        if not setup_data.current_otp or not pyotp.TOTP(current_user.totp_secret).verify(
            setup_data.current_otp,
            valid_window=1,
        ):
            raise HTTPException(status_code=401, detail="Valid current 2FA code required")

    secret = pyotp.random_base32()
    current_user.pending_totp_secret = secret
    session.add(current_user)
    client_host = request.client.host if request.client else "unknown"
    log_audit(
        session,
        current_user.id,
        "TOTP_ENROLLMENT_STARTED",
        "Started two-factor enrollment",
        client_host,
        request.headers.get("user-agent"),
        commit=False,
    )
    session.commit()
    
    # Generate QR Code
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=current_user.username, issuer_name="Atlas")
    
    # Create QR image
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    
    return Response(content=buf.getvalue(), media_type="image/png")

@router.post("/2fa/verify")
@limiter.limit("5/minute")
def verify_2fa(
    request: Request,
    otp_data: OTPVerify,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    secret = current_user.pending_totp_secret
    if not secret:
        raise HTTPException(status_code=400, detail="No pending 2FA enrollment")
        
    totp = pyotp.TOTP(secret)
    if not totp.verify(otp_data.otp):
        raise HTTPException(status_code=400, detail="Invalid OTP")

    current_user.totp_secret = secret
    current_user.pending_totp_secret = None
    session.add(current_user)
    client_host = request.client.host if request.client else "unknown"
    log_audit(
        session,
        current_user.id,
        "TOTP_ENROLLMENT_COMPLETED",
        "Enabled two-factor authentication",
        client_host,
        request.headers.get("user-agent"),
        commit=False,
    )
    session.commit()

    return {"message": "Verified"}
