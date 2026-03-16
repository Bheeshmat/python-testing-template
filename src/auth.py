"""
JWT Authentication utilities.

TEMPLATE NOTE:
- SECRET_KEY must be set in .env for production. Never hardcode it.
- get_current_user is a FastAPI dependency — inject with Depends(get_current_user).
- In tests, override get_current_user via app.dependency_overrides to skip
  token validation. See tests/conftest.py for the authenticated_client fixture.
"""

import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
# Generate a secure key: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# ── Password Hashing ──────────────────────────────────────────────────────────
# bcrypt is the industry standard for password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── OAuth2 Scheme ─────────────────────────────────────────────────────────────
# tokenUrl tells FastAPI where clients send credentials to get a token
# This also powers the Swagger UI "Authorize" button
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    """Returns a bcrypt hash of the given password."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Returns True if the plain password matches the hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    """
    Creates a signed JWT token.

    Args:
        data: Payload to encode. Typically {"sub": str(user_id)}.
              "sub" (subject) is the JWT standard field for the user identifier.

    Returns:
        Signed JWT token string.
    """
    payload = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload.update({"exp": expire})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """
    FastAPI dependency — decodes the JWT and returns the current user info.

    Usage in routes:
        @app.get("/users/me")
        def get_me(current_user: dict = Depends(get_current_user)):
            return {"user_id": current_user["user_id"]}

    Raises:
        HTTPException 401: if the token is missing, expired, or invalid.

    TESTING NOTE:
        Override this in tests with app.dependency_overrides[get_current_user].
        See the authenticated_client fixture in tests/conftest.py.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        return {"user_id": int(user_id)}
    except JWTError:
        raise credentials_exception
