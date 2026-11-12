"""
Where the app's files live.

  APP_DIR      this computer's own files: app_settings.json, mail_settings.json, secrets/.
               The project folder, or the folder holding the .exe when packaged.
  BUNDLE_DIR   read-only files shipped with the app: templates/, static/.
  data folder  shared data: CourseReports/ and course_departments.json. Chosen on the Settings
               page and remembered in app_settings.json, so it can be a synced folder such as
               a Google shared drive. Defaults to APP_DIR when running from source.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)  # running as the packaged .exe
APP_DIR = Path(sys.executable).parent if FROZEN else Path(__file__).parent
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
SETTINGS_FILE = APP_DIR / "app_settings.json"

REPORTS_NAME = "CourseReports"
DEPARTMENTS_NAME = "course_departments.json"


def load() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def saved_data_dir() -> Path | None:
    """The data folder chosen on the Settings page; else the project folder when running from source."""
    chosen = load().get("data_dir")
    if chosen:
        return Path(chosen)
    return None if FROZEN else APP_DIR


def normalize_data_dir(text: str) -> Path:
    """Accept either the data folder or its CourseReports folder."""
    path = Path(text.strip().strip('"')).expanduser()
    if path.name.lower() == REPORTS_NAME.lower() and not (path / REPORTS_NAME).is_dir():
        path = path.parent
    return path
