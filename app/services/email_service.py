import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger("brightloop.email")


def send_email(to: str, subject: str, body: str) -> None:
    """Send via SMTP when configured, otherwise print to the console (Level 1)."""
    if not settings.smtp_host:
        print(f"\n=== EMAIL (console) ===\nTo: {to}\nSubject: {subject}\n\n{body}\n=======================\n", flush=True)
        return

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError):
        logger.exception("SMTP send failed; message for %s follows", to)
        print(f"\n=== EMAIL (SMTP failed, console) ===\nTo: {to}\nSubject: {subject}\n\n{body}\n", flush=True)
