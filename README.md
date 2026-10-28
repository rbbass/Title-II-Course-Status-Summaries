# Title II Course Status Summaries

Turns course-report JSON exports into readable accessibility summaries — as a local web app or as Markdown
files — and tracks how each course changes from report to report.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Web app

```powershell
.venv\Scripts\python app.py            # then open the address it prints (default http://127.0.0.1:5077)
.venv\Scripts\python app.py --debug    # auto-reload while developing
```

- **All courses** — each course's latest report, with the change since its previous report. Sortable.
- **Course page** — pick any report received for the course. Shows changes since the previous report, a
  history chart and table across all reports, the monthly score trend, where-to-start priorities, file
  types, and severe/major/minor issue tables. Download any report as Markdown, or print it.
- **Email** — pull reports from a Gmail inbox (below).
- **Add reports by hand** — upload exports on the home page, or drop them into `CourseReports/`; they're
  filed into their course's history automatically.

The server listens on `127.0.0.1` only.

## Importing reports from Gmail

One-time setup (details are on the app's Email page):

1. In [Google Cloud Console](https://console.cloud.google.com/), enable the **Gmail API**, configure the
   OAuth consent screen, and create an **OAuth client ID** of type **Desktop app**.
2. Save the downloaded JSON as `secrets/credentials.json`.
3. In the app, open **Email**, set the sender and/or subject the reports arrive with, and click
   **Connect Gmail**. Sign in and allow read-only access.

Then click **Check email** whenever new reports may have arrived. Every `.json` attachment on a matching
message is stored as a snapshot stamped with the time the email arrived. Messages already processed are
skipped, and the same report is never stored twice.

`secrets/` (OAuth client and token) and `mail_settings.json` are git-ignored — this repo is public.

## How reports are stored

```
CourseReports/
  Power Systems I 001 Fall 2026/
    2026-10-28_102842.json      ← unmodified export, named by when it was received
    2026-11-30_091500.json
```

The course name comes from the export's file name, e.g. `course-report (Power Systems I 001 Fall 2026).json`.

## Command line

```powershell
python accessibility_report.py "CourseReports\Power Systems I 001 Fall 2026\*.json" --out-dir reports
```

Writes `<course>.md` plus a `<course>-trend.png` chart (needs matplotlib) per export.

## Layout

| File | Purpose |
| --- | --- |
| `accessibility_report.py` | Parsing and analysis (`summarize()`), Markdown output, CLI |
| `report_store.py` | Timestamped snapshots per course |
| `gmail_source.py` | Gmail sign-in and attachment import |
| `app.py` | Flask app, SVG charts |
| `templates/`, `static/` | Pages and styles |
| `CourseReports/` | Stored reports |
