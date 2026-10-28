# Title II Course Status Summaries

Turns course-report JSON exports into readable accessibility summaries — as a local web app or as Markdown files.

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

- **All courses** — every `*.json` in `CourseReports/`, sortable by score, change, files, remediation and severe issues.
- **Course page** — score trend chart, where-to-start priorities, file types, and severe/major/minor issue tables.
  Download the same report as Markdown, or print it.
- **Add reports** — upload exports from the home page or drop them in `CourseReports/`. The course name is
  read from the file name, e.g. `course-report (Power Systems I 001 Fall 2026).json`.

The server listens on `127.0.0.1` only.

## Command line

```powershell
python accessibility_report.py "CourseReports\*.json" --out-dir reports
```

Writes `<course>.md` plus a `<course>-trend.png` chart (needs matplotlib) per export.

## Layout

| File | Purpose |
| --- | --- |
| `accessibility_report.py` | Parsing and analysis (`summarize()`), Markdown output, CLI |
| `app.py` | Flask app, SVG trend chart |
| `templates/`, `static/` | Pages and styles |
| `CourseReports/` | Input exports |
