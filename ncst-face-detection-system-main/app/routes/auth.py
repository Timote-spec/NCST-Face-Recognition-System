from datetime import datetime, timedelta, timezone

import bcrypt as _bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.database import get_db_connection, get_admin_email, log_system_action, pst_str
from app.email_service import send_password_reset_email
from app.schemas import (
    AdminLoginRequest,
    AdminRegisterRequest,
    ForgotPasswordRequest,
    GenericResponse,
    ResetPasswordTokenRequest,
    TokenResponse,
)
from app.services.password_reset_service import (
    generate_reset_token,
    is_reset_expired,
    verify_reset_token,
)

router = APIRouter()
_security = HTTPBearer(auto_error=False)

GENERIC_RESET_MESSAGE = (
    "If an account exists with that email, a password reset link has been sent."
)
PENDING_APPROVAL_MESSAGE = "Your account is pending admin approval."


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


def _send_email_or_fail(send_fn, *args) -> None:
    try:
        send_fn(*args)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send email. Check Gmail SMTP settings in .env ({exc})",
        ) from exc


def _is_allowed_registration_email(email: str) -> bool:
    return True


# ─── Endpoints ─────────────────────────────────────────────────────

@router.post("/auth/register", response_model=GenericResponse)
def register_admin(body: AdminRegisterRequest):
    conn = get_db_connection()
    email = body.email.strip().lower()

    if not _is_allowed_registration_email(email):
        raise HTTPException(
            status_code=403,
            detail="Registration is restricted to authorized emails only.",
        )

    existing = conn.execute(
        "SELECT approval_status FROM admins WHERE email = ?",
        (email,),
    ).fetchone()
    if existing:
        if existing["approval_status"] == "pending":
            raise HTTPException(
                status_code=409,
                detail="A registration for this email is already pending approval.",
            )
        raise HTTPException(status_code=409, detail="Email already registered")

    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    password_hash = _hash_password(body.password)
    now_str = pst_str()
    try:
        conn.execute(
            """
            INSERT INTO admins (
                admin_id, email, password_hash, first_name, last_name, created_at,
                is_approved, approval_status
            ) VALUES (?, ?, ?, ?, ?, ?, 0, 'pending')
            """,
            (body.admin_id, email, password_hash, body.first_name, body.last_name, now_str),
        )
        conn.commit()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    log_system_action(
        email,
        "REGISTER",
        f"Admin registration submitted for {email} (pending approval)",
    )

    return GenericResponse(
        status="ok",
        message=(
            "Registration submitted successfully! Please wait for an administrator "
            "to verify and approve your account."
        ),
    )


@router.post("/auth/login", response_model=TokenResponse)
def login_admin(body: AdminLoginRequest):
    conn = get_db_connection()
    row = conn.execute(
        """
        SELECT admin_id, email, password_hash, is_approved, approval_status
        FROM admins WHERE email = ?
        """,
        (body.email.strip().lower(),),
    ).fetchone()

    if not row or not _verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if row["approval_status"] == "rejected":
        raise HTTPException(
            status_code=403,
            detail="Your account registration was rejected. Contact an administrator.",
        )

    if not row["is_approved"] or row["approval_status"] != "approved":
        raise HTTPException(status_code=403, detail=PENDING_APPROVAL_MESSAGE)

    token = _create_token(row["admin_id"])

    admin_email = row["email"]
    log_system_action(admin_email, "LOGIN", f"Admin {admin_email} signed in")

    return TokenResponse(access_token=token)


@router.post("/auth/logout", response_model=GenericResponse)
def logout_admin(_admin: str = Depends(get_current_admin)):
    admin_email = get_admin_email(_admin)
    log_system_action(admin_email, "LOGOUT", f"Admin {admin_email} signed out")
    return GenericResponse(status="ok", message="Signed out")


@router.post("/auth/forgot-password", response_model=GenericResponse)
def forgot_password(body: ForgotPasswordRequest):
    email = body.email.strip().lower()
    conn = get_db_connection()
    row = conn.execute(
        "SELECT admin_id FROM admins WHERE email = ?",
        (email,),
    ).fetchone()

    if row:
        plain_token, token_hash, expires_at = generate_reset_token()
        conn.execute(
            """
            UPDATE admins
               SET reset_password_token = ?,
                   reset_password_expires = ?
             WHERE email = ?
            """,
            (token_hash, expires_at.strftime("%Y-%m-%d %H:%M:%S"), email),
        )
        conn.commit()

        reset_link = (
            f"{settings.frontend_base_url.rstrip('/')}/reset-password?token={plain_token}"
        )
        _send_email_or_fail(send_password_reset_email, email, reset_link)

        log_system_action(email, "PASSWORD_RESET_REQUEST", f"Password reset link sent to {email}")

    return GenericResponse(status="ok", message=GENERIC_RESET_MESSAGE)


@router.post("/auth/reset-password", response_model=GenericResponse)
def reset_password(body: ResetPasswordTokenRequest):
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    conn = get_db_connection()
    rows = conn.execute(
        """
        SELECT admin_id, email, reset_password_token, reset_password_expires
        FROM admins
        WHERE reset_password_token IS NOT NULL
        """
    ).fetchall()

    matched = None
    for row in rows:
        if verify_reset_token(body.token.strip(), row["reset_password_token"]):
            matched = row
            break

    if not matched:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    if is_reset_expired(matched["reset_password_expires"]):
        conn.execute(
            """
            UPDATE admins
               SET reset_password_token = NULL,
                   reset_password_expires = NULL
             WHERE admin_id = ?
            """,
            (matched["admin_id"],),
        )
        conn.commit()
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    new_hash = _hash_password(body.new_password)
    conn.execute(
        """
        UPDATE admins
           SET password_hash = ?,
               reset_password_token = NULL,
               reset_password_expires = NULL
         WHERE admin_id = ?
        """,
        (new_hash, matched["admin_id"]),
    )
    conn.commit()

    log_system_action(
        matched["email"],
        "PASSWORD_RESET",
        f"Password reset completed for {matched['email']}",
    )

    return GenericResponse(status="ok", message="Password has been reset successfully")
