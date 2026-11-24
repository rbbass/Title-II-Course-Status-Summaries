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
  Assign each course a department in the **Dept.** column; choices save immediately to
  `course_departments.json`.
  Check courses (or the header checkbox for all) and click **Generate Department Compilation Report** to
  save one self-contained HTML file (an overview table with totals, then each selected course's latest
  report) to `Department Instructional Digital Resource Reports\Course Accessibility Compilation Reports -
  <dept>` in the data folder, for the department chosen under Select by Department, or `- Other`.
  **Generate All Reports for All Departments** does both reports for every course, checked or not: a
  compilation per department (plus Other for courses with none) and every department's inventory.
  **Generate Department Resource Inventory** writes the checked courses into each one's department
  Google Sheet, **Instructional Digital Resource Inventory - &lt;dept&gt;** (found by name on Google Drive),
  on its "Department Resource Inventory" sheet. A course already there (same Course Name and Term) is
  updated; others are added below the last row, and the sheet's table is extended to cover them. Archive
  is never written, and blank values never overwrite what's in the sheet. Courses with no department are
  skipped. See [Writing to Google Sheets](#writing-to-google-sheets) for the one-time setup.
- **Course page** — pick any report received for the course. Shows changes since the previous report, a
  history chart and table across all reports, the monthly score trend, where-to-start priorities, file
  types, and severe/major/minor issue tables.
- **Download report (HTML)** — a single self-contained `.html` file of the report you're viewing (styles and
  charts inline, no scripts or external links) to email or share. Its history stops at that report.
  Recipients can open it in any browser, or print it to PDF.
- **Subjects** — upload the Course History report (below) and map each subject to a department.
- **Departments** — the departments with their full names, subjects and course counts; add, rename or
  remove them here (saved as `departments.json` in the data folder). A new department needs its own
  inventory Google Sheet. A new short name carries the department's subjects, chosen course
  departments and compilation folder over; its Google Sheet is renamed by hand. Removing a department
  leaves its subjects and courses with none, and doesn't delete anything on the shared drive.
- **Email** — pull reports from a Gmail inbox (below).
- **Settings** — choose the data folder (below).
- **Add reports by hand** — upload exports on the home page, or drop them into `CourseReports/`; they're
  filed into their course's history automatically.

The server listens on `127.0.0.1` only.

## Course History report

Upload the registrar's **Course History - S0041.xlsx** on the Subjects page to fill in each course's
number (e.g. EE 347), instructor and department. A report named "Power Systems I 001 Fall 2026" matches
rows titled POWER SYSTEMS I, section 001, term 202604; cross-listed rows are combined (EE 430/530).
Matched courses are listed by number, and their department comes from the Subject column, mapped on
the **Subjects** page (saved as `subject_departments.json` in the data folder; ECE and EE → ECE to start).
Courses not in the spreadsheet keep their name and the Dept. dropdown.

Only the needed columns are kept, in `course_history.json` in the data folder. The `.xlsx` itself is
git-ignored: it names instructors and this repo is public.

## Shared data folder

The **data folder** holds `CourseReports/` and `course_departments.json`. Choose it on the **Settings**
page; the choice is saved on that computer in `app_settings.json` (git-ignored). Running from source with
no choice saved, the project folder is used. `--data-dir <folder>` overrides it for one run.

To share reports with colleagues, use a synced folder such as a Google shared drive
(`G:\Shared drives\MCECS ADA Course Reports`) via Google Drive for desktop, and point everyone's copy of
the app at it. Mark the folder **Available offline** so pages load quickly. One person checks email;
everyone sees the new reports once Drive syncs.

## Packaged app for people without Python

```powershell
.\build.ps1
```

Builds `dist\Course Accessibility Reports\` and a `.zip` of it. Recipients unzip it anywhere local (not
inside Google Drive), double-click `Course Accessibility Reports.exe`, and pick the data folder on first
run. A console window shows the app is running; closing it stops the app. Windows may warn about an
unsigned app the first time (**More info → Run anyway**). Rebuild and resend after changing the app.

The packaged app keeps its `app_settings.json`, and any Gmail or Google Sheets sign-in, next to the `.exe`.

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

## Writing to Google Sheets

**Generate Department Resource Inventory** uses the same OAuth client as Gmail (`secrets/credentials.json`).
One-time setup:

1. In the same Google Cloud project, enable the **Google Sheets API** and the **Google Drive API**.
2. Click **Generate Department Resource Inventory**. The first time, a browser tab asks you to sign in
   and allow the app to edit your spreadsheets and see your Drive file names (used only to find each
   department's sheet by name). The sign-in is saved to `secrets/sheets_token.json`; delete that file to
   sign in again.

The account you sign in with needs edit access to the department sheets.

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
| `app_settings.py` | App and data folder locations |
| `build.ps1` | Packages the app as a Windows program |
| `templates/`, `static/` | Pages and styles |
| `CourseReports/` | Stored reports |
