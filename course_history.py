"""
Course details from the registrar's Course History report (S0041, an Excel file).

An uploaded report is boiled down to the columns the app uses (subject, course number, term,
section, title, instructor) and saved as course_history.json in the data folder, so everyone
sharing that folder sees the same details.

Courses are matched by title, section and term: a report named "Power Systems I 001 Fall 2026"
matches rows titled "POWER SYSTEMS I", section 001, term 202604. Term codes are YYYYTT, where
YYYY is the calendar year and TT is 01 Winter, 02 Spring, 03 Summer, 04 Fall.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

FILE_NAME = "course_history.json"
SHEET_NAME = "Excel List"
SEASON_CODES = {"Winter": "01", "Spring": "02", "Summer": "03", "Fall": "04"}

# Subject code -> department until changed on the Subjects page (saved as subject_departments.json
# in the data folder). Subjects named like a department map to it unless set otherwise.
SUBJECTS_FILE_NAME = "subject_departments.json"
DEFAULT_SUBJECT_DEPARTMENTS = {"ECE": "ECE", "EE": "ECE"}

COLUMNS = {"subject": "Subject", "course": "Course", "term": "Term", "sec": "Sec", "title": "Title",
           "last": "Instructor_Last_Name", "first": "Instructor_First_Name"}

SECTION_RE = re.compile(r"^(?P<title>.+?)\s+(?P<sec>\d{1,3})$")


class HistoryError(ValueError):
    pass


# --------------------------------------------------------------------------- reading the spreadsheet

def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def parse_xlsx(source) -> list[dict]:
    """Rows of the report as [{subject, course, term, sec, title, last, first}]. source: path or file object."""
    import openpyxl

    try:
        wb = openpyxl.load_workbook(source, read_only=True, data_only=True)
    except Exception as e:  # openpyxl raises several types for files that aren't valid workbooks
        raise HistoryError(f"couldn't be opened as an Excel workbook ({e})") from e
    try:
        ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.worksheets[0]
        rows = ws.iter_rows(values_only=True)
        # A few title lines come first; the header row is the one naming the columns.
        header = next((cells for cells in ([_text(c) for c in row] for row in rows)
                       if "Subject" in cells and "Title" in cells), None)
        if header is None:
            raise HistoryError("has no header row with Subject and Title columns")
        missing = [name for name in COLUMNS.values() if name not in header]
        if missing:
            raise HistoryError(f"is missing column{'s' if len(missing) > 1 else ''} {', '.join(missing)}")
        idx = {key: header.index(name) for key, name in COLUMNS.items()}
        records = []
        for row in rows:
            rec = {key: _text(row[i]) if i < len(row) else "" for key, i in idx.items()}
            if rec["title"] and re.fullmatch(r"\d{6}", rec["term"]):
                records.append(rec)
    finally:
        wb.close()
    if not records:
        raise HistoryError("has no course rows")
    return records


# --------------------------------------------------------------------------- stored copy

_cache: dict[Path, tuple[float, dict]] = {}


def save(data_dir: Path, records: list[dict], source_name: str) -> None:
    doc = {"source": source_name, "uploaded": datetime.now().isoformat(timespec="seconds"), "records": records}
    (data_dir / FILE_NAME).write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")


def load_subjects(data_dir: Path) -> dict[str, str]:
    """{subject: department}; an empty department means none."""
    try:
        return json.loads((data_dir / SUBJECTS_FILE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(DEFAULT_SUBJECT_DEPARTMENTS)


def save_subjects(data_dir: Path, mapping: dict[str, str]) -> None:
    (data_dir / SUBJECTS_FILE_NAME).write_text(json.dumps(dict(sorted(mapping.items())), indent=2) + "\n",
                                               encoding="utf-8")


def subject_counts(history: dict | None) -> dict[str, int]:
    """{subject: number of sections} in the report, alphabetical."""
    counts: dict[str, int] = {}
    for r in history["records"] if history else []:
        if r["subject"]:
            counts[r["subject"].upper()] = counts.get(r["subject"].upper(), 0) + 1
    return dict(sorted(counts.items()))


def load(data_dir: Path) -> dict | None:
    """{source, uploaded, records}, or None before the first upload. Re-read only when the file changes."""
    path = data_dir / FILE_NAME
    try:
        mtime = path.stat().st_mtime
        if path not in _cache or _cache[path][0] != mtime:
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["uploaded"] = datetime.fromisoformat(doc["uploaded"])
            _cache[path] = (mtime, doc)
        return _cache[path][1]
    except (OSError, ValueError, KeyError):
        return None


# --------------------------------------------------------------------------- matching

def _norm(title: str) -> str:
    return " ".join(title.upper().split())


def _same_section(a: str, b: str) -> bool:
    return int(a) == int(b) if a.isdigit() and b.isdigit() else a.upper() == b.upper()


def department(subject: str, mapping: dict[str, str], departments: list[str]) -> str:
    subject = subject.upper()
    if subject in mapping:
        return mapping[subject]
    return subject if subject in departments else ""


def lookup(history: dict | None, name: str, season: str, year: int,
           mapping: dict[str, str], departments: list[str]) -> dict | None:
    """Details for a course named like 'Power Systems I 001' in the given term, or None if not in the report.

    Returns {code: 'EE 430/530', sec: '001', instructors: [{first, last}], dept: 'ECE' or ''}; cross-listed
    rows (same title, section and term) are combined.
    """
    if not history:
        return None
    m = SECTION_RE.match(name)
    title, sec = (m["title"], m["sec"]) if m else (name, None)
    term, title = f"{year}{SEASON_CODES[season]}", _norm(title)
    hits = [r for r in history["records"] if r["term"] == term and _norm(r["title"]) == title
            and (sec is None or _same_section(r["sec"], sec))]
    if not hits:
        return None

    numbers: dict[str, list[str]] = {}
    for r in hits:
        if r["course"] not in numbers.setdefault(r["subject"], []):
            numbers[r["subject"]].append(r["course"])
    instructors = list({(r["first"], r["last"]): None for r in hits if r["last"]})
    depts = {department(r["subject"], mapping, departments) for r in hits} - {""}
    return {"code": " / ".join(f"{s} {'/'.join(n)}" for s, n in numbers.items()),
            "sec": sec or hits[0]["sec"],
            "instructors": [{"first": f, "last": l} for f, l in instructors],
            "dept": depts.pop() if len(depts) == 1 else ""}
