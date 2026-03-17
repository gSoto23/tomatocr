
from datetime import datetime, timedelta
from typing import Optional, Union
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings

import bcrypt

# Password hashing
# Workaround for passlib + modern bcrypt (Issue with 72 byte limit check)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    # Passlib triggers an internal bcrypt limit check even on short passwords due to padding bugs in python 3.12+ 
    # Or in newer `bcrypt` library iterations. It's safer to use passlib with a manual truncate wrapper
    if len(plain_password) > 71:
        plain_password = plain_password[:71]
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    if len(password) > 71:
        password = password[:71]
    return pwd_context.hash(password)

# JWT
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt
