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
.venv\Scripts\python app.py            # then open the address it prints
.venv\Scripts\python app.py --debug    # auto-reload while developing
```

It serves on the first free port from 5077 (so a second copy gets 5078); `--port <n>` picks one, and
`--data-dir <folder>` uses another data folder for that run.

- **All courses** — each course's latest report: course number, term (F26, W27, …), instructor, overall
  score and its change since the previous report, files, remediated, severe issues, latest report date
  and department. Sort by any column.
  - **Dept.** — courses matched in the Course History report take their department from their subject;
    for the rest, choose one here (saved immediately to `course_departments.json`).
  - **Select by Department** and **Select by Academic year and Term** check the matching courses; used
    together they combine (e.g. ECE courses in F26). Academic years run Fall through Summer.
  - **Generate All Reports for All Departments** — for every course, checked or not: a compilation
    report for each department (plus Other for courses with none) and every department's inventory.
  - **Generate Department Compilation Report** — one self-contained HTML file of the checked courses
    (an overview table with totals, then each course's latest report), saved to
    `Department Instructional Digital Resource Reports\Course Accessibility Compilation Reports - <dept>`
    in the data folder, for the department chosen under Select by Department, or `- Other` if none.
    Files are named by date and time and never overwrite one another.
  - **Generate Department Resource Inventory** — writes the checked courses into their departments'
    Google Sheets (see [Department Resource Inventory](#department-resource-inventory)).
- **Course page** — pick any report received for the course. Shows changes since the previous report, a
  history chart and table across all reports, the monthly score trend, where-to-start priorities, file
  types, and severe/major/minor issue tables. A report stored by mistake can be deleted here.
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
number (e.g. EE 347), instructor (shown as R. Bass) and department. A new upload replaces the last one.

A report named "Power Systems I 001 Fall 2026" matches rows titled POWER SYSTEMS I, section 001, term
202604 (YYYYTT: 01 Winter, 02 Spring, 03 Summer, 04 Fall). Punctuation is ignored, so
"Sem_ Intro Research & Training" matches SEM: INTRO RESEARCH & TRAINING, and a name ending in a course
and section, like "Lab For Ece 221 ECE-221L-002", also matches on that subject and number.
Cross-listed rows are combined (EE 430/530), and two sections of a course in one term get their section
number (ECE 221L-001). A matched course's department comes from its subject, mapped on the **Subjects**
page (saved as `subject_departments.json`); a subject named like a department, such as ECE, maps to it
unless set otherwise. Courses not in the spreadsheet keep their name and the Dept. dropdown.

Only the needed columns are kept, in `course_history.json` in the data folder. The `.xlsx` itself is
git-ignored: it names instructors and this repo is public.

## Department Resource Inventory

Each department has a Google Sheet, **Instructional Digital Resource Inventory - &lt;dept&gt;**, found by
name on Google Drive. Courses go on its "Department Resource Inventory" sheet: a course already listed
(same Course Name and Term) is updated, and others are added below the last row, with the sheet's table
extended to cover them. Courses with no department are skipped.

| Column | Value |
| --- | --- |
| Course Name, Term, Instructor Name | e.g. EE 347, F26, R. Bass |
| Priority Tracking | Overall score above 90: Completed; below 50: First: Highest; 50–90 split evenly into Second, Third, Fourth |
| Archive | Never written; it's ticked by hand |
| Needs Review | TRUE when the score is below 80 |
| Accessibility Confirmed | TRUE when the score is 80 or more |
| Date Confirmed | Date of the first report scoring 80 or more |

A course with no files (YuJa reports its score as 0) counts as Completed and confirmed, dated by its
first report with no files. Blank values never overwrite what's in the sheet, so dates typed in by hand
stay. See [Writing to Google Sheets](#writing-to-google-sheets) for the one-time setup.

## Shared data folder

The **data folder** holds everything the app shares between its users:

| In the data folder | What |
| --- | --- |
| `CourseReports/` | Stored reports (see [How reports are stored](#how-reports-are-stored)) |
| `Department Instructional Digital Resource Reports/` | Saved compilation reports, a folder per department |
| `course_departments.json` | Departments chosen in the Dept. column |
| `departments.json` | The department list (Departments page) |
| `subject_departments.json` | Subject → department (Subjects page) |
| `course_history.json` | The needed columns of the last Course History upload |

Choose it on the **Settings** page; the choice is saved on that computer in `app_settings.json`
(git-ignored). Running from source with no choice saved, the project folder is used, and the files
above are git-ignored there.

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
Characters a folder name can't hold, such as `:` and `/`, become `_` ("Finite Element Mod_anlys 001 Fall 2026").

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
| `course_history.py` | Course History (.xlsx) import, course matching, subject → department |
| `gmail_source.py` | Gmail sign-in and attachment import |
| `sheets_inventory.py` | Department Resource Inventory Google Sheets |
| `app.py` | Flask app: pages, departments, compilations, SVG charts |
| `app_settings.py` | App and data folder locations |
| `build.ps1` | Packages the app as a Windows program |
| `templates/`, `static/` | Pages and styles |
| `power-systems-i-001-fall-2026.md` | Sample command-line report |
