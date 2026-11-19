"""Write course rows into a department's "Instructional Digital Resource Inventory - <dept>.xlsx".

The workbook's "Department Resource Inventory" sheet has a header row (row 2 in the shared template)
and one row per course. A course already in the sheet, matched on Course Name and Term, is updated in
place; a new course is added below the last row in use. Archive is never written (it is ticked by
hand), and an empty value never overwrites something already in the sheet, so a date typed into
Date Confirmed stays put. The sheet's table and the Priority Tracking dropdown are extended to cover
added rows.
"""

from __future__ import annotations

import io
from datetime import date, datetime
from pathlib import Path

import openpyxl
from openpyxl.worksheet.cell_range import CellRange

SHEET = "Department Resource Inventory"

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


def _text(v) -> str:
    return "" if v is None else str(v).strip()


def _header(ws) -> tuple[int, dict[str, int]]:
    """(header row, {field: column}) from the first rows of the sheet."""
    for row in ws.iter_rows(min_row=1, max_row=10):
        cols = {}
        for cell in row:
            h = _text(cell.value).lower()
            for field, start in FIELDS.items():
                if field not in cols and h.startswith(start):
                    cols[field] = cell.column
        if "course" in cols and "term" in cols:
            return row[0].row, cols
    raise ValueError(f'no "Course Name" and "Term" header found on the "{ws.title}" sheet')


def _extend(ws, old_last: int, new_last: int) -> None:
    """Grow the table, and any dropdowns that ended with it, down to new_last."""
    for table in ws.tables.values():
        r = CellRange(table.ref)
        if r.max_row < new_last:
            r.expand(down=new_last - r.max_row)
            table.ref = r.coord
            if table.autoFilter is not None:
                table.autoFilter.ref = r.coord
    for dv in ws.data_validations.dataValidation:
        for r in dv.sqref.ranges:
            if r.max_row == old_last:
                r.expand(down=new_last - old_last)


def update(path: Path, records: list[dict]) -> tuple[int, int]:
    """Update or add each record ({field: value}) in the workbook at path. Returns (updated, added)."""
    wb = openpyxl.load_workbook(path)
    ws = wb[SHEET] if SHEET in wb.sheetnames else wb.worksheets[0]
    head, cols = _header(ws)

    existing: dict[tuple[str, str], int] = {}
    last = head  # last row with a course, term or instructor in it
    for r in range(head + 1, ws.max_row + 1):
        course, term = _text(ws.cell(r, cols["course"]).value), _text(ws.cell(r, cols["term"]).value)
        if course or term or ("instructor" in cols and _text(ws.cell(r, cols["instructor"]).value)):
            last = r
        if course:
            existing.setdefault((course.lower(), term.lower()), r)
    table_last = max((CellRange(t.ref).max_row for t in ws.tables.values()), default=last)

    updated = added = 0
    for rec in records:
        row = existing.get((_text(rec["course"]).lower(), _text(rec["term"]).lower()))
        if row:
            updated += 1
        else:
            last += 1
            row = last
            existing[(_text(rec["course"]).lower(), _text(rec["term"]).lower())] = row
            added += 1
        for field, value in rec.items():
            if field == "archive" or field not in cols or value is None or value == "":
                continue
            cell = ws.cell(row, cols[field])
            cell.value = value
            if isinstance(value, (date, datetime)) and cell.number_format == "General":
                cell.number_format = "m/d/yyyy"

    if last > table_last:
        _extend(ws, table_last, last)
    # Build the whole file in memory first, so a failure never leaves a half-written file on the drive.
    buf = io.BytesIO()
    wb.save(buf)
    path.write_bytes(buf.getvalue())
    return updated, added
