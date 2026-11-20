"""Send the finished analysis email (with the workbook attached) to the analyst's inbox.

The .eml HAP already writes is a complete message (text, HTML, the workbook as attachment), so delivery only sets the recipient
and sender and hands it to an SMTP server. Settings come from the environment or backend/.env (never committed):

    HAP_EMAIL_TO         recipient, default houda@vlixes.us
    HAP_SMTP_USER        the mailbox that sends (for Gmail / Google Workspace: the address itself)
    HAP_SMTP_PASSWORD    an APP PASSWORD for that mailbox (not the normal password)
    HAP_SMTP_HOST        default smtp.gmail.com
    HAP_SMTP_PORT        default 587 (STARTTLS); 465 uses SSL
    HAP_EMAIL_FROM       optional, default HAP_SMTP_USER
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email import policy
from email.parser import BytesParser
from pathlib import Path

DEFAULT_TO = "houda@vlixes.us"
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def _setting(name: str, default: str | None = None) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            key, sep, val = line.partition("=")
            if sep and key.strip() == name and val.strip():
                return val.strip().strip('"').strip("'")
    except OSError:
        pass
    return default


def delivery_configured() -> bool:
    return bool(_setting("HAP_SMTP_USER") and _setting("HAP_SMTP_PASSWORD"))


def send_analysis_email(eml_path: Path | str, *, to: str | None = None) -> dict:
    """Send the saved .eml as is (attachments included). Returns {"sent": bool, "to": ..., "error": ...}; never raises."""
    recipient = to or _setting("HAP_EMAIL_TO", DEFAULT_TO)
    user, password = _setting("HAP_SMTP_USER"), _setting("HAP_SMTP_PASSWORD")
    if not (user and password):
        return {"sent": False, "to": recipient, "error": "email not configured: set HAP_SMTP_USER and HAP_SMTP_PASSWORD (an app password) in backend/.env"}
    try:
        msg = BytesParser(policy=policy.SMTP).parse(open(eml_path, "rb"))
        for header in ("X-Unsent", "To", "From", "Cc", "Bcc"):
            del msg[header]
        msg["To"] = recipient
        msg["From"] = _setting("HAP_EMAIL_FROM", user)
        host, port = _setting("HAP_SMTP_HOST", "smtp.gmail.com"), int(_setting("HAP_SMTP_PORT", "587"))
        context = ssl.create_default_context()                 # the OS trust store, as for Google Drive (antivirus HTTPS scanning)
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=context, timeout=60) as smtp:
                smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=60) as smtp:
                smtp.starttls(context=context)
                smtp.login(user, password)
                smtp.send_message(msg)
        return {"sent": True, "to": recipient, "error": None}
    except Exception as exc:  # noqa: BLE001 - a failed send must not lose the analysis
        return {"sent": False, "to": recipient, "error": f"{type(exc).__name__}: {exc}"}
