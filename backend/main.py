from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, Response, Request, Cookie
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select, delete
from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from typing import List, Annotated, Optional
import uuid
import pyotp
import qrcode
import io
import os
from datetime import datetime, timedelta, timezone
import pandas as pd
from fastapi.responses import StreamingResponse

import secrets

# Rate Limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from database import create_db_and_tables, get_session
from models import User, Contract, Tag, ContractTagLink, AuditLog, ContractPermission, ContractList, ContractListLink
from schemas import ContractRead, UserCreate, UserRead, UserUpdate, PermissionCreate, PermissionRead, ContractListRead, ContractListCreate, ContractListUpdate, AuditLogRead, OTPVerify, TagRead, TagCreate, TagUpdate, ContractAnalysisResult, ChatRequest, ChatResponse
from auth import verify_password, create_access_token, get_password_hash, ACCESS_TOKEN_EXPIRE_MINUTES
from security_utils import log_audit
from file_utils import validate_file, save_upload_file, resolve_file_path

# Configuration
PRODUCTION_MODE = os.getenv("PRODUCTION", "false").lower() == "true"
RATE_LIMIT_LOGIN = os.getenv("RATE_LIMIT_LOGIN", "5/minute")

# Initialize Rate Limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    # Allow localhost and local network access
    allow_origins=[
        "http://localhost",
        "http://localhost:80",
        "http://127.0.0.1",
        "http://127.0.0.1:80",
    ],
    # Also allow any origin matching local network IPs
    allow_origin_regex=r"^https?://(192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

@app.on_event("startup")
def on_startup():
    create_db_and_tables()
    # Create initial admin user if not exists
    with next(get_session()) as session:
        user = session.exec(select(User).where(User.username == "admin")).first()
        admin_pw = os.getenv("ADMIN_PASSWORD")
        if not admin_pw:
            # Only generate random if not set AND user doesn't exist
            if not user:
                admin_pw = secrets.token_urlsafe(16)
                print(f"\n[SECURITY ALERT] ADMIN_PASSWORD not set. Generated temporary password: {admin_pw}\n")
        
        if admin_pw:
            hashed_pw = get_password_hash(admin_pw)
            if not user:
                # Create new
                admin_user = User(username="admin", hashed_password=hashed_pw, role="admin")
                session.add(admin_user)
                session.commit()
            else:
                # Update existing (Self-Healing)
                user.hashed_password = hashed_pw
                session.add(user)
                session.commit()
            
        # Create some default tags
        if not session.exec(select(Tag)).first():
            tags = [
                Tag(name="Software", color="#3b82f6"),
                Tag(name="Hardware", color="#ef4444"),
                Tag(name="Legal", color="#10b981"),
                Tag(name="HR", color="#f59e0b")
            ]
            for t in tags: 
                session.add(t)
            session.commit()

async def get_current_user(
    token: Annotated[Optional[str], Depends(oauth2_scheme)] = None, 
    access_token: Annotated[Optional[str], Cookie()] = None,
    session: Session = Depends(get_session)
):
    # Prioritize Cookie, fall back to Header (for API testing tools if needed, but we can enforce Cookie)
    final_token = access_token if access_token else token
    
    if not final_token:
         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    from jose import JWTError, jwt
    from auth import SECRET_KEY, ALGORITHM
    from schemas import TokenData
    
    try:
        payload = jwt.decode(final_token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
        token_data = TokenData(username=username)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
        
    user = session.exec(select(User).where(User.username == token_data.username)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user

@app.post("/token")
@limiter.limit(RATE_LIMIT_LOGIN)
async def login_for_access_token(
    response: Response,
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], 
    session: Session = Depends(get_session)
):
    user = session.exec(select(User).where(User.username == form_data.username)).first()
    
    # Mitigation against Timing Attacks:
    # Always perform a password verification to simulate workload, even if user is not found.
    if user:
        is_valid = verify_password(form_data.password, user.hashed_password)
    else:
        # Verify against a dummy hash to consume roughly same time
        verify_password(form_data.password, "$2b$12$MA8m9iq9ZqTVSzMjoAVSQu9AGRa5IYuE3zn/C2.qvYpPJc1y4vIR.")
        is_valid = False

    if not is_valid:
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
        # Approach: User validation passed. If 2FA enabled, return a temporary "PRE-AUTH" token or 403 with "2FA Required".
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
        data={"sub": user.username, "role": user.role}, expires_delta=access_token_expires
    )
    
    # Set HttpOnly Cookie
    # Secure flag only when request comes via HTTPS (check X-Forwarded-Proto from nginx)
    is_https = request.headers.get("x-forwarded-proto", "http") == "https"
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_https,  # Only secure if actually using HTTPS
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    
    client_host = request.client.host if request.client else "unknown"
    log_audit(session, user.id, "LOGIN", "User logged in", client_host, request.headers.get("user-agent"))
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/logout")
def logout(response: Response):
    """Clear the access_token cookie to log out"""
    response.delete_cookie(key="access_token")
    return {"message": "Logged out"}


# --- 2FA Endpoints ---
@app.post("/2fa/setup")
def setup_2fa(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    secret = pyotp.random_base32()
    current_user.totp_secret = secret
    session.add(current_user)
    session.commit()
    
    # Generate QR Code
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=current_user.username, issuer_name="ZE-Dashboard")
    
    # Create QR image
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    
    return Response(content=buf.getvalue(), media_type="image/png")

@app.post("/2fa/verify")
def verify_2fa(otp_data: OTPVerify, current_user: User = Depends(get_current_user)):
    if not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="2FA not setup")
        
    totp = pyotp.TOTP(current_user.totp_secret)
    if not totp.verify(otp_data.otp):
        raise HTTPException(status_code=400, detail="Invalid OTP")
        
    return {"message": "Verified"}

# --- Contract Endpoints ---

@app.get("/contracts", response_model=List[ContractRead])
def read_contracts(
    q: Optional[str] = None,                    # Full-text search
    tags: Optional[str] = None,                 # Comma-separated tag names
    list_id: Optional[int] = None,              # Filter by list
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    start_date_from: Optional[datetime] = None,
    start_date_to: Optional[datetime] = None,
    status: Optional[str] = None,               # "active" or "expired"
    sort_by: Optional[str] = "uploaded_at",     # title, value, start_date, end_date
    sort_order: Optional[str] = "desc",         # asc or desc
    current_user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    """
    Get contracts with optional search and filters.
    By default, ALL users see ALL contracts.
    Permissions are OPTIONAL restrictions, not required grants.
    """
    statement = select(Contract)
    
    # Full-text search on title and description
    if q:
        search_term = f"%{q}%"
        statement = statement.where(
            or_(
                Contract.title.ilike(search_term),
                Contract.description.ilike(search_term)
            )
        )
    
    # Filter by tags (comma-separated)
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_list:
            statement = statement.join(ContractTagLink).join(Tag).where(Tag.name.in_(tag_list))
    
    # Filter by list
    if list_id is not None:
        statement = statement.join(ContractListLink).where(ContractListLink.list_id == list_id)
    
    # Value range
    if min_value is not None:
        statement = statement.where(Contract.value >= min_value)
    if max_value is not None:
        statement = statement.where(Contract.value <= max_value)
    
    # Date range (start_date filter)
    if start_date_from:
        statement = statement.where(Contract.start_date != None, Contract.start_date >= start_date_from)
    if start_date_to:
        statement = statement.where(Contract.start_date != None, Contract.start_date <= start_date_to)
    
    # Status filter
    now = datetime.now(timezone.utc)
    if status == "active":
        statement = statement.where(or_(Contract.end_date == None, Contract.end_date >= now))
    elif status == "expired":
        statement = statement.where(Contract.end_date != None, Contract.end_date < now)
    
    # Sorting
    sort_columns = {
        "title": Contract.title,
        "value": Contract.value,
        "start_date": Contract.start_date,
        "end_date": Contract.end_date,
        "uploaded_at": Contract.uploaded_at
    }
    sort_column = sort_columns.get(sort_by, Contract.uploaded_at)
    
    if sort_order == "asc":
        statement = statement.order_by(sort_column.asc())
    else:
        statement = statement.order_by(sort_column.desc())
    
    # Ensure unique results when joining
    statement = statement.distinct()
    
    # Eager load relationships to prevent N+1 queries and DetachedInstanceError
    statement = statement.options(selectinload(Contract.tags), selectinload(Contract.lists))
    contracts = session.exec(statement).all()
    return contracts

@app.get("/contracts/export")
def export_contracts(
    q: Optional[str] = None,
    tags: Optional[str] = None,
    list_id: Optional[int] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    start_date_from: Optional[datetime] = None,
    start_date_to: Optional[datetime] = None,
    status: Optional[str] = None,
    format: str = "csv",
    current_user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    """
    Export filtered contracts as CSV or Excel.
    """
    statement = select(Contract)
    
    # --- Filter Logic (Duplicated from read_contracts for safety) ---
    if q:
        search_term = f"%{q}%"
        statement = statement.where(
            or_(
                Contract.title.ilike(search_term),
                Contract.description.ilike(search_term)
            )
        )
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_list:
            statement = statement.join(ContractTagLink).join(Tag).where(Tag.name.in_(tag_list))
    if list_id is not None:
        statement = statement.join(ContractListLink).where(ContractListLink.list_id == list_id)
    if min_value is not None:
        statement = statement.where(Contract.value >= min_value)
    if max_value is not None:
        statement = statement.where(Contract.value <= max_value)
    if start_date_from:
        statement = statement.where(Contract.start_date != None, Contract.start_date >= start_date_from)
    if start_date_to:
        statement = statement.where(Contract.start_date != None, Contract.start_date <= start_date_to)
    
    now = datetime.now(timezone.utc)
    if status == "active":
        statement = statement.where(or_(Contract.end_date == None, Contract.end_date >= now))
    elif status == "expired":
        statement = statement.where(Contract.end_date != None, Contract.end_date < now)
        
    statement = statement.distinct()
    statement = statement.options(selectinload(Contract.tags), selectinload(Contract.lists))
    contracts = session.exec(statement).all()
    
    # --- Data Processing ---
    data = []
    for c in contracts:
        data.append({
            "ID": c.id,
            "Titel": c.title,
            "Beschreibung": c.description,
            "Wert (€)": c.value,
            "Jährlicher Wert (€)": c.annual_value,
            "Startdatum": c.start_date.strftime("%Y-%m-%d") if c.start_date else "",
            "Enddatum": c.end_date.strftime("%Y-%m-%d") if c.end_date else "",
            "Kündigungsfrist (Tage)": c.notice_period if c.notice_period is not None else "",
            "Geschützt": "Ja" if c.is_protected else "Nein",
            "Tags": ", ".join([t.name for t in c.tags]),
            "Listen": ", ".join([l.name for l in c.lists]),
            "Erstellt am": c.uploaded_at.strftime("%Y-%m-%d %H:%M") if c.uploaded_at else ""
        })
        
    df = pd.DataFrame(data)
    
    if format == "excel":
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Verträge')
        output.seek(0)
        
        headers = {
            'Content-Disposition': 'attachment; filename="vertrage_export.xlsx"'
        }
        return StreamingResponse(output, headers=headers, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
    else: # Default to CSV
        output = io.StringIO()
        df.to_csv(output, index=False, sep=';', encoding='utf-8-sig') # German Excel compatible CSV
        output_bytes = io.BytesIO(output.getvalue().encode('utf-8-sig'))
        
        headers = {
            'Content-Disposition': 'attachment; filename="vertrage_export.csv"'
        }
        return StreamingResponse(output_bytes, headers=headers, media_type='text/csv')

def parse_date_form(val: Optional[str]) -> Optional[datetime]:
    if not val: return None
    try: return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except ValueError: raise HTTPException(status_code=422, detail="Invalid date format")

def parse_float_form(val: Optional[str]) -> Optional[float]:
    if not val: return None
    try: return float(val)
    except ValueError: raise HTTPException(status_code=422, detail="Invalid float format")

def parse_int_form(val: Optional[str]) -> Optional[int]:
    if not val: return None
    try: return int(val)
    except ValueError: raise HTTPException(status_code=422, detail="Invalid int format")

@app.post("/contracts", response_model=ContractRead)
async def create_contract(
    request: Request,
    title: Annotated[str, Form()],
    file: UploadFile = File(...),
    start_date: Annotated[Optional[str], Form()] = None,
    end_date: Annotated[Optional[str], Form()] = None,
    value: Annotated[Optional[str], Form()] = None,
    annual_value: Annotated[Optional[str], Form()] = None,
    notice_period: Annotated[Optional[str], Form()] = "30",
    description: Annotated[Optional[str], Form()] = None,
    tags: Annotated[Optional[str], Form()] = "",
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    # 1. Validate File
    try:
        await validate_file(file)
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail="Invalid file")

    # 2. Save File
    try:
        file_path = await save_upload_file(file)
    except HTTPException as e:
        raise e
        
    contract = Contract(
        title=title,
        description=description if description else None,
        start_date=parse_date_form(start_date),
        end_date=parse_date_form(end_date),
        file_path=file_path,
        value=parse_float_form(value),
        annual_value=parse_float_form(annual_value),
        notice_period=parse_int_form(notice_period)
    )
    
    # Handle Tags
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_list:
            # Optimization: Fetch existing tags in one query
            existing_tags = session.exec(select(Tag).where(Tag.name.in_(tag_list))).all()
            existing_map = {t.name: t for t in existing_tags}

            for t_name in tag_list:
                # Find in pre-fetched map or create
                tag = existing_map.get(t_name)
                
                if not tag:
                    try:
                        tag = Tag(name=t_name)
                        session.add(tag)
                        session.commit()
                        session.refresh(tag)
                        existing_map[t_name] = tag
                    except IntegrityError:
                        session.rollback()
                        # Race condition caught: tag was created by another request
                        tag = session.exec(select(Tag).where(Tag.name == t_name)).first()
                        if tag: existing_map[t_name] = tag
            
                if tag:
                     contract.tags.append(tag)
            
    try:
        session.add(contract)
        session.commit()
        session.refresh(contract)
    except Exception as e:
        # Cleanup file if DB insert fails
        if os.path.exists(file_path):
            os.remove(file_path)
        raise e
    
    client_host = request.client.host if request.client else "unknown"
    log_audit(session, current_user.id, "UPLOAD", f"[CID:{contract.id}] Uploaded contract {contract.title}", client_host, request.headers.get("user-agent"))
    return contract

# Removed unused StreamingResponse import
@app.get("/contracts/{contract_id}/download")
def download_contract(contract_id: int, request: Request, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    contract = session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    # Check permission
    if not check_contract_permission(current_user, contract_id, "read", session):
        raise HTTPException(status_code=403, detail="You don't have permission to access this contract")
        
    try:
        resolved_path = resolve_file_path(contract.file_path)
    except FileNotFoundError:
        print(f"[ERROR] File not found on disk: {contract.file_path}")
        raise HTTPException(status_code=404, detail="File not found on server")

    # Standard download
    client_host = request.client.host if request.client else "unknown"
    log_audit(session, current_user.id, "DOWNLOAD", f"[CID:{contract.id}] Downloaded {contract.title}", client_host, request.headers.get("user-agent"))
    
    # Determine basic mime types to avoid browser confusion
    # Determine basic mime types to avoid browser confusion
    import mimetypes
    media_type, _ = mimetypes.guess_type(resolved_path)
    
    # Check explicitly for pdf to be sure
    _, ext = os.path.splitext(resolved_path)
    if ext.lower() == ".pdf":
        media_type = "application/pdf"
        
    if not media_type:
        media_type = "application/octet-stream"
        
    # Ensure extension is in filename
    filename = f"{contract.title}{ext}"
    
    from fastapi.responses import FileResponse
    return FileResponse(resolved_path, media_type=media_type, filename=filename)

@app.put("/contracts/{contract_id}", response_model=ContractRead)
async def update_contract(
    contract_id: int, 
    request: Request,
    title: Annotated[Optional[str], Form()] = None,
    description: Annotated[Optional[str], Form()] = None,
    start_date: Annotated[Optional[str], Form()] = None,
    end_date: Annotated[Optional[str], Form()] = None,
    value: Annotated[Optional[str], Form()] = None,
    annual_value: Annotated[Optional[str], Form()] = None,
    notice_period: Annotated[Optional[str], Form()] = None,
    tags: Annotated[Optional[str], Form()] = None,
    file: UploadFile = File(None),
    current_user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    contract = session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    # Check permission (need at least "write" level)
    if not check_contract_permission(current_user, contract_id, "write", session):
        raise HTTPException(status_code=403, detail="You don't have permission to edit this contract")
        
    changes = []
    
    # helper to check and update
    def check_and_update_str(field_name, new_val):
        if new_val is not None:
            if new_val == "" and field_name != "title":
                new_val = None
            old_val = getattr(contract, field_name)
            if old_val != new_val:
                changes.append(f"{field_name}: '{old_val}' -> '{new_val}'")
                setattr(contract, field_name, new_val)

    def check_and_update_parsed(field_name, new_val_str, parser_func):
        if new_val_str is not None:
            parsed_val = parser_func(new_val_str)
            old_val = getattr(contract, field_name)
            if old_val != parsed_val:
                changes.append(f"{field_name}: '{old_val}' -> '{parsed_val}'")
                setattr(contract, field_name, parsed_val)
    
    check_and_update_str("title", title)
    check_and_update_str("description", description)
    check_and_update_parsed("start_date", start_date, parse_date_form)
    check_and_update_parsed("end_date", end_date, parse_date_form)
    check_and_update_parsed("value", value, parse_float_form)
    check_and_update_parsed("annual_value", annual_value, parse_float_form)
    check_and_update_parsed("notice_period", notice_period, parse_int_form)

    # Handle File Update
    if file:
        # Validate and Save
        try:
            await validate_file(file)
            new_file_path = await save_upload_file(file)
        except HTTPException as e:
            raise e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
            
        # Mark old file for deletion AFTER commit
        old_file_path = contract.file_path
        
        contract.file_path = new_file_path
        changes.append("file: updated")
    else:
        old_file_path = None
    
    # Handle Tags Update if provided
    if tags is not None:
        # Simple Logic: Clear and Re-add. 
        old_tags = [t.name for t in contract.tags]
        new_tags = [t.strip() for t in tags.split(",") if t.strip()]
        
        if set(old_tags) != set(new_tags):
            changes.append(f"tags: {old_tags} -> {new_tags}")
            contract.tags = []
            for t_name in new_tags:
                tag = session.exec(select(Tag).where(Tag.name == t_name)).first()
                if not tag:
                    try:
                        tag = Tag(name=t_name)
                        session.add(tag)
                        session.commit()
                        session.refresh(tag)
                    except IntegrityError:
                        session.rollback()
                        tag = session.exec(select(Tag).where(Tag.name == t_name)).first()
                
                if tag:
                    contract.tags.append(tag)
    
    if changes:
        session.add(contract)
        session.commit()
        session.refresh(contract)

        # Now it is safe to remove the old file if it was updated
        if old_file_path and os.path.exists(old_file_path) and old_file_path != contract.file_path:
             try:
                os.remove(old_file_path)
             except Exception as e:
                print(f"Error removing old file: {e}")
        
        diff_summary = "; ".join(changes)
        log_audit(
            session, 
            current_user.id, 
            "UPDATE_CONTRACT", 
            f"[CID:{contract_id}] Updated Contract. Changes: {diff_summary}", 
            request.client.host if request.client else "unknown", 
            request.headers.get("user-agent")
        )
    
    return contract

@app.delete("/contracts/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contract(
    contract_id: int, 
    current_user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    contract = session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    # Check permission (need "full" level to delete)
    if not check_contract_permission(current_user, contract_id, "full", session):
        raise HTTPException(status_code=403, detail="You don't have permission to delete this contract")
    
    if contract.is_protected:
        raise HTTPException(
            status_code=403, 
            detail="This contract is protected. You must unprotect it from the Protected Contracts page before deleting."
        )
    
    # Save file path before deleting record
    file_path_to_delete = contract.file_path

    session.delete(contract)
    session.commit()

    # Delete file if exists (After commit checks pass)
    if file_path_to_delete and os.path.exists(file_path_to_delete):
        try:
            os.remove(file_path_to_delete)
        except Exception as e:
            print(f"Error deleting file: {e}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.put("/contracts/{contract_id}/toggle-protection", response_model=ContractRead)
def toggle_contract_protection(
    contract_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Toggle the protected status of a contract (Admin only or Full Permission?) -> Let's say Full Perm."""
    contract = session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    # Check permission (need "full" level to change protection)
    # Alternatively, maybe only Admin? User asked: "auch vor Admins" -> implies Admins can remove it but need extra step.
    # So "full" permission or Admin is fine, but the UI flow prevents accidental delete.
    if not check_contract_permission(current_user, contract_id, "full", session):
        raise HTTPException(status_code=403, detail="You don't have permission to modify protection status")
        
    contract.is_protected = not contract.is_protected
    session.add(contract)
    session.commit()
    session.refresh(contract)
    
    action = "PROTECTED" if contract.is_protected else "UNPROTECTED"
    log_audit(
        session, 
        current_user.id, 
        f"CONTRACT_{action}", 
        f"[CID:{contract_id}] Contract {action}", 
        "unknown",
        "unknown"
    )
    
    return contract


# Helper dependency for admin-only endpoints
def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


@app.get("/tags", response_model=List[TagRead])
def get_tags(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Get all tags (requires authentication)"""
    return session.exec(select(Tag)).all()


@app.post("/tags", response_model=TagRead, status_code=201)
def create_tag(
    tag_data: TagCreate,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Create a new tag (Admin only)"""
    # Check if tag name already exists
    existing = session.exec(select(Tag).where(Tag.name == tag_data.name)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tag mit diesem Namen existiert bereits")
    
    new_tag = Tag(name=tag_data.name, color=tag_data.color)
    session.add(new_tag)
    session.commit()
    session.refresh(new_tag)
    
    log_audit(session, admin.id, "CREATE_TAG", f"Created tag '{new_tag.name}'", request.client.host if request.client else "unknown", request.headers.get("user-agent"))
    return new_tag


@app.put("/tags/{tag_id}", response_model=TagRead)
def update_tag(
    tag_id: int,
    tag_data: TagUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Update an existing tag (Admin only)"""
    tag = session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag nicht gefunden")
    
    changes = []
    
    if tag_data.name is not None and tag_data.name != tag.name:
        # Check if new name already exists
        existing = session.exec(select(Tag).where(Tag.name == tag_data.name)).first()
        if existing:
            raise HTTPException(status_code=400, detail="Tag mit diesem Namen existiert bereits")
        changes.append(f"name: '{tag.name}' -> '{tag_data.name}'")
        tag.name = tag_data.name
    
    if tag_data.color is not None and tag_data.color != tag.color:
        changes.append(f"color: '{tag.color}' -> '{tag_data.color}'")
        tag.color = tag_data.color
    
    if changes:
        session.add(tag)
        session.commit()
        session.refresh(tag)
        log_audit(session, admin.id, "UPDATE_TAG", f"Updated tag '{tag.name}': {'; '.join(changes)}", request.client.host if request.client else "unknown", request.headers.get("user-agent"))
    
    return tag


@app.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(
    tag_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Delete a tag (Admin only). Removes tag from all contracts."""
    tag = session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag nicht gefunden")
    
    tag_name = tag.name
    
    # Remove all contract-tag links first
    session.exec(delete(ContractTagLink).where(ContractTagLink.tag_id == tag_id))
    
    session.delete(tag)
    session.commit()
    
    log_audit(session, admin.id, "DELETE_TAG", f"Deleted tag '{tag_name}'", request.client.host if request.client else "unknown", request.headers.get("user-agent"))
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.get("/audit-logs", response_model=List[AuditLogRead])
def get_audit_logs(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    results = session.exec(select(AuditLog, User).join(User, isouter=True).order_by(AuditLog.timestamp.desc()).limit(100)).all()
    logs = []
    for log, user in results:
        l_dict = log.model_dump()
        l_dict["username"] = user.username if user else "Unknown"
        logs.append(l_dict)
    return logs

@app.get("/contracts/{contract_id}/audit", response_model=List[AuditLogRead])
def get_contract_audit_logs(
    contract_id: int, 
    current_user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    pattern = f"%[CID:{contract_id}]%"
    results = session.exec(select(AuditLog, User).join(User, isouter=True).where(AuditLog.details.like(pattern)).order_by(AuditLog.timestamp.desc())).all()
    
    logs = []
    for log, user in results:
        l_dict = log.model_dump()
        l_dict["username"] = user.username if user else "Unknown"
        logs.append(l_dict)
    return logs


# ========================================
#           ADMIN PANEL ENDPOINTS
# ========================================


# Helper to check contract permission
def check_contract_permission(user: User, contract_id: int, required_level: str, session: Session) -> bool:
    """Check if user has required permission level for a contract.
    Admin users always have full access.
    If NO permission entry exists for the user/contract, DEFAULT IS FULL ACCESS.
    Permissions are OPTIONAL RESTRICTIONS, not required grants.
    required_level: 'read', 'write', or 'full'
    """
    if user.role == "admin":
        return True
    
    permission = session.exec(
        select(ContractPermission)
        .where(ContractPermission.user_id == user.id)
        .where(ContractPermission.contract_id == contract_id)
    ).first()
    
    # NO permission entry
    # Default: READ matches "Wiki-style" open access.
    # WRITE/FULL are restricted to protect data integrity.
    if not permission:
        if required_level == "read":
            return True
        return False
    
    level_hierarchy = {"read": 1, "write": 2, "full": 3}
    return level_hierarchy.get(permission.permission_level, 0) >= level_hierarchy.get(required_level, 0)


# --- Current User Info Endpoint ---
@app.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "has_2fa": bool(current_user.totp_secret)
    }


# --- User Management Endpoints ---
@app.get("/admin/users", response_model=List[UserRead])
def list_users(
    admin: User = Depends(require_admin), 
    session: Session = Depends(get_session)
):
    """List all users (Admin only)"""
    users = session.exec(select(User)).all()
    result = []
    for u in users:
        user_dict = {
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "is_active": u.is_active if hasattr(u, 'is_active') else True,
            "created_at": u.created_at if hasattr(u, 'created_at') else datetime.now(timezone.utc),
            "has_2fa": bool(u.totp_secret)
        }
        result.append(user_dict)
    return result


@app.post("/admin/users", response_model=UserRead)
def create_user(
    request: Request,
    user_data: UserCreate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Create a new user (Admin only)"""
    # Check if username exists
    existing = session.exec(select(User).where(User.username == user_data.username)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    new_user = User(
        username=user_data.username,
        hashed_password=get_password_hash(user_data.password),
        role="user",
        is_active=True,
        created_at=datetime.now(timezone.utc)
    )
    session.add(new_user)
    session.commit()
    session.refresh(new_user)
    
    log_audit(session, admin.id, "CREATE_USER", f"Created user '{new_user.username}'", request.client.host if request.client else "unknown", request.headers.get("user-agent"))
    
    return {
        "id": new_user.id,
        "username": new_user.username,
        "role": new_user.role,
        "is_active": new_user.is_active,
        "created_at": new_user.created_at,
        "has_2fa": False
    }


@app.put("/admin/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    request: Request,
    user_data: UserUpdate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Update a user (Admin only)"""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    changes = []
    
    if user_data.username is not None and user_data.username != user.username:
        # Check if new username exists
        existing = session.exec(select(User).where(User.username == user_data.username)).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username already exists")
        changes.append(f"username: '{user.username}' -> '{user_data.username}'")
        user.username = user_data.username
    
    if user_data.password is not None:
        user.hashed_password = get_password_hash(user_data.password)
        changes.append("password: updated")
    
    if user_data.role is not None and user_data.role != user.role:
        if user_data.role not in ["admin", "user"]:
            raise HTTPException(status_code=400, detail="Role must be 'admin' or 'user'")
        changes.append(f"role: '{user.role}' -> '{user_data.role}'")
        user.role = user_data.role
    
    if user_data.is_active is not None and hasattr(user, 'is_active'):
        if user_data.is_active != user.is_active:
            changes.append(f"is_active: {user.is_active} -> {user_data.is_active}")
            user.is_active = user_data.is_active
    
    if changes:
        session.add(user)
        session.commit()
        session.refresh(user)
        log_audit(session, admin.id, "UPDATE_USER", f"Updated user '{user.username}': {'; '.join(changes)}", request.client.host if request.client else "unknown", request.headers.get("user-agent"))
    
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active if hasattr(user, 'is_active') else True,
        "created_at": user.created_at if hasattr(user, 'created_at') else datetime.now(timezone.utc),
        "has_2fa": bool(user.totp_secret)
    }


@app.delete("/admin/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Deactivate a user (Admin only) - We don't actually delete to preserve audit trail"""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    
    # Deactivate instead of delete
    if hasattr(user, 'is_active'):
        user.is_active = False
        session.add(user)
        session.commit()
    
    log_audit(session, admin.id, "DEACTIVATE_USER", f"Deactivated user '{user.username}'", request.client.host if request.client else "unknown", request.headers.get("user-agent"))
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Permission Management Endpoints ---
@app.get("/admin/permissions", response_model=List[PermissionRead])
def list_permissions(
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """List all contract permissions (Admin only)"""
    perms = session.exec(select(ContractPermission)).all()
    result = []
    for p in perms:
        user = session.get(User, p.user_id)
        contract = session.get(Contract, p.contract_id)
        result.append({
            "id": p.id,
            "user_id": p.user_id,
            "contract_id": p.contract_id,
            "permission_level": p.permission_level,
            "username": user.username if user else None,
            "contract_title": contract.title if contract else None
        })
    return result


@app.get("/admin/users/{user_id}/permissions", response_model=List[PermissionRead])
def get_user_permissions(
    user_id: int,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Get all permissions for a specific user (Admin only)"""
    perms = session.exec(select(ContractPermission).where(ContractPermission.user_id == user_id)).all()
    result = []
    for p in perms:
        contract = session.get(Contract, p.contract_id)
        user = session.get(User, p.user_id)
        result.append({
            "id": p.id,
            "user_id": p.user_id,
            "contract_id": p.contract_id,
            "permission_level": p.permission_level,
            "username": user.username if user else None,
            "contract_title": contract.title if contract else None
        })
    return result


@app.post("/admin/permissions", response_model=PermissionRead)
def create_permission(
    request: Request,
    perm_data: PermissionCreate,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Create a new contract permission (Admin only)"""
    # Validate user and contract exist
    user = session.get(User, perm_data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    contract = session.get(Contract, perm_data.contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    # Check if permission already exists
    existing = session.exec(
        select(ContractPermission)
        .where(ContractPermission.user_id == perm_data.user_id)
        .where(ContractPermission.contract_id == perm_data.contract_id)
    ).first()
    
    if existing:
        # Update existing permission
        existing.permission_level = perm_data.permission_level
        session.add(existing)
        session.commit()
        session.refresh(existing)
        
        log_audit(session, admin.id, "UPDATE_PERMISSION", 
                  f"Updated permission for '{user.username}' on contract '{contract.title}' to '{perm_data.permission_level}'",
                  request.client.host if request.client else "unknown", request.headers.get("user-agent"))
        
        return {
            "id": existing.id,
            "user_id": existing.user_id,
            "contract_id": existing.contract_id,
            "permission_level": existing.permission_level,
            "username": user.username,
            "contract_title": contract.title
        }
    
    new_perm = ContractPermission(
        user_id=perm_data.user_id,
        contract_id=perm_data.contract_id,
        permission_level=perm_data.permission_level
    )
    session.add(new_perm)
    session.commit()
    session.refresh(new_perm)
    
    log_audit(session, admin.id, "CREATE_PERMISSION", 
              f"Granted '{perm_data.permission_level}' permission to '{user.username}' for contract '{contract.title}'",
              request.client.host if request.client else "unknown", request.headers.get("user-agent"))
    
    return {
        "id": new_perm.id,
        "user_id": new_perm.user_id,
        "contract_id": new_perm.contract_id,
        "permission_level": new_perm.permission_level,
        "username": user.username,
        "contract_title": contract.title
    }


@app.delete("/admin/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_permission(
    permission_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    session: Session = Depends(get_session)
):
    """Delete a contract permission (Admin only)"""
    perm = session.get(ContractPermission, permission_id)
    if not perm:
        raise HTTPException(status_code=404, detail="Permission not found")
    
    user = session.get(User, perm.user_id)
    contract = session.get(Contract, perm.contract_id)
    
    session.delete(perm)
    session.commit()
    
    log_audit(session, admin.id, "DELETE_PERMISSION", 
              f"Revoked permission from '{user.username if user else 'Unknown'}' for contract '{contract.title if contract else 'Unknown'}'",
              request.client.host if request.client else "unknown", request.headers.get("user-agent"))
    
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ========================================
#           CONTRACT LISTS ENDPOINTS
# ========================================

@app.get("/lists", response_model=List[ContractListRead])
def get_lists(
    current_user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    """Get all contract lists with contract counts."""
    lists = session.exec(select(ContractList)).all()
    result = []
    for lst in lists:
        count = session.exec(
            select(func.count(ContractListLink.contract_id))
            .where(ContractListLink.list_id == lst.id)
        ).one()
        result.append({
            "id": lst.id,
            "name": lst.name,
            "description": lst.description,
            "color": lst.color,
            "created_at": lst.created_at,
            "contract_count": count or 0
        })
    return result


@app.post("/lists", response_model=ContractListRead, status_code=201)
def create_list(
    list_data: ContractListCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Create a new contract list."""
    new_list = ContractList(
        name=list_data.name,
        description=list_data.description,
        color=list_data.color
    )
    session.add(new_list)
    session.commit()
    session.refresh(new_list)
    return {
        "id": new_list.id,
        "name": new_list.name,
        "description": new_list.description,
        "color": new_list.color,
        "created_at": new_list.created_at,
        "contract_count": 0
    }


@app.get("/lists/{list_id}", response_model=ContractListRead)
def get_list(
    list_id: int, 
    current_user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    """Get a specific list with its contract count."""
    lst = session.get(ContractList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")
    
    count = session.exec(
        select(func.count(ContractListLink.contract_id))
        .where(ContractListLink.list_id == lst.id)
    ).one()
    
    return {
        "id": lst.id,
        "name": lst.name,
        "description": lst.description,
        "color": lst.color,
        "created_at": lst.created_at,
        "contract_count": count or 0
    }


@app.put("/lists/{list_id}", response_model=ContractListRead)
def update_list(
    list_id: int,
    list_data: ContractListUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Update a list."""
    lst = session.get(ContractList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")
    
    if list_data.name is not None:
        lst.name = list_data.name
    if list_data.description is not None:
        lst.description = list_data.description
    if list_data.color is not None:
        lst.color = list_data.color
    
    session.add(lst)
    session.commit()
    session.refresh(lst)
    
    count = session.exec(
        select(func.count(ContractListLink.contract_id))
        .where(ContractListLink.list_id == lst.id)
    ).one()
    
    return {
        "id": lst.id,
        "name": lst.name,
        "description": lst.description,
        "color": lst.color,
        "created_at": lst.created_at,
        "contract_count": count or 0
    }


@app.delete("/lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_list(
    list_id: int, 
    current_user: User = Depends(get_current_user), 
    session: Session = Depends(get_session)
):
    """Delete a list (contracts are NOT deleted, only the association)."""
    lst = session.get(ContractList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")
    
    # Remove all links first
    session.exec(delete(ContractListLink).where(ContractListLink.list_id == list_id))
    session.delete(lst)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/lists/{list_id}/contracts/{contract_id}", status_code=201)
def add_contract_to_list(
    list_id: int,
    contract_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Add a contract to a list."""
    # Check list exists
    lst = session.get(ContractList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")
    
    # Check contract exists
    contract = session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    
    # Check if already linked
    existing = session.exec(
        select(ContractListLink).where(
            ContractListLink.list_id == list_id,
            ContractListLink.contract_id == contract_id
        )
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Contract already in list")
    
    link = ContractListLink(list_id=list_id, contract_id=contract_id)
    session.add(link)
    session.commit()
    return {"ok": True, "message": f"Contract '{contract.title}' added to list '{lst.name}'"}


@app.delete("/lists/{list_id}/contracts/{contract_id}")
def remove_contract_from_list(
    list_id: int,
    contract_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Remove a contract from a list."""
    link = session.exec(
        select(ContractListLink).where(
            ContractListLink.list_id == list_id,
            ContractListLink.contract_id == contract_id
        )
    ).first()
    
    if not link:
        raise HTTPException(status_code=404, detail="Contract not in list")
    
    session.delete(link)
    session.commit()
    return {"ok": True, "message": "Contract removed from list"}


@app.get("/lists/{list_id}/contracts", response_model=List[ContractRead])
def get_list_contracts(
    list_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Get all contracts in a specific list."""
    lst = session.get(ContractList, list_id)
    if not lst:
        raise HTTPException(status_code=404, detail="List not found")
    
    contracts = session.exec(
        select(Contract)
        .join(ContractListLink)
        .where(ContractListLink.list_id == list_id)
    ).all()
    
    return contracts


# ========================================
#           AI FEATURES (Mistral Large 3)
# ========================================

# Imports moved to top


@app.post("/contracts/analyze", response_model=ContractAnalysisResult)
@limiter.limit("5/minute")
async def analyze_contract_pdf(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Analyze a PDF contract using Mistral AI and extract structured data.
    Returns auto-fill suggestions for contract form fields.
    """
    if not os.getenv("MISTRAL_API_KEY"):
        raise HTTPException(
            status_code=503, 
            detail="KI-Analyse nicht verfügbar. MISTRAL_API_KEY nicht konfiguriert."
        )
    
    # Use consolidated validation
    try:
        mime_type = await validate_file(file)
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail="Invalid file")
        
    if mime_type != "application/pdf":
         raise HTTPException(status_code=400, detail="Nur PDF-Dateien werden unterstützt.")

    # Read full file into memory
    pdf_bytes = await file.read()
    
    try:
        from ai_service import analyze_contract_pdf as analyze_pdf
        result = await analyze_pdf(pdf_bytes)
        return ContractAnalysisResult(**result)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        print(f"[AI ERROR] Contract analysis failed: {e}")
        raise HTTPException(
            status_code=500, 
            detail="KI-Analyse fehlgeschlagen. Bitte versuche es erneut."
        )


@app.post("/contracts/{contract_id}/chat", response_model=ChatResponse)
@limiter.limit("10/minute")
async def chat_with_contract(
    contract_id: int,
    chat_req: ChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    Chat with AI about a specific contract.
    Ask questions about contract terms, dates, conditions, etc.
    """
    if not os.getenv("MISTRAL_API_KEY"):
        raise HTTPException(
            status_code=503, 
            detail="KI-Chat nicht verfügbar. MISTRAL_API_KEY nicht konfiguriert."
        )
    
    contract = session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Vertrag nicht gefunden")
    
    # Check permission
    if not check_contract_permission(current_user, contract_id, "read", session):
        raise HTTPException(status_code=403, detail="Keine Berechtigung für diesen Vertrag")
    
    try:
        abs_path = resolve_file_path(contract.file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Vertragsdatei nicht gefunden")
    
    try:
        import aiofiles
        async with aiofiles.open(abs_path, "rb") as f:
            pdf_bytes = await f.read()
        
        from ai_service import chat_about_contract
        answer = await chat_about_contract(pdf_bytes, chat_req.question)
        return ChatResponse(answer=answer)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        print(f"[AI ERROR] Contract chat failed: {e}")
        raise HTTPException(
            status_code=500, 
            detail="KI-Chat fehlgeschlagen. Bitte versuche es erneut."
        )


from fastapi.responses import StreamingResponse

@app.post("/contracts/{contract_id}/chat/stream")
@limiter.limit("10/minute")
async def chat_with_contract_stream(
    contract_id: int,
    chat_req: ChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    Stream chat responses about a contract using Server-Sent Events.
    Tokens are sent as they arrive for real-time response display.
    """
    if not os.getenv("MISTRAL_API_KEY"):
        raise HTTPException(
            status_code=503, 
            detail="KI-Chat nicht verfügbar. MISTRAL_API_KEY nicht konfiguriert."
        )
    
    contract = session.get(Contract, contract_id)
    if not contract:
        raise HTTPException(status_code=404, detail="Vertrag nicht gefunden")
    
    # Check permission
    if not check_contract_permission(current_user, contract_id, "read", session):
        raise HTTPException(status_code=403, detail="Keine Berechtigung für diesen Vertrag")
    
    try:
        abs_path = resolve_file_path(contract.file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Vertragsdatei nicht gefunden")
    
    # Read PDF into memory
    import aiofiles
    async with aiofiles.open(abs_path, "rb") as f:
        pdf_bytes = await f.read()
    
    async def generate_stream():
        """Generate SSE stream from AI response."""
        import json as _json
        try:
            from ai_service import chat_about_contract_stream
            async for chunk in chat_about_contract_stream(pdf_bytes, chat_req.question):
                # JSON-encode chunk to preserve newlines and special chars
                yield f"data: {_json.dumps(chunk)}\n\n"
            # Send done signal
            yield "data: \"[DONE]\"\n\n"
        except Exception as e:
            print(f"[AI ERROR] Stream failed: {e}")
            yield f"data: {_json.dumps(f'[ERROR] {str(e)}')}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@app.get("/ai/status")
def get_ai_status(current_user: User = Depends(get_current_user)):
    """Check if AI features are available."""
    has_key = bool(os.getenv("MISTRAL_API_KEY"))
    return {
        "available": has_key,
        "model": "mistral-large-latest" if has_key else None,
        "features": ["contract_analysis", "contract_chat"] if has_key else []
    }
