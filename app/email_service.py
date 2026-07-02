import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger(__name__)


def _gmail_configured() -> bool:
    return bool(settings.gmail_user.strip() and settings.gmail_app_password.strip())


def _smtp_configured() -> bool:
    return bool(
        settings.smtp_host.strip()
        and settings.smtp_user.strip()
        and settings.smtp_password.strip()
    )


def is_email_configured() -> bool:
    return _gmail_configured() or _smtp_configured()


def _send_via_gmail(to_email: str, subject: str, body: str) -> None:
    from_address = settings.gmail_user.strip()
    msg = MIMEMultipart()
    msg["From"] = from_address
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
        server.starttls()
        server.login(settings.gmail_user.strip(), settings.gmail_app_password.strip())
        server.send_message(msg)


def _send_via_smtp(to_email: str, subject: str, body: str) -> None:
    from_address = settings.smtp_from_email or settings.smtp_user
    if not from_address:
        raise ValueError("SMTP_FROM_EMAIL or SMTP_USER must be set when SMTP_HOST is configured")

    msg = MIMEMultipart()
    msg["From"] = from_address
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            if settings.smtp_user and settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


def _send_email(to_email: str, subject: str, body: str) -> None:
    if not is_email_configured():
        logger.warning(
            "Email not configured — message to %s not sent. Subject: %s",
            to_email,
            subject,
        )
        print(f"[DEV] Email to {to_email}\nSubject: {subject}\n\n{body}")
        return

    if _gmail_configured():
        _send_via_gmail(to_email, subject, body)
        return

    _send_via_smtp(to_email, subject, body)


def send_password_reset_email(to_email: str, reset_link: str) -> None:
    subject = "NCST Face Recognition — Reset Your Password"
    body = f"""Hello,

You requested a password reset for your NCST Face Recognition admin account.

Click the link below to set a new password (valid for {settings.password_reset_expiry_hours} hour(s)):

{reset_link}

If you did not request this, you can safely ignore this email. Your password will not change.

— NCST Face Recognition System
"""
    _send_email(to_email, subject, body)


def send_account_approved_email(to_email: str, first_name: str) -> None:
    subject = "NCST Face Recognition — Account Approved"
    login_url = f"{settings.frontend_base_url.rstrip('/')}/login"
    body = f"""Hello {first_name},

Your NCST Face Recognition administrator account has been approved.

You can now sign in at:
{login_url}

— NCST Face Recognition System
"""
    _send_email(to_email, subject, body)


def send_otp_email(to_email: str, otp: str) -> None:
    subject = "NCST Face Recognition — Password Reset OTP"
    body = f"""Hello,

You requested a password reset for your NCST Face Recognition admin account.

Your one-time password (OTP) is: {otp}

This code expires in {settings.otp_expiry_minutes} minutes. If you did not request this, you can ignore this email.

— NCST Face Recognition System
"""
    _send_email(to_email, subject, body)


def send_registration_verification_email(
    admin_email: str,
    otp: str,
    *,
    registering_email: str,
) -> None:
    subject = "NCST Face Recognition — New Admin Registration Approval"
    body = f"""Hello Administrator,

Someone is attempting to create a new NCST Face Recognition admin account.

Registering email: {registering_email}

Approval verification code: {otp}

Share this code with the person registering only if you approve this account.
This code expires in {settings.otp_expiry_minutes} minutes.

If you did not expect this request, ignore this email and do not share the code.

— NCST Face Recognition System
"""
    _send_email(admin_email, subject, body)
