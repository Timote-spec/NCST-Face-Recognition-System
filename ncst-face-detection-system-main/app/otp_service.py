import hashlib
import secrets
from datetime import timedelta

from app.config import settings
from app.database import get_db_connection, pst_now, pst_str


def _hash_otp(email: str, otp: str) -> str:
    payload = f"{email}:{otp}:{settings.jwt_secret_key}"
    return hashlib.sha256(payload.encode()).hexdigest()


def generate_otp() -> str:
    return f"{secrets.randbelow(900000) + 100000:06d}"


def store_otp(email: str, otp: str) -> None:
    conn = get_db_connection()
    otp_hash = _hash_otp(email, otp)
    expires_at = pst_str(pst_now() + timedelta(minutes=settings.otp_expiry_minutes))

    conn.execute("DELETE FROM password_otps WHERE email = ?", (email,))
    conn.execute(
        "INSERT INTO password_otps (email, otp_hash, expires_at, created_at) VALUES (?, ?, ?, ?)",
        (email, otp_hash, expires_at, pst_str()),
    )
    conn.commit()


def verify_otp(email: str, otp: str) -> bool:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT otp_hash, expires_at FROM password_otps WHERE email = ?",
        (email,),
    ).fetchone()

    if not row:
        return False

    if pst_str() > row["expires_at"]:
        conn.execute("DELETE FROM password_otps WHERE email = ?", (email,))
        conn.commit()
        return False

    if _hash_otp(email, otp) != row["otp_hash"]:
        return False

    conn.execute("DELETE FROM password_otps WHERE email = ?", (email,))
    conn.commit()
    return True


def can_request_otp(email: str) -> bool:
    conn = get_db_connection()
    row = conn.execute(
        "SELECT created_at FROM password_otps WHERE email = ? ORDER BY created_at DESC LIMIT 1",
        (email,),
    ).fetchone()
    if not row:
        return True

    from datetime import datetime

    created = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
    now = pst_now().replace(tzinfo=None)
    return now >= created + timedelta(seconds=60)
