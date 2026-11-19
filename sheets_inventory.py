"""Write course rows into a department's "Instructional Digital Resource Inventory - <dept>" Google Sheet.

The spreadsheet is found by name on Google Drive (Drive for desktop's .gsheet files can't be read from
disk). On its "Department Resource Inventory" sheet, a course already listed (same Course Name and
Term) is updated in place, and a new course is added below the last row in use. Archive is never
written (it is ticked by hand), and an empty value never overwrites something already in the sheet,
so a date typed into Date Confirmed stays put. If added rows run past the sheet's table, the table is
extended so they get its dropdowns and checkboxes.

Setup (once): in the Google Cloud project that holds secrets/credentials.json (see gmail_source.py),
enable the Google Sheets API and the Google Drive API. The first time the inventory is generated, a
browser tab asks you to sign in and allow access; the token is saved to secrets/sheets_token.json.
"""

from __future__ import annotations

from datetime import date

from gmail_source import CLIENT_FILE, SECRETS, libraries_installed

TOKEN_FILE = SECRETS / "sheets_token.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive.metadata.readonly"]  # to find the spreadsheet by name
SHEET = "Department Resource Inventory"
NAME = "Instructional Digital Resource Inventory - {dept}"

# Field -> how its header starts (lower case). Headers carry notes after the name, e.g.
# "Archive (checking box auto adds to to-do list)", so only the start is compared.
FIELDS = {
    "course": "course name",
    "term": "term",
    "instructor": "instructor name",
    "priority": "priority tracking",
    "archive": "archive",
    "needs_review": "needs review",
    "confirmed": "accessibility confirmed",
    "date": "date confirmed",
}


class SheetsError(Exception):
    pass


def _text(v) -> str:
    return "" if v is None else str(v).strip()


def _col(n: int) -> str:
    """1 -> A, 27 -> AA."""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


# --------------------------------------------------------------------------- merge (no Google calls)
def plan(values: list[list], records: list[dict]) -> tuple[list[tuple[int, int, object]], int, int, int]:
    """Where each record goes, given the sheet's current values (rows of cells, from A1).

    Returns ([(row, column, value), ...], updated, added, last row in use); rows and columns count from 1.
    """
    head, cols = None, {}
    for i, row in enumerate(values[:10], 1):
        found = {}
        for j, v in enumerate(row, 1):
            h = _text(v).lower()
            for field, start in FIELDS.items():
                if field not in found and h.startswith(start):
                    found[field] = j
        if "course" in found and "term" in found:
            head, cols = i, found
            break
    if head is None:
        raise SheetsError(f'no "Course Name" and "Term" header found on the "{SHEET}" sheet')

    def cell(row: list, field: str) -> str:
        c = cols.get(field)
        return _text(row[c - 1]) if c and c <= len(row) else ""

    existing: dict[tuple[str, str], int] = {}
    last = head  # last row with a course, term or instructor in it
    for i, row in enumerate(values[head:], head + 1):
        course, term = cell(row, "course"), cell(row, "term")
        if course or term or cell(row, "instructor"):
            last = i
        if course:
            existing.setdefault((course.lower(), term.lower()), i)

    writes, updated, added = [], 0, 0
    for rec in records:
        key = (_text(rec["course"]).lower(), _text(rec["term"]).lower())
        row = existing.get(key)
        if row:
            updated += 1
        else:
            last += 1
            row = existing[key] = last
            added += 1
        for field, value in rec.items():
            if field != "archive" and field in cols and value is not None and value != "":
                writes.append((row, cols[field], value))
    return writes, updated, added, last


# --------------------------------------------------------------------------- Google
def credentials(interactive: bool = True):
    """Saved credentials, refreshed if needed; otherwise a browser sign-in (when interactive)."""
    if not libraries_installed():
        raise SheetsError("Google libraries aren't installed. Run: .venv\\Scripts\\pip install -r requirements.txt")
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
            raise SheetsError("Google Sheets isn't connected.")
        if not CLIENT_FILE.is_file():
            raise SheetsError(f"Missing OAuth client file: {CLIENT_FILE}. See the Gmail setup steps in the README.")
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True, success_message=(
            "Google Sheets connected. You can close this tab and return to the app."))
    SECRETS.mkdir(exist_ok=True)
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return creds


class Inventory:
    """One sign-in, reused for every department in a run."""

    def __init__(self):
        from googleapiclient.discovery import build
        creds = credentials()
        self.sheets = build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets()
        self.drive = build("drive", "v3", credentials=creds, cache_discovery=False).files()

    def find(self, dept: str) -> str:
        """The spreadsheet ID for a department, looked up by its exact name on Drive (shared drives included)."""
        name = NAME.format(dept=dept)
        q = (f"name = '{name}' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false")
        files = self.drive.list(q=q, corpora="allDrives", includeItemsFromAllDrives=True, supportsAllDrives=True,
                                fields="files(id,name)", pageSize=10).execute().get("files", [])
        if not files:
            raise SheetsError(f'no Google Sheet named "{name}" that you can open')
        if len(files) > 1:
            raise SheetsError(f'{len(files)} Google Sheets are named "{name}"; rename or remove the extras')
        return files[0]["id"]

    def update(self, dept: str, records: list[dict]) -> tuple[int, int]:
        """Update or add each record ({field: value}) in the department's sheet. Returns (updated, added)."""
        sid = self.find(dept)
        meta = self.sheets.get(spreadsheetId=sid,
                               fields="sheets(properties(sheetId,title),tables(tableId,range))").execute()
        sheet = next((s for s in meta.get("sheets", []) if s["properties"]["title"] == SHEET), None)
        if sheet is None:
            raise SheetsError(f'no "{SHEET}" sheet in "{NAME.format(dept=dept)}"')
        values = self.sheets.values().get(spreadsheetId=sid, range=f"'{SHEET}'!A1:Z",
                                          valueRenderOption="FORMATTED_VALUE").execute().get("values", [])
        writes, updated, added, last = plan(values, records)

        # Extend the table first, so added rows get its column types (dropdown, checkboxes).
        for t in sheet.get("tables", []):
            r = t["range"]
            if r.get("endRowIndex", 0) < last:
                self.sheets.batchUpdate(spreadsheetId=sid, body={"requests": [{"updateTable": {
                    "table": {"tableId": t["tableId"], "range": {**r, "endRowIndex": last}},
                    "fields": "range"}}]}).execute()

        # Dates go in as typed text (USER_ENTERED) so Sheets stores a real date; everything else as is (RAW),
        # so a course name like "EE 430/530" is never read as a date or a formula.
        for mode, pick in (("RAW", lambda v: not isinstance(v, date)), ("USER_ENTERED", lambda v: isinstance(v, date))):
            data = [{"range": f"'{SHEET}'!{_col(c)}{r}", "values": [[v.isoformat() if isinstance(v, date) else v]]}
                    for r, c, v in writes if pick(v)]
            if data:
                self.sheets.values().batchUpdate(spreadsheetId=sid, body={"valueInputOption": mode,
                                                                          "data": data}).execute()
        return updated, added
