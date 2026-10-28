"""
Timestamped course-report snapshots on disk.

Layout:
    <root>/<course name>/<YYYY-MM-DD_HHMMSS>.json

Each file is an unmodified course-report export; the file name records when it was
received (email date, or upload time). A loose export dropped straight into <root>,
e.g. "course-report (Power Systems I 001 Fall 2026).json", is filed into its course
folder by file_loose(), stamped with the file's modified time.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import accessibility_report as ar

STAMP_FORMAT = "%Y-%m-%d_%H%M%S"
STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}$")


@dataclass(frozen=True)
class Snapshot:
    course: str
    path: Path
    taken: datetime

    @property
    def id(self) -> str:
        return self.path.stem


def safe_name(name: str) -> str:
    """A course name usable as a folder name on Windows and elsewhere."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name).strip(" .")
    return name or "Unnamed course"


def course_dir(root: Path, course: str) -> Path | None:
    """The folder for an existing course, or None if the name is unknown or escapes root."""
    path = (root / course).resolve()
    if path.parent != root.resolve() or not path.is_dir():
        return None
    return path


def snapshots(root: Path, course: str) -> list[Snapshot]:
    """Snapshots for one course, oldest first."""
    folder = course_dir(root, course)
    if folder is None:
        return []
    out = [Snapshot(folder.name, p, datetime.strptime(p.stem, STAMP_FORMAT))
           for p in folder.glob("*.json") if STAMP_RE.match(p.stem)]
    return sorted(out, key=lambda s: s.taken)


def courses(root: Path) -> dict[str, list[Snapshot]]:
    """{course name: snapshots oldest first} for every course folder with at least one snapshot."""
    found = {d.name: snapshots(root, d.name) for d in sorted(root.iterdir()) if d.is_dir()}
    return {name: snaps for name, snaps in found.items() if snaps}


def save(root: Path, course: str, data: dict, taken: datetime) -> tuple[Path, bool]:
    """Store a snapshot. Returns (path, created); an identical snapshot at the same time is not duplicated."""
    folder = root / safe_name(course)
    folder.mkdir(parents=True, exist_ok=True)
    taken = taken.replace(microsecond=0)
    text = json.dumps(data, ensure_ascii=False)
    while True:
        path = folder / f"{taken.strftime(STAMP_FORMAT)}.json"
        if not path.exists():
            path.write_text(text, encoding="utf-8")
            return path, True
        if json.loads(path.read_text(encoding="utf-8")) == data:
            return path, False
        taken += timedelta(seconds=1)


def file_loose(root: Path) -> list[Path]:
    """Move loose exports in root into their course folders. Returns the new paths."""
    moved = []
    for path in sorted(root.glob("*.json")):
        try:
            data = ar.load(path)
        except (OSError, ValueError):
            continue  # leave unreadable files where they are; the app lists them
        taken = datetime.fromtimestamp(path.stat().st_mtime)
        new_path, _ = save(root, ar.course_from_filename(path), data, taken)
        path.unlink()
        moved.append(new_path)
    return moved
