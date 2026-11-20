"""One-time Google Drive sign-in for HAP (read-only).

Before the first run, in Google Cloud Console: enable the Google Drive API, create an OAuth client of type "Desktop app", download its JSON
and save it as backend/storage/drive/client_secret.json (or point HAP_DRIVE_CLIENT_SECRET at it). Then:

    python scripts/drive_login.py

A browser tab opens; sign in with the Google account that owns the files and allow read-only access. The password is typed into Google's
own page and never reaches HAP. Afterwards run_batch.py downloads files from your Drive folder:

    python scripts/run_batch.py WWD:new_company --drive-folder <folder link or id>      (or set HAP_DRIVE_FOLDER_ID)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.drive_sync_service import DriveError, login  # noqa: E402

if __name__ == "__main__":
    try:
        print("Saved", login())
    except DriveError as exc:
        raise SystemExit(f"Drive sign-in failed: {exc}")
