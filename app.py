#!/usr/bin/env python3
"""
Local web app for browsing course-report JSON exports over time.

Usage:
    python app.py                         # serves http://127.0.0.1:5077 (or the next free port)
    python app.py --port 8080 --debug
    python app.py --reports-dir path/to/exports

Reports live in CourseReports/<course>/<timestamp>.json (see report_store.py). They arrive
from Gmail (see gmail_source.py), from the upload form, or by dropping an export into
CourseReports/, where it is filed automatically.
"""

from __future__ import annotations

import argparse
import math
import os
import socket
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, abort, flash, redirect, render_template, request, url_for
from markupsafe import Markup, escape

import accessibility_report as ar
import gmail_source
import report_store

app = Flask(__name__)
app.config["REPORTS_DIR"] = Path(__file__).parent / "CourseReports"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.secret_key = os.urandom(16)

app.jinja_env.filters["score"] = ar.fmt_score
app.jinja_env.filters["num"] = lambda n: f"{n:,}"
app.jinja_env.filters["when"] = lambda t: f"{t:%b} {t.day}, {t.year}, {t:%I:%M %p}".replace(" 0", " ")
app.jinja_env.filters["day"] = lambda t: f"{t:%b} {t.day}, {t.year}"

SORTS = {
    "course": (lambda c: c["course"].lower(), False),
    "overall": (lambda c: c["s"]["overall"] if c["s"]["overall"] is not None else -1, False),
    "change": (lambda c: c["changes"]["overall"] if c["changes"] else 0, False),
    "files": (lambda c: c["s"]["processed"], True),
    "remediated": (lambda c: c["s"]["remediated"] / c["s"]["processed"] if c["s"]["processed"] else 0, False),
    "severe": (lambda c: c["s"]["severities"][0]["total"], True),
    "updated": (lambda c: c["snap"].taken, True),
}


# --------------------------------------------------------------------------- data

def reports_dir() -> Path:
    return Path(app.config["REPORTS_DIR"])


def load_snapshot(snap: report_store.Snapshot) -> dict:
    data = ar.load(snap.path)
    return {"snap": snap, "data": data, "s": ar.summarize(data)}


def changes(s: dict, prev: dict | None) -> dict | None:
    """Metric differences between two summaries (s minus prev)."""
    if prev is None:
        return None

    def diff(a, b):
        return None if a is None or b is None else a - b

    return {
        "overall": diff(s["overall"], prev["overall"]),
        "processed": s["processed"] - prev["processed"],
        "remediated": s["remediated"] - prev["remediated"],
        **{sev["name"].lower(): sev["total"] - p["total"] for sev, p in zip(s["severities"], prev["severities"])},
    }


def load_course(course: str) -> list[dict]:
    """Every snapshot of a course, oldest first, or 404."""
    snaps = report_store.snapshots(reports_dir(), course)
    if not snaps:
        abort(404)
    return [load_snapshot(snap) for snap in snaps]


def load_all() -> tuple[list[dict], list[tuple[str, str]]]:
    root = reports_dir()
    report_store.file_loose(root)
    rows, errors = [], [(p.name, "couldn't be read as a course-report export") for p in root.glob("*.json")]
    for course, snaps in report_store.courses(root).items():
        try:
            latest = load_snapshot(snaps[-1])
            prev = load_snapshot(snaps[-2]) if len(snaps) > 1 else None
        except (OSError, ValueError, KeyError, TypeError) as e:
            errors.append((course, str(e)))
            continue
        rows.append({"course": course, "snap": latest["snap"], "s": latest["s"], "count": len(snaps),
                     "prev_snap": prev["snap"] if prev else None,
                     "changes": changes(latest["s"], prev["s"] if prev else None)})
    return rows, errors


# --------------------------------------------------------------------------- charts

def short_month(label: str) -> str:
    """'October 2026' -> 'Oct ’26'."""
    parts = label.split()
    return f"{parts[0][:3]} ’{parts[1][-2:]}" if len(parts) == 2 else label


def trend_headline(s: dict) -> str:
    months, overall = s["months"], s["series"].get("Overall", [])
    if not overall:
        return "No scores recorded yet"
    first, last = overall[0], overall[-1]
    if len(months) == 1:
        return f"Overall score {last:.1f}, {months[-1]['Date']}"
    direction = "rose" if last > first else "slipped" if last < first else "held"
    return f"Overall score {direction} from {first:.1f} to {last:.1f}, {months[0]['Date']} to {months[-1]['Date']}"


def line_chart_svg(uid: str, axis_labels: list[str], point_labels: list[str], series: dict[str, list],
                   title: str, desc: str) -> Markup:
    """Score lines (0–100) with "Overall" highlighted. The page's data table is the text alternative."""
    n = len(axis_labels)
    if not n or not series:
        return Markup("")

    width, height = 760, 320
    left, right, top, bottom = 40, 150, 14, 34
    plot_w, plot_h = width - left - right, height - top - bottom

    def x(i: int) -> float:
        return left + (plot_w * i / (n - 1) if n > 1 else plot_w / 2)

    def y(v: float) -> float:
        return top + plot_h * (1 - v / 100)

    out = [f'<svg class="trend" viewBox="0 0 {width} {height}" role="img" '
           f'aria-labelledby="{uid}-title {uid}-desc">',
           f'<title id="{uid}-title">{escape(title)}</title>',
           f'<desc id="{uid}-desc">{escape(desc)}</desc>']

    for tick in (0, 25, 50, 75, 100):
        out.append(f'<line class="grid" x1="{left}" x2="{left + plot_w}" y1="{y(tick):.1f}" y2="{y(tick):.1f}"/>')
        out.append(f'<text class="axis" x="{left - 8}" y="{y(tick):.1f}" text-anchor="end" '
                   f'dominant-baseline="middle">{tick}</text>')
    step = math.ceil(n / 8)  # keep axis labels from colliding
    for i, text in enumerate(axis_labels):
        if i % step == 0 or i == n - 1:
            out.append(f'<text class="axis" x="{x(i):.1f}" y="{height - 10}" text-anchor="middle">'
                       f'{escape(text)}</text>')

    end_labels = []
    # Draw Overall last so it sits on top.
    for name, values in sorted(series.items(), key=lambda kv: kv[0] == "Overall"):
        pts = [(i, v) for i, v in enumerate(values) if v is not None]
        if not pts:
            continue
        cls = "overall" if name == "Overall" else "other"
        if len(pts) > 1:
            coords = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in pts)
            out.append(f'<polyline class="line {cls}" points="{coords}"/>')
        for i, v in pts:
            out.append(f'<circle class="dot {cls}" cx="{x(i):.1f}" cy="{y(v):.1f}" r="{5 if cls == "overall" else 3.5}">'
                       f'<title>{escape(name)}, {escape(point_labels[i])}: {v:.1f}</title></circle>')
        last_i, last_v = pts[-1]
        end_labels.append((y(last_v), x(last_i), name, last_v, cls))

    # End-of-line labels, nudged apart so they don't collide.
    end_labels.sort()
    min_gap, prev = 15, None
    for ly, lx, name, v, cls in end_labels:
        ty = ly if prev is None else max(ly, prev + min_gap)
        if abs(ty - ly) > 2:
            out.append(f'<line class="leader" x1="{lx + 6:.1f}" y1="{ly:.1f}" x2="{lx + 14:.1f}" y2="{ty:.1f}"/>')
        out.append(f'<text class="end-label {cls}" x="{lx + 16:.1f}" y="{ty:.1f}" dominant-baseline="middle">'
                   f'{escape(name)} {v:.1f}</text>')
        prev = ty

    out.append("</svg>")
    return Markup("".join(out))


def trend_svg(s: dict) -> Markup:
    labels = [m["Date"] for m in s["months"]]
    return line_chart_svg("trend", [short_month(m) for m in labels], labels, s["series"], trend_headline(s),
                          "Cumulative accessibility score by format, 0 to 100, from this report. "
                          "The same data is in the table that follows the chart.")


def history_series(reports: list[dict]) -> dict[str, list]:
    """{"Overall": [...], format: [...]} — each report's overall score and latest per-format scores."""
    series: dict[str, list] = {"Overall": [r["s"]["overall"] for r in reports]}
    for i, r in enumerate(reports):
        latest = r["s"]["months"][-1] if r["s"]["months"] else {}
        for name, value in latest.items():
            if name in ("Date", "Overall") or value is None:
                continue
            series.setdefault(name, [None] * len(reports))[i] = value
    return series


def history_svg(reports: list[dict], series: dict[str, list]) -> Markup:
    first, last = series["Overall"][0], series["Overall"][-1]
    title = (f"Overall score went from {ar.fmt_score(first)} to {ar.fmt_score(last)} across "
             f"{len(reports)} reports")
    taken = [r["snap"].taken for r in reports]
    return line_chart_svg("history", [f"{t:%b} {t.day}" for t in taken], [f"{t:%b} {t.day}, {t.year}" for t in taken],
                          series, title, "Overall and per-format score, 0 to 100, in each report received. "
                          "The same data is in the table that follows the chart.")


# --------------------------------------------------------------------------- routes: reports

@app.get("/")
def index():
    courses, errors = load_all()
    sort = request.args.get("sort", "overall")
    key, reverse = SORTS.get(sort, SORTS["overall"])
    if request.args.get("dir") == "desc":
        reverse = True
    elif request.args.get("dir") == "asc":
        reverse = False
    courses.sort(key=key, reverse=reverse)
    return render_template("index.html", courses=courses, errors=errors, sort=sort,
                           direction="desc" if reverse else "asc", reports_dir=reports_dir(),
                           mail=gmail_source.status(), settings=gmail_source.load_settings())


@app.post("/upload")
def upload():
    saved, rejected = [], []
    now = datetime.now()
    for f in request.files.getlist("reports"):
        if not f or not f.filename:
            continue
        try:
            data = ar.parse_export(f.read())
        except ValueError as e:
            rejected.append(f"{f.filename}: {e}")
            continue
        course = ar.course_from_filename(Path(f.filename.replace("\\", "/")))
        path, created = report_store.save(reports_dir(), course, data, now)
        saved.append(path.parent.name + ("" if created else " (already stored)"))

    if saved:
        flash(f"Added {len(saved)} report{'s' if len(saved) != 1 else ''}: {', '.join(saved)}", "ok")
    for msg in rejected:
        flash(f"Not added — {msg}", "error")
    if not saved and not rejected:
        flash("Choose one or more .json exports to upload.", "error")
    return redirect(url_for("index"))


@app.get("/course/<course>")
def course(course: str):
    reports = load_course(course)
    ids = [r["snap"].id for r in reports]
    at = request.args.get("at", ids[-1])
    if at not in ids:
        abort(404)
    i = ids.index(at)
    current, prev = reports[i], reports[i - 1] if i else None
    s = current["s"]

    series = history_series(reports) if len(reports) > 1 else None
    return render_template(
        "report.html", course=reports[0]["snap"].course, current=current, prev=prev, s=s,
        changes=changes(s, prev["s"] if prev else None), reports=reports, is_latest=i == len(reports) - 1,
        chart=trend_svg(s), headline=trend_headline(s),
        series_rows=sorted(s["series"].items(), key=lambda kv: kv[0] != "Overall"),
        history_chart=history_svg(reports, series) if series else None,
        history_rows=sorted(series.items(), key=lambda kv: kv[0] != "Overall") if series else None)


@app.get("/course/<course>/markdown")
def course_markdown(course: str):
    reports = load_course(course)
    at = request.args.get("at")
    r = next((r for r in reports if r["snap"].id == at), reports[-1]) if at else reports[-1]
    snap = r["snap"]
    md = ar.build_report(r["data"], snap.course, f"{snap.course}/{snap.path.name}", None)
    filename = f"{ar.slugify(snap.course)}-{snap.taken:%Y-%m-%d}.md"
    return Response(md, mimetype="text/markdown", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# --------------------------------------------------------------------------- routes: email

@app.get("/email")
def email():
    settings = gmail_source.load_settings()
    return render_template("email.html", mail=gmail_source.status(), settings=settings,
                           query=gmail_source.search_query(settings),
                           client_file=gmail_source.CLIENT_FILE, token_file=gmail_source.TOKEN_FILE)


@app.post("/email/settings")
def email_settings():
    settings = gmail_source.load_settings()
    sender, subject = request.form.get("sender", "").strip(), request.form.get("subject", "").strip()
    if (sender, subject) != (settings["sender"], settings["subject"]):
        # New criteria may match messages skipped before, so look at everything again.
        settings["seen"] = []
    settings.update(sender=sender, subject=subject)
    gmail_source.save_settings(settings)
    flash("Email settings saved.", "ok")
    return redirect(url_for("email"))


@app.post("/email/connect")
def email_connect():
    try:
        address = gmail_source.connect()
        flash(f"Connected to Gmail as {address}.", "ok")
    except Exception as e:  # sign-in can fail in many library-specific ways; show them all
        flash(f"Couldn't connect to Gmail — {e}", "error")
    return redirect(url_for("email"))


@app.post("/email/disconnect")
def email_disconnect():
    gmail_source.disconnect()
    flash("Disconnected from Gmail. The saved sign-in was deleted.", "ok")
    return redirect(url_for("email"))


@app.post("/email/check")
def email_check():
    try:
        result = gmail_source.check(reports_dir())
    except gmail_source.MailError as e:
        flash(str(e), "error")
        return redirect(url_for("email"))
    except Exception as e:  # network or Google API errors
        flash(f"Couldn't check email — {e}", "error")
        return redirect(request.form.get("next") or url_for("index"))

    if result.saved:
        flash(f"Added {len(result.saved)} report{'s' if len(result.saved) != 1 else ''}: "
              + "; ".join(result.saved), "ok")
    elif not result.problems:
        flash(f"No new reports ({result.messages} new matching email{'s' if result.messages != 1 else ''}"
              + (f", {result.duplicates} already stored" if result.duplicates else "") + ").", "ok")
    for msg in result.problems:
        flash(f"Skipped — {msg}", "error")
    return redirect(request.form.get("next") or url_for("index"))


@app.errorhandler(404)
def not_found(_):
    return render_template("404.html"), 404


# --------------------------------------------------------------------------- main

DEFAULT_PORT = 5077


def port_free(port: int) -> bool:
    # Exclusive bind, so a port another app holds on Windows reads as taken.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def main() -> None:
    p = argparse.ArgumentParser(description="Serve course accessibility reports locally.")
    p.add_argument("--reports-dir", type=Path, default=app.config["REPORTS_DIR"],
                   help="folder of course-report snapshots (default: CourseReports/)")
    p.add_argument("--port", type=int, help=f"port to serve on (default: first free from {DEFAULT_PORT})")
    p.add_argument("--debug", action="store_true", help="auto-reload on code changes")
    args = p.parse_args()

    args.reports_dir.mkdir(parents=True, exist_ok=True)
    app.config["REPORTS_DIR"] = args.reports_dir

    # The debug reloader re-runs this in a child process; reuse the port the parent chose.
    port = int(os.environ.get("REPORTS_APP_PORT", 0)) or args.port
    if port is None:
        port = next((p for p in range(DEFAULT_PORT, DEFAULT_PORT + 20) if port_free(p)), None)
        if port is None:
            raise SystemExit(f"No free port in {DEFAULT_PORT}–{DEFAULT_PORT + 19}; pass --port.")
    elif "REPORTS_APP_PORT" not in os.environ and not port_free(port):
        raise SystemExit(f"Port {port} is already in use; pick another with --port.")
    os.environ["REPORTS_APP_PORT"] = str(port)

    # Bound to localhost only: this is a single-user tool, not a server.
    app.run(host="127.0.0.1", port=port, debug=args.debug)


if __name__ == "__main__":
    main()
