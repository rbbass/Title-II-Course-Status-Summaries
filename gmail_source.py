"""
Fetch course-report JSON attachments from Gmail (read-only).

Setup (once):
  1. In Google Cloud Console, enable the Gmail API and create an OAuth client ID of
     type "Desktop app". Download it as secrets/credentials.json.
  2. In the app, open "Email" and click "Connect Gmail". A browser tab asks you to
     sign in and allow read-only access; the token is saved to secrets/token.json.

Each matching message's JSON attachments are saved as snapshots stamped with the
time Gmail received the message. Processed message IDs are remembered in
mail_settings.json so later checks only look at new mail.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import accessibility_report as ar
import report_store

BASE = Path(__file__).parent
SECRETS = BASE / "secrets"
CLIENT_FILE = SECRETS / "credentials.json"
TOKEN_FILE = SECRETS / "token.json"
SETTINGS_FILE = BASE / "mail_settings.json"

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class MailError(Exception):
    pass


@dataclass
class CheckResult:
    saved: list[str] = field(default_factory=list)       # "course — timestamp"
    duplicates: int = 0
    messages: int = 0
    problems: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- settings

def load_settings() -> dict:
    defaults = {"sender": "", "subject": "", "seen": [], "last_check": None}
    try:
        return defaults | json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaults


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def search_query(settings: dict) -> str:
    """Gmail search for messages with JSON attachments, narrowed by sender and subject."""
    parts = ["has:attachment", "filename:json"]
    if settings.get("sender"):
        parts.append(f"from:({settings['sender']})")
    if settings.get("subject"):
        parts.append(f'subject:"{settings["subject"].replace(chr(34), "")}"')
    return " ".join(parts)


# --------------------------------------------------------------------------- auth

def libraries_installed() -> bool:
    try:
        import google_auth_oauthlib  # noqa: F401
        import googleapiclient  # noqa: F401
    except ImportError:
        return False
    return True


def status() -> dict:
    return {"libraries": libraries_installed(), "client": CLIENT_FILE.is_file(), "token": TOKEN_FILE.is_file()}


def credentials(interactive: bool = False):
    """Saved credentials, refreshed if needed. With interactive=True, run the browser sign-in when missing."""
    if not libraries_installed():
        raise MailError("Gmail libraries aren't installed. Run: .venv\\Scripts\\pip install -r requirements.txt")
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if TOKEN_FILE.is_file():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if creds and not creds.valid and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            creds = None
    if not creds or not creds.valid:
        if not interactive:
            raise MailError("Gmail isn't connected, or the sign-in expired. Connect Gmail on the Email page.")
        if not CLIENT_FILE.is_file():
            raise MailError(f"Missing OAuth client file: {CLIENT_FILE}. See the setup steps on the Email page.")
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True,
                                      success_message="Gmail connected. You can close this tab and return to the app.")
    SECRETS.mkdir(exist_ok=True)
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return creds


def connect() -> str:
    """Sign in (opening a browser tab) and return the connected address."""
    creds = credentials(interactive=True)
    return _service(creds).users().getProfile(userId="me").execute()["emailAddress"]


def disconnect() -> None:
    TOKEN_FILE.unlink(missing_ok=True)


def _service(creds):
    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


# --------------------------------------------------------------------------- fetch

def _attachment_parts(part: dict):
    if part.get("filename", "").lower().endswith(".json"):
        yield part
    for child in part.get("parts", []) or []:
        yield from _attachment_parts(child)


def check(root: Path) -> CheckResult:
    """Import report attachments from messages not seen before."""
    from googleapiclient.errors import HttpError

    settings = load_settings()
    seen = set(settings["seen"])
    service = _service(credentials())
    messages = service.users().messages()
    result = CheckResult()

    try:
        ids, page = [], None
        while True:
            resp = messages.list(userId="me", q=search_query(settings), pageToken=page, maxResults=100).execute()
            ids += [m["id"] for m in resp.get("messages", [])]
            page = resp.get("nextPageToken")
            if not page:
                break

        for msg_id in reversed(ids):  # oldest first
            if msg_id in seen:
                continue
            result.messages += 1
            msg = messages.get(userId="me", id=msg_id, format="full").execute()
            received = datetime.fromtimestamp(int(msg["internalDate"]) / 1000)
            for part in _attachment_parts(msg["payload"]):
                name = part["filename"]
                body = part.get("body", {})
                raw = body.get("data") or messages.attachments().get(
                    userId="me", messageId=msg_id, id=body["attachmentId"]).execute()["data"]
                try:
                    data = ar.parse_export(base64.urlsafe_b64decode(raw))
                except ValueError as e:
                    result.problems.append(f"{name} ({received:%Y-%m-%d}): {e}")
                    continue
                course = ar.course_from_filename(Path(name))
                path, created = report_store.save(root, course, data, received)
                if created:
                    result.saved.append(f"{path.parent.name} — {received:%Y-%m-%d %H:%M}")
                else:
                    result.duplicates += 1
            # A bad attachment won't improve on a re-read, so the message counts as handled either way.
            seen.add(msg_id)
    except HttpError as e:
        result.problems.append(f"Gmail error: {e.reason if hasattr(e, 'reason') else e}")
    finally:
        settings["seen"] = sorted(seen)
        settings["last_check"] = datetime.now().isoformat(timespec="seconds")
        save_settings(settings)
    return result
