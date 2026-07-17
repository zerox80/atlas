"""Password hashing and JWT creation helpers."""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from jose import jwt
from passlib.context import CryptContext

SECRET_KEY = os.getenv("SECRET_KEY")
INSECURE_SECRET_KEYS = {
    "change_this_to_a_secure_random_hex_string",
    "changeme",
    "secret",
}
if (
    not SECRET_KEY
    or len(SECRET_KEY) < 32
    or SECRET_KEY.strip().lower() in INSECURE_SECRET_KEYS
):
    raise ValueError(
        "FATAL: SECRET_KEY must be a unique random value with at least 32 characters."
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its stored hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password using the configured password context."""
    return pwd_context.hash(password)


def create_access_token(
    data: Mapping[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT using the configured or explicitly supplied lifetime."""
    to_encode = dict(data)
    lifetime = expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + lifetime
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
