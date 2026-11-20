"""Send the finished analysis email (with the workbook attached) to the analyst's inbox.

Two ways to send, tried in this order:
  1. Gmail API (no password): sign in once as the sending mailbox with  python scripts/gmail_login.py  (token kept in storage/drive).
  2. SMTP with an app password (settings below).

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


GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_TOKEN = "gmail_token.json"


def _gmail_ready() -> bool:
    from services.drive_sync_service import auth_dir

    return (auth_dir() / GMAIL_TOKEN).exists()


def delivery_configured() -> bool:
    return _gmail_ready() or bool(_setting("HAP_SMTP_USER") and _setting("HAP_SMTP_PASSWORD"))


def gmail_login() -> Path:
    """One-time sign-in as the sending mailbox; the token only allows sending mail (gmail.send)."""
    from services.drive_sync_service import login

    return login(scope=GMAIL_SCOPE, token_name=GMAIL_TOKEN, purpose="Gmail (send only)", client_file="gmail_client_secret.json")


def _prepare(eml_path: Path | str, recipient: str, sender: str | None):
    msg = BytesParser(policy=policy.SMTP).parse(open(eml_path, "rb"))
    for header in ("X-Unsent", "To", "From", "Cc", "Bcc"):
        del msg[header]
    msg["To"] = recipient
    if sender:
        msg["From"] = sender
    return msg


def _send_gmail_api(eml_path: Path | str, recipient: str) -> dict:
    import base64

    import httpx
    from services.drive_sync_service import _access_token, _tls, auth_dir

    msg = _prepare(eml_path, recipient, _setting("HAP_EMAIL_FROM"))      # Gmail fills in the signed-in mailbox as the sender
    with httpx.Client(timeout=60, verify=_tls()) as client:
        token = _access_token(auth_dir(), client, GMAIL_TOKEN)
        resp = client.post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                           headers={"Authorization": f"Bearer {token}"},
                           json={"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()})
    if resp.status_code != 200:
        return {"sent": False, "to": recipient, "error": f"Gmail API {resp.status_code}: {resp.text[:300]}"}
    return {"sent": True, "to": recipient, "error": None}


def send_analysis_email(eml_path: Path | str, *, to: str | None = None) -> dict:
    """Send the saved .eml as is (attachments included). Returns {"sent": bool, "to": ..., "error": ...}; never raises."""
    recipient = to or _setting("HAP_EMAIL_TO", DEFAULT_TO)
    try:
        if _gmail_ready():
            return _send_gmail_api(eml_path, recipient)
        user, password = _setting("HAP_SMTP_USER"), _setting("HAP_SMTP_PASSWORD")
        if not (user and password):
            return {"sent": False, "to": recipient,
                    "error": "email not configured: run  python scripts/gmail_login.py  once (or set HAP_SMTP_USER and HAP_SMTP_PASSWORD in backend/.env)"}
        msg = _prepare(eml_path, recipient, _setting("HAP_EMAIL_FROM", user))
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
