"""One-time Gmail sign-in so HAP can email finished analyses (send-only, no password stored).

Uses the same Google OAuth client file as the Drive login (backend/storage/drive/client_secret.json). In Google Cloud Console enable the
Gmail API for that project, then run:

    python scripts/gmail_login.py

A browser tab opens; sign in as the SENDING mailbox (ai.agent.houda@vlixes.us) and allow "send email on your behalf".
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.drive_sync_service import DriveError  # noqa: E402
from services.email_delivery_service import gmail_login  # noqa: E402

if __name__ == "__main__":
    try:
        print("Saved", gmail_login())
    except DriveError as exc:
        raise SystemExit(f"Gmail sign-in failed: {exc}")
