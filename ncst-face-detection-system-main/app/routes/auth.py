from datetime import datetime, timedelta, timezone

import bcrypt as _bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.database import get_db_connection, get_admin_email, log_system_action, pst_str
from app.email_service import send_otp_email
from app.otp_service import can_request_otp, generate_otp, store_otp, verify_otp
from app.schemas import (
    AdminLoginRequest,
    AdminRegisterRequest,
    AdminResponse,
    GenericResponse,
    RequestOtpRequest,
    ResetPasswordRequest,
    TokenResponse,
)

router = APIRouter()
_security = HTTPBearer(auto_error=False)


# ─── JWT helpers ───────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def _verify_password(password: str, password_hash: str) -> bool:
    return _bcrypt.checkpw(password.encode(), password_hash.encode())


def _create_token(admin_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": admin_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expiry_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# ─── Endpoints ─────────────────────────────────────────────────────

@router.post("/auth/register", response_model=AdminResponse)
def register_admin(body: AdminRegisterRequest):
    conn = get_db_connection()
    email = body.email.strip().lower()
    existing = conn.execute("SELECT 1 FROM admins WHERE email = ?", (email,)).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    password_hash = _hash_password(body.password)
    now_str = pst_str()
    try:
        conn.execute(
            "INSERT INTO admins (admin_id, email, password_hash, first_name, last_name, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (body.admin_id, email, password_hash, body.first_name, body.last_name, now_str),
        )
        conn.commit()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    row = conn.execute(
        "SELECT admin_id, email, first_name, last_name, created_at FROM admins WHERE admin_id = ?",
        (body.admin_id,),
    ).fetchone()

    return AdminResponse(
        admin_id=row["admin_id"],
        email=row["email"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        created_at=row["created_at"],
    )


@router.post("/auth/login", response_model=TokenResponse)
def login_admin(body: AdminLoginRequest):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT admin_id, email, password_hash FROM admins WHERE email = ?",
        (body.email.strip().lower(),),
    ).fetchone()

    if not row or not _verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = _create_token(row["admin_id"])

    admin_email = row["email"]
    log_system_action(admin_email, "LOGIN", f"Admin {admin_email} signed in")

    return TokenResponse(access_token=token)


@router.post("/auth/logout", response_model=GenericResponse)
def logout_admin(_admin: str = Depends(get_current_admin)):
    admin_email = get_admin_email(_admin)
    log_system_action(admin_email, "LOGOUT", f"Admin {admin_email} signed out")
    return GenericResponse(status="ok", message="Signed out")


@router.post("/auth/forgot-password/request-otp", response_model=GenericResponse)
def request_password_otp(body: RequestOtpRequest):
    email = body.email.strip().lower()
    conn = get_db_connection()
    row = conn.execute("SELECT 1 FROM admins WHERE email = ?", (email,)).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="No account found with this email")

    if not can_request_otp(email):
        raise HTTPException(
            status_code=429,
            detail="Please wait a minute before requesting another OTP",
        )

    otp = generate_otp()
    store_otp(email, otp)

    try:
        send_otp_email(email, otp)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to send OTP email. Please try again later.",
        )

    log_system_action(email, "OTP_REQUEST", f"Password reset OTP requested for {email}")

    return GenericResponse(
        status="ok",
        message="A verification code has been sent to your email",
    )


@router.post("/auth/forgot-password/reset", response_model=GenericResponse)
def reset_password_with_otp(body: ResetPasswordRequest):
    email = body.email.strip().lower()

    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    conn = get_db_connection()
    row = conn.execute("SELECT 1 FROM admins WHERE email = ?", (email,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No account found with this email")

    if not verify_otp(email, body.otp.strip()):
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")

    new_hash = _hash_password(body.new_password)
    conn.execute(
        "UPDATE admins SET password_hash = ? WHERE email = ?",
        (new_hash, email),
    )
    conn.commit()

    log_system_action(email, "PASSWORD_RESET", f"Password reset for {email}")

    return GenericResponse(status="ok", message="Password has been reset successfully")
