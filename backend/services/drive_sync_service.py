"""Google Drive access for the daily batch: list the analyst's workbooks and download the ones an analysis needs into the HAP work folder.

One-time sign-in (you, in your browser; HAP never sees the password):  python scripts/drive_login.py
After that the batch downloads what it needs by file name, so nothing has to be copied into the work folder by hand.

Read-only: the token only has the ``drive.readonly`` scope. Uses httpx (already a dependency) and the Drive v3 REST API.
Files are cached: a file is downloaded again only when its Drive checksum / modified time changed.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import ssl

import httpx


def _tls():
    """Trust the operating system's certificate store (Windows/macOS), not only httpx's bundled list.
    Antivirus HTTPS scanning (for example Avast) re-signs traffic with a root that only the OS store knows."""
    return ssl.create_default_context()


SCOPE = "https://www.googleapis.com/auth/drive.readonly"
DRIVE_API = "https://www.googleapis.com/drive/v3"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
GSHEET_MIME = "application/vnd.google-apps.spreadsheet"
FOLDER_MIME = "application/vnd.google-apps.folder"
CACHE_FILE = ".drive_cache.json"

_BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_AUTH_DIR = _BACKEND / "storage" / "drive"


class DriveError(RuntimeError):
    pass


def auth_dir() -> Path:
    raw = os.environ.get("HAP_DRIVE_AUTH_DIR", "").strip()
    return Path(raw) if raw else DEFAULT_AUTH_DIR


def folder_id_from(text: str | None) -> str | None:
    """A Drive folder id from an id or a folder link (https://drive.google.com/drive/folders/<id>?...)."""
    if not text:
        return None
    text = text.strip()
    m = re.search(r"/folders/([A-Za-z0-9_\-]+)", text)
    if m:
        return m.group(1)
    return text if re.fullmatch(r"[A-Za-z0-9_\-]{10,}", text) else None


@dataclass
class DriveFile:
    id: str
    name: str            # the name to save under (a Google Sheet gets ".xlsx")
    modified: str
    size: int | None
    md5: str | None
    mime: str

    @property
    def signature(self) -> str:
        return self.md5 or self.modified


# --------------------------------------------------------------------------- sign-in (OAuth, desktop flow with PKCE)

def _client_config(directory: Path) -> dict:
    path = Path(os.environ.get("HAP_DRIVE_CLIENT_SECRET", "").strip() or directory / "client_secret.json")
    if not path.exists():
        raise DriveError(
            f"Google OAuth client file not found: {path}. Create a Desktop-app OAuth client in Google Cloud Console "
            "(Drive API enabled), download its JSON and save it there."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    cfg = data.get("installed") or data.get("web")
    if not cfg or not cfg.get("client_id"):
        raise DriveError(f"{path} is not an OAuth client file (no 'installed' section)")
    return cfg


def login(directory: Path | None = None, *, open_browser: bool = True, scope: str = SCOPE, token_name: str = "token.json",
          purpose: str = "Google Drive (read-only)") -> Path:
    """Open the Google consent page, catch the redirect on localhost, store a refresh token. Returns the token file."""
    directory = Path(directory or auth_dir())
    directory.mkdir(parents=True, exist_ok=True)
    cfg = _client_config(directory)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    result: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = parse_qs(urlparse(self.path).query)
            if q.get("state", [""])[0] == state and "code" in q:
                result["code"] = q["code"][0]
                body = f"HAP is connected to {purpose}. You can close this tab.".encode()
            else:
                result["error"] = q.get("error", ["unexpected response"])[0]
                body = b"Google sign-in was not completed. You can close this tab and try again."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # silence
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    redirect = f"http://127.0.0.1:{server.server_port}"
    url = cfg.get("auth_uri", "https://accounts.google.com/o/oauth2/v2/auth") + "?" + urlencode({
        "client_id": cfg["client_id"], "redirect_uri": redirect, "response_type": "code", "scope": scope,
        "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    print("Sign in with the Google account that owns the files:\n" + url)
    if open_browser:
        webbrowser.open(url)
    thread.join(timeout=300)
    server.server_close()
    if "code" not in result:
        raise DriveError(f"Google sign-in failed: {result.get('error', 'timed out')}")
    resp = httpx.post(cfg.get("token_uri", "https://oauth2.googleapis.com/token"), data={
        "client_id": cfg["client_id"], "client_secret": cfg.get("client_secret", ""), "code": result["code"],
        "code_verifier": verifier, "grant_type": "authorization_code", "redirect_uri": redirect,
    }, timeout=30, verify=_tls())
    token = resp.json()
    if resp.status_code != 200 or "refresh_token" not in token:
        raise DriveError(f"Google did not return a refresh token: {token.get('error_description') or token.get('error') or resp.text}")
    path = directory / token_name
    path.write_text(json.dumps({"refresh_token": token["refresh_token"], "client_id": cfg["client_id"],
                                "client_secret": cfg.get("client_secret", ""),
                                "token_uri": cfg.get("token_uri", "https://oauth2.googleapis.com/token")}), encoding="utf-8")
    return path


def _access_token(directory: Path, client: httpx.Client, token_name: str = "token.json") -> str:
    path = directory / token_name
    if not path.exists():
        raise DriveError("Not signed in to Google Drive yet: run  python scripts/drive_login.py  once")
    t = json.loads(path.read_text(encoding="utf-8"))
    resp = client.post(t["token_uri"], data={"client_id": t["client_id"], "client_secret": t["client_secret"],
                                              "refresh_token": t["refresh_token"], "grant_type": "refresh_token"})
    if resp.status_code != 200:
        raise DriveError(f"Google Drive sign-in expired or was revoked ({resp.json().get('error', resp.status_code)}): run scripts/drive_login.py again")
    return resp.json()["access_token"]


# --------------------------------------------------------------------------- listing and downloading

class DriveClient:
    def __init__(self, directory: Path | None = None, *, client: httpx.Client | None = None) -> None:
        self.directory = Path(directory or auth_dir())
        self._http = client or httpx.Client(timeout=120, verify=_tls())
        self._token: str | None = None

    def _headers(self) -> dict[str, str]:
        if self._token is None:
            self._token = _access_token(self.directory, self._http)
        return {"Authorization": f"Bearer {self._token}"}

    def _get(self, url: str, **kw) -> httpx.Response:
        resp = self._http.get(url, headers=self._headers(), **kw)
        if resp.status_code >= 400:
            raise DriveError(f"Google Drive request failed ({resp.status_code}): {resp.text[:200]}")
        return resp

    def _list(self, q: str) -> list[dict]:
        out, token = [], None
        while True:
            params = {"q": q, "pageSize": 1000, "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
                      "fields": "nextPageToken, files(id,name,mimeType,modifiedTime,size,md5Checksum)"}
            if token:
                params["pageToken"] = token
            body = self._get(f"{DRIVE_API}/files", params=params).json()
            out += body.get("files", [])
            token = body.get("nextPageToken")
            if not token:
                return out

    def list_spreadsheets(self, folder_id: str, *, max_folders: int = 5000, batch: int = 40) -> list[DriveFile]:
        """Every .xlsx and Google Sheet in the folder and its subfolders. For a name used twice the newest copy wins.

        Subfolders are listed in batches (one query asks for the children of up to ``batch`` folders), so hundreds of company folders
        take a handful of requests instead of one each."""
        files: dict[str, DriveFile] = {}
        pending, seen = [folder_id], {folder_id}
        while pending:
            group, pending = pending[:batch], pending[batch:]
            parents = " or ".join(f"'{fid}' in parents" for fid in group)
            for item in self._list(f"({parents}) and trashed = false"):
                mime = item["mimeType"]
                if mime == FOLDER_MIME:
                    if item["id"] not in seen and len(seen) < max_folders:
                        seen.add(item["id"])
                        pending.append(item["id"])
                elif mime in (XLSX_MIME, GSHEET_MIME):
                    name = item["name"] if item["name"].lower().endswith(".xlsx") else item["name"] + ".xlsx"
                    f = DriveFile(item["id"], name, item.get("modifiedTime", ""), int(item["size"]) if item.get("size") else None,
                                  item.get("md5Checksum"), mime)
                    if name not in files or f.modified > files[name].modified:
                        files[name] = f
        return sorted(files.values(), key=lambda f: f.name.lower())

    def download(self, f: DriveFile, target: Path) -> None:
        if f.mime == GSHEET_MIME:
            resp = self._get(f"{DRIVE_API}/files/{f.id}/export", params={"mimeType": XLSX_MIME})
        else:
            resp = self._get(f"{DRIVE_API}/files/{f.id}", params={"alt": "media", "supportsAllDrives": "true"})
        if resp.content[:2] != b"PK":
            raise DriveError(f"{f.name}: Drive did not return an .xlsx file")
        tmp = target.with_name(target.name + ".part")
        tmp.write_bytes(resp.content)
        tmp.replace(target)


def _drive_time(text: str) -> float:
    from datetime import datetime

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def sync_files(client: DriveClient, files: list[DriveFile], work: Path, refresh_if_newer: set[str] | None = None) -> dict[str, list[str]]:
    """Download the files into the work folder. Returns {"downloaded": [...], "cached": [...], "kept_local": [...]}.

    A file already in the folder that HAP did not download itself is left alone (it may be a hand-edited copy) and reported as kept_local,
    except the names in ``refresh_if_newer`` (the daily summary sheet): a local copy older than the Drive version is replaced by it."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    cache_path = work / CACHE_FILE
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    report: dict[str, list[str]] = {"downloaded": [], "cached": [], "kept_local": []}
    for f in files:
        target = work / f.name
        entry = cache.get(f.name)
        if target.exists() and entry is None:
            if f.name in (refresh_if_newer or set()) and _drive_time(f.modified) > target.stat().st_mtime:
                pass                                  # Drive has a newer version of a sheet that now lives there: take it
            else:
                report["kept_local"].append(f.name)
                continue
        if target.exists() and entry and entry.get("signature") == f.signature:
            report["cached"].append(f.name)
            continue
        client.download(f, target)
        cache[f.name] = {"id": f.id, "signature": f.signature}
        report["downloaded"].append(f.name)
    cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    return report
