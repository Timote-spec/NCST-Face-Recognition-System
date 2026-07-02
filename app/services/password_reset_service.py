import secrets
from datetime import datetime, timedelta, timezone

import bcrypt as _bcrypt

from app.config import settings


def generate_reset_token() -> tuple[str, str, datetime]:
    """Return (plain_token, hashed_token, expires_at)."""
    plain_token = secrets.token_urlsafe(32)
    token_hash = _bcrypt.hashpw(plain_token.encode(), _bcrypt.gensalt()).decode()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.password_reset_expiry_hours)
    return plain_token, token_hash, expires_at


def verify_reset_token(plain_token: str, stored_hash: str | None) -> bool:
    if not plain_token or not stored_hash:
        return False
    try:
        return _bcrypt.checkpw(plain_token.encode(), stored_hash.encode())
    except ValueError:
        return False


def is_reset_expired(expires_at: str | datetime | None) -> bool:
    if not expires_at:
        return True
    if isinstance(expires_at, str):
        try:
            expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            expires_dt = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    else:
        expires_dt = expires_at
    if expires_dt.tzinfo is None:
        expires_dt = expires_dt.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > expires_dt
