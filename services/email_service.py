"""
Free email sending via SMTP — works without Instantly.
For Gmail: enable 2FA → App Passwords → generate one for "Mail".
Set SMTP_USER=you@gmail.com  SMTP_PASSWORD=xxxx-xxxx-xxxx-xxxx in .env
"""
import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from ..utils.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
from ..utils.logger import get_logger

logger = get_logger(__name__)


def _send_sync(to: str, subject: str, body: str) -> bool:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = to
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, [to], msg.as_string())
    return True


async def send_email(to: str, subject: str, body: str) -> bool:
    """Send one email via SMTP. Returns True on success."""
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("email.smtp.not_configured")
        return False
    try:
        result = await asyncio.to_thread(_send_sync, to, subject, body)
        logger.info("email.smtp.sent", to=to, subject=subject[:50])
        return result
    except Exception as e:
        logger.error("email.smtp.failed", to=to, error=str(e))
        return False
