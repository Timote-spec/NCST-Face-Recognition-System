import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger(__name__)


def is_email_configured() -> bool:
    return bool(
        settings.smtp_host.strip()
        and settings.smtp_user.strip()
        and settings.smtp_password.strip()
    )


def _send_email(to_email: str, subject: str, body: str) -> None:
    if not is_email_configured():
        logger.warning(
            "SMTP not fully configured — email to %s not sent. "
            "Set SMTP_HOST, SMTP_USER, and SMTP_PASSWORD in .env. Subject: %s",
            to_email,
            subject,
        )
        print(f"[DEV] Email to {to_email}\nSubject: {subject}\n\n{body}")
        return

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
