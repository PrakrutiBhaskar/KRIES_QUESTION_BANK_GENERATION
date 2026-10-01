"""Outgoing email (password-reset links).

Configured with SMTP_* in .env. With SMTP_HOST unset nothing is sent: the
message is written to the backend log so the reset flow can be tried locally
without a mail server.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from ..config import settings

logger = logging.getLogger("backend.mailer")


def _deliver(msg: EmailMessage) -> None:
    """Blocking SMTP send. Run it off the event loop (BackgroundTasks does)."""
    if settings.smtp_security == "ssl":
        server: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=15,
            context=ssl.create_default_context(),
        )
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
    with server:
        if settings.smtp_security == "starttls":
            server.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(msg)


def send_password_reset_email(to: str, name: str, link: str) -> None:
    minutes = settings.password_reset_expire_minutes
    if not settings.smtp_host:
        logger.warning(
            "SMTP_HOST is not set, so no email was sent. Password reset link for %s "
            "(valid %d minutes): %s",
            to, minutes, link,
        )
        return

    msg = EmailMessage()
    msg["Subject"] = "Reset your KRIES password"
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg.set_content(
        f"Hi {name},\n\n"
        f"We received a request to reset your KRIES password. Open this link to choose a new one "
        f"(it works once and expires in {minutes} minutes):\n\n{link}\n\n"
        "If you didn't ask for this, you can ignore this email; your password won't change.\n"
    )
    try:
        _deliver(msg)
    except Exception:  # never surface mail problems to the caller (that would reveal the account exists)
        logger.exception("Could not send the password reset email to %s", to)
