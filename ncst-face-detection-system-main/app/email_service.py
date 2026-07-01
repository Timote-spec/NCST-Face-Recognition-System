import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger(__name__)


def send_otp_email(to_email: str, otp: str) -> None:
    subject = "NCST Face Recognition — Password Reset OTP"
    body = f"""Hello,

You requested a password reset for your NCST Face Recognition admin account.

Your one-time password (OTP) is: {otp}

This code expires in {settings.otp_expiry_minutes} minutes. If you did not request this, you can ignore this email.

— NCST Face Recognition System
"""

    if not settings.smtp_host:
        logger.warning(
            "SMTP not configured — OTP for %s: %s (set SMTP_HOST in .env to send emails)",
            to_email,
            otp,
        )
        print(f"[DEV] OTP for {to_email}: {otp}")
        return

    msg = MIMEMultipart()
    msg["From"] = settings.smtp_from_email or settings.smtp_user
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)
