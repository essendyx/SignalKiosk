import base64
import hashlib
import os
from datetime import datetime, timedelta, timezone
from cryptography.fernet import Fernet
from jose import jwt
from passlib.context import CryptContext
from .config import encryption_key_path, settings

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(raw: str, hashed: str) -> bool:
    return pwd_ctx.verify(raw, hashed)


def hash_password(raw: str) -> str:
    return pwd_ctx.hash(raw)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _load_or_create_fernet_key() -> bytes:
    if settings.secret_encryption_key:
        return settings.secret_encryption_key.encode("utf-8")
    path = encryption_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_text(encoding="utf-8").strip().encode("utf-8")
    key = Fernet.generate_key()
    path.write_text(key.decode("utf-8"), encoding="utf-8")
    return key


_fernet = Fernet(_load_or_create_fernet_key())


def encrypt_secret(value: str) -> str:
    return _fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    return _fernet.decrypt(value.encode("utf-8")).decode("utf-8")


def create_access_token(subject: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": subject, "role": role, "exp": now + timedelta(hours=12), "iat": now}
    return jwt.encode(payload, settings.app_secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.app_secret_key, algorithms=["HS256"])
