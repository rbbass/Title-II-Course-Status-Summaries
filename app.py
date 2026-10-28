#!/usr/bin/env python3
"""
Local web app for browsing course-report JSON exports.

Usage:
    python app.py                         # serves http://127.0.0.1:5077 (or the next free port)
    python app.py --port 8080 --debug
    python app.py --reports-dir path/to/exports

Reads every *.json in the reports folder (default: CourseReports/). New exports can be
added by dropping them in that folder or uploading them from the home page.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
from pathlib import Path

from flask import Flask, Response, abort, flash, redirect, render_template, request, url_for
from markupsafe import Markup, escape

import accessibility_report as ar

app = Flask(__name__)
app.config["REPORTS_DIR"] = Path(__file__).parent / "CourseReports"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.secret_key = os.urandom(16)

app.jinja_env.filters["score"] = ar.fmt_score
app.jinja_env.filters["num"] = lambda n: f"{n:,}"

# Keys every course-report export is expected to carry.
REQUIRED_KEYS = ("Overall Totals", "Cumulative Score")

SORTS = {
    "course": (lambda c: c["course"].lower(), False),
    "overall": (lambda c: c["s"]["overall"] if c["s"]["overall"] is not None else -1, False),
    "change": (lambda c: c["s"]["delta"] if c["s"]["delta"] is not None else 0, False),
    "files": (lambda c: c["s"]["processed"], True),
    "remediated": (lambda c: c["s"]["remediated"] / c["s"]["processed"] if c["s"]["processed"] else 0, False),
    "severe": (lambda c: c["s"]["severities"][0]["total"], True),
}


# --------------------------------------------------------------------------- data

def reports_dir() -> Path:
    return Path(app.config["REPORTS_DIR"])


def report_path(filename: str) -> Path:
    """Resolve a report by file name, refusing anything outside the reports folder."""
    path = (reports_dir() / filename).resolve()
    if path.parent != reports_dir().resolve() or path.suffix.lower() != ".json" or not path.is_file():
        abort(404)
    return path


def load_course(path: Path) -> dict:
    data = ar.load(path)
    return {"filename": path.name, "course": ar.course_from_filename(path), "data": data,
            "s": ar.summarize(data)}


def load_all() -> tuple[list[dict], list[tuple[str, str]]]:
    courses, errors = [], []
    for path in sorted(reports_dir().glob("*.json")):
        try:
            courses.append(load_course(path))
        except (OSError, ValueError, KeyError, TypeError) as e:
            errors.append((path.name, str(e)))
    return courses, errors


def safe_upload_name(name: str) -> str:
    """Keep the export's own name (the course is parsed from it) but drop anything risky."""
    name = Path(name.replace("\\", "/")).name
    name = re.sub(r"[^A-Za-z0-9 ()._-]+", "_", name).strip(" .")
    if not name.lower().endswith(".json"):
        name += ".json"
    return name


# --------------------------------------------------------------------------- chart

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


def trend_svg(s: dict) -> Markup:
    """Line chart of score by format. Overall is highlighted; the data table on the page is the text alternative."""
    months, series = s["months"], s["series"]
    if not months or not series:
        return Markup("")

    width, height = 760, 320
    left, right, top, bottom = 40, 150, 14, 34
    plot_w, plot_h = width - left - right, height - top - bottom
    n = len(months)

    def x(i: int) -> float:
        return left + (plot_w * i / (n - 1) if n > 1 else plot_w / 2)

    def y(v: float) -> float:
        return top + plot_h * (1 - v / 100)

    out = [f'<svg class="trend" viewBox="0 0 {width} {height}" role="img" '
           f'aria-labelledby="trend-title trend-desc">',
           f'<title id="trend-title">{escape(trend_headline(s))}</title>',
           '<desc id="trend-desc">Cumulative accessibility score by format, 0 to 100. '
           'The same data is in the table that follows the chart.</desc>']

    for tick in (0, 25, 50, 75, 100):
        out.append(f'<line class="grid" x1="{left}" x2="{left + plot_w}" y1="{y(tick):.1f}" y2="{y(tick):.1f}"/>')
        out.append(f'<text class="axis" x="{left - 8}" y="{y(tick):.1f}" text-anchor="end" '
                   f'dominant-baseline="middle">{tick}</text>')
    for i, m in enumerate(months):
        out.append(f'<text class="axis" x="{x(i):.1f}" y="{height - 10}" text-anchor="middle">'
                   f'{escape(short_month(m["Date"]))}</text>')

    end_labels = []
    # Draw Overall last so it sits on top.
    for name, values in sorted(series.items(), key=lambda kv: kv[0] == "Overall"):
        pts = [(i, v) for i, v in enumerate(values) if v is not None]
        cls = "overall" if name == "Overall" else "other"
        if len(pts) > 1:
            coords = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in pts)
            out.append(f'<polyline class="line {cls}" points="{coords}"/>')
        for i, v in pts:
            out.append(f'<circle class="dot {cls}" cx="{x(i):.1f}" cy="{y(v):.1f}" r="{5 if cls == "overall" else 3.5}">'
                       f'<title>{escape(name)}, {escape(months[i]["Date"])}: {v:.1f}</title></circle>')
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


# --------------------------------------------------------------------------- routes

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
                           direction="desc" if reverse else "asc", reports_dir=reports_dir())


@app.post("/upload")
def upload():
    saved, rejected = [], []
    for f in request.files.getlist("reports"):
        if not f or not f.filename:
            continue
        try:
            data = json.loads(f.read().decode("utf-8-sig"))
            if not isinstance(data, dict) or not all(k in data for k in REQUIRED_KEYS):
                raise ValueError("doesn't look like a course-report export")
            ar.summarize(data)
        except (ValueError, KeyError, TypeError, UnicodeDecodeError) as e:
            rejected.append(f"{f.filename}: {e}")
            continue
        name = safe_upload_name(f.filename)
        (reports_dir() / name).write_text(json.dumps(data), encoding="utf-8")
        saved.append(name)

    if saved:
        flash(f"Added {len(saved)} report{'s' if len(saved) != 1 else ''}: {', '.join(saved)}", "ok")
    for msg in rejected:
        flash(f"Not added — {msg}", "error")
    if not saved and not rejected:
        flash("Choose one or more .json exports to upload.", "error")
    return redirect(url_for("index"))


@app.get("/course/<path:filename>")
def course(filename: str):
    c = load_course(report_path(filename))
    s = c["s"]
    series_rows = sorted(s["series"].items(), key=lambda kv: kv[0] != "Overall")
    return render_template("report.html", c=c, s=s, chart=trend_svg(s), headline=trend_headline(s),
                           series_rows=series_rows)


@app.get("/course/<path:filename>/markdown")
def course_markdown(filename: str):
    path = report_path(filename)
    c = load_course(path)
    md = ar.build_report(c["data"], c["course"], path.name, None)
    return Response(md, mimetype="text/markdown",
                    headers={"Content-Disposition": f'attachment; filename="{ar.slugify(c["course"])}.md"'})


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
                   help="folder of course-report JSON exports (default: CourseReports/)")
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
