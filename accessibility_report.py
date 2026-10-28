#!/usr/bin/env python3
"""
Generate a Markdown accessibility report (plus a score-trend chart) from a
course-report JSON export.

Usage:
    python accessibility_report.py "course-report (Power Systems I 001 Fall 2026).json"
    python accessibility_report.py reports/*.json --out-dir output/
    python accessibility_report.py report.json --course "Power Systems I (001)" --no-chart

Outputs, per input file:
    <out-dir>/<slug>.md          the report
    <out-dir>/<slug>-trend.png   score trend by format (needs matplotlib)

Only the standard library is required; matplotlib is optional and used for the chart.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

# Friendly names for the format codes used in the export.
FORMAT_LABELS = {
    "pdf": "PDF",
    "html": "HTML (web)",
    "web": "HTML (web)",
    "xlsx": "Excel (xlsx)",
    "excel": "Excel (xlsx)",
    "pptx": "PowerPoint (pptx)",
    "powerpoint": "PowerPoint (pptx)",
    "doc": "Word (doc)",
    "docx": "Word (docx)",
    "word": "Word",
    "gif": "GIF",
}

# Maps a file-type code to the column name used in "Cumulative Score".
SCORE_COLUMN = {
    "pdf": "PDF",
    "html": "Web",
    "xlsx": "Excel",
    "pptx": "PowerPoint",
    "doc": "Word",
    "docx": "Word",
    "gif": "GIF",
}

SEVERITY_SECTIONS = [
    ("Severe", "Severe Issues By Document Type"),
    ("Major", "Major Issues By Document Type"),
    ("Minor", "Minor Issues By Document Type"),
]


# --------------------------------------------------------------------------- helpers

def label(fmt: str) -> str:
    return FORMAT_LABELS.get(fmt.lower(), fmt.upper())


def fmt_score(value) -> str:
    return "—" if value is None else f"{value:.1f}"


def pct(part: float, whole: float) -> str:
    return "—" if not whole else f"{part / whole * 100:.1f}%"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "report"


def course_from_filename(path: Path) -> str:
    """'course-report (Power Systems I 001 Fall 2026).json' -> 'Power Systems I 001 Fall 2026'.

    A timestamped snapshot ('<course>/2026-10-28_102800.json') is named by its folder.
    """
    match = re.search(r"\((.+)\)", path.stem)
    if match:
        return match.group(1)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{6}", path.stem) and path.parent.name:
        return path.parent.name
    return re.sub(r"[_-]+", " ", path.stem).replace("course report", "").strip() or path.stem


def md_table(headers: list[str], rows: list[list[str]], align: list[str] | None = None) -> str:
    align = align or ["left"] * len(headers)
    marks = {"left": "---", "right": "---:", "center": ":---:"}
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(marks[a] for a in align) + " |",
    ]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


# --------------------------------------------------------------------------- data

def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def parse_export(raw: bytes) -> dict:
    """Parse and sanity-check a course-report export; raises ValueError if it isn't one."""
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except UnicodeDecodeError as e:
        raise ValueError(f"not UTF-8 text ({e.reason})") from e
    if not isinstance(data, dict) or not all(k in data for k in ("Overall Totals", "Cumulative Score")):
        raise ValueError("doesn't look like a course-report export")
    try:
        summarize(data)
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"unexpected export contents ({e})") from e
    return data


def scored_months(data: dict) -> list[dict]:
    """Months that have an Overall score (earlier empty months are dropped)."""
    return [m for m in data.get("Cumulative Score", []) if m.get("Overall") is not None]


def score_series(months: list[dict]) -> dict[str, list]:
    """{column name: [score or None per month]} for every column with at least one score."""
    columns = [k for k in (months[0].keys() if months else []) if k != "Date"]
    return {
        col: [m.get(col) for m in months]
        for col in columns
        if any(m.get(col) is not None for m in months)
    }


def issues(data: dict, key: str) -> list[dict]:
    return sorted(data.get(key, []), key=lambda r: r.get("Instances", 0), reverse=True)


# --------------------------------------------------------------------------- chart

def make_chart(months: list[dict], out_path: Path) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  matplotlib not installed; skipping chart (pip install matplotlib)", file=sys.stderr)
        return False

    series = score_series(months)
    if not series or len(months) < 1:
        return False

    labels = [m["Date"].replace(" 20", " '") for m in months]
    x = list(range(len(months)))

    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=150)
    grey, accent = "#B4B2A9", "#2A6FDB"

    end_labels = []
    for name, values in series.items():
        pts = [(i, v) for i, v in zip(x, values) if v is not None]
        if not pts:
            continue
        xs, ys = zip(*pts)
        is_overall = name == "Overall"
        color = accent if is_overall else grey
        ax.plot(xs, ys, color=color, linewidth=3 if is_overall else 1.5,
                marker="o", markersize=6 if is_overall else 4, zorder=3 if is_overall else 2)
        end_labels.append((ys[-1], name, color, is_overall))

    # End-of-line labels, nudged apart so they don't collide.
    end_labels.sort(key=lambda t: t[0], reverse=True)
    last_y = None
    for y, name, color, bold in end_labels:
        ly = y if last_y is None else min(y, last_y - 4.5)
        ax.annotate(f"{name} {y:.1f}", xy=(x[-1], y), xytext=(x[-1] + 0.12, ly),
                    va="center", fontsize=10, color=color if bold else "#333333",
                    fontweight="bold" if bold else "normal",
                    arrowprops=dict(arrowstyle="-", color="#DDDDDD", lw=0.8) if abs(ly - y) > 1 else None)
        last_y = ly

    overall = series.get("Overall", [])
    first, last = overall[0], overall[-1]
    direction = "rose" if last > first else "slipped" if last < first else "held"
    title = (f"Overall score {direction} from {first:.1f} to {last:.1f}, "
             f"{months[0]['Date']} to {months[-1]['Date']}") if len(months) > 1 else \
        f"Overall score {last:.1f}, {months[-1]['Date']}"

    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", pad=22)
    ax.text(0, 1.02, "Cumulative accessibility score by format (0–100)", transform=ax.transAxes,
            fontsize=9.5, color="#666666")
    ax.set_ylim(0, 100)
    ax.set_xlim(-0.2, x[-1] + 0.6 if len(x) > 1 else 0.8)
    ax.set_xticks(x, labels)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.grid(axis="y", color="#EEEEEE")
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#CCCCCC")
    ax.tick_params(colors="#666666", length=0)

    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return True


# --------------------------------------------------------------------------- report

def reporting_period(data: dict) -> str:
    filters = {f["Filter"]: f["Value"] for f in data.get("Filters", [])}
    if not filters:
        return ""
    start = date(int(filters["Start Year"]), int(filters["Start Month"]), 1).strftime("%B %Y")
    end = date(int(filters["End Year"]), int(filters["End Month"]), 1).strftime("%B %Y")
    return f"{start} – {end}"


def summarize(data: dict) -> dict:
    """Everything the Markdown report and the web app show, computed once."""
    totals = (data.get("Overall Totals") or [{}])[0]
    processed = totals.get("Total Number Of Files Processed", 0)
    remediated = totals.get("Total Files Remediated", 0)

    months = scored_months(data)
    latest = months[-1] if months else {}

    files_in = sorted(data.get("Files By Document Type", []), key=lambda r: r["Files"], reverse=True)
    total_files = sum(r["Files"] for r in files_in) or processed
    files = []
    for r in files_in:
        col = SCORE_COLUMN.get(r["Document Type"].lower())
        files.append({"type": r["Document Type"], "label": label(r["Document Type"]), "files": r["Files"],
                      "share": pct(r["Files"], total_files), "score": latest.get(col) if col else None})

    severities = []
    for severity, key in SEVERITY_SECTIONS:
        rows = issues(data, key)
        total = sum(r["Instances"] for r in rows)
        severities.append({
            "name": severity,
            "total": total,
            "rows": [{"format": r["Format"], "label": label(r["Format"]), "description": r["Description"],
                      "instances": r["Instances"], "share": pct(r["Instances"], total)} for r in rows],
        })

    # Severe first, then major, top five of each by instance count.
    priorities = [dict(row, severity=s["name"]) for s in severities[:2] for row in s["rows"][:5]]

    scored = {k: v for k, v in latest.items() if k not in ("Date", "Overall") and v is not None}
    return {
        "overall": totals.get("Overall Accessibility Score"),
        "processed": processed,
        "remediated": remediated,
        "remediated_pct": pct(remediated, processed),
        "alt_downloads": totals.get("Alternative Format Downloads", 0),
        "period": reporting_period(data),
        "months": months,
        "series": score_series(months),
        "empty_months": [m["Date"] for m in data.get("Cumulative Score", []) if m.get("Overall") is None],
        "delta": months[-1]["Overall"] - months[0]["Overall"] if len(months) > 1 else None,
        "latest_label": latest.get("Date", "latest"),
        "files": files,
        "total_files": total_files,
        "severities": severities,
        "priorities": priorities,
        "best": max(scored.items(), key=lambda kv: kv[1]) if scored else None,
        "worst": min(scored.items(), key=lambda kv: kv[1]) if scored else None,
    }


def build_report(data: dict, course: str, source_name: str, chart_file: str | None) -> str:
    s = summarize(data)
    overall, months, files = s["overall"], s["months"], s["files"]

    out: list[str] = []
    out.append(f"# {course} — Accessibility Report\n")
    today = date.today()
    out.append(f"_Generated {today:%B} {today.day}, {today.year} from `{source_name}`"
               + (f" · reporting period {s['period']}_" if s["period"] else "_") + "\n")

    # ---- Summary
    out.append("## Summary\n")
    change = ""
    if s["delta"] is not None and overall is not None:
        delta = s["delta"]
        word = "up" if delta > 0 else "down"
        change = f", {word} {abs(delta):.1f} points since {months[0]['Date']}" if delta else \
            f", unchanged since {months[0]['Date']}"
    out.append(f"The overall accessibility score is **{fmt_score(overall)} out of 100**{change}. "
               f"Of {s['processed']} files processed, {s['remediated']} ({s['remediated_pct']}) have been "
               f"remediated, and {s['alt_downloads']} alternative-format downloads were recorded.\n")

    bullets = []
    if files:
        top = files[0]
        bullets.append(f"**{top['label']} files dominate the course:** "
                       f"{top['files']} of {s['total_files']} ({top['share']})"
                       + (f", scoring {fmt_score(top['score'])}." if top["score"] is not None else "."))
    severe = s["severities"][0]
    if severe["rows"]:
        t = severe["rows"][0]
        bullets.append(f"**Top severe issue:** \"{t['description']}\" in {t['label']} files "
                       f"— {t['instances']:,} instances ({t['share']} of severe issues).")
    if s["best"]:
        (best, best_score), (worst, worst_score) = s["best"], s["worst"]
        bullets.append(f"**Highest-scoring format:** {best} at {best_score:.1f}. "
                       f"**Lowest:** {worst} at {worst_score:.1f}.")
    out.append("\n".join(f"- {b}" for b in bullets) + "\n")

    # ---- Trend
    if months:
        out.append("## Score trend\n")
        if chart_file:
            out.append(f"![Accessibility score trend by format]({chart_file})\n")
        headers = ["Format"] + [m["Date"] for m in months]
        rows = [[name] + [fmt_score(v) for v in vals] for name, vals in s["series"].items()]
        rows.sort(key=lambda r: r[0] != "Overall")
        out.append(md_table(headers, rows, ["left"] + ["right"] * len(months)) + "\n")
        if s["empty_months"]:
            out.append(f"_No scores recorded for: {', '.join(s['empty_months'])}._\n")

    # ---- Files by type
    if files:
        out.append("## Course content by file type\n")
        rows = [[r["label"], r["files"], r["share"], fmt_score(r["score"])] for r in files]
        rows.append(["**Total**", f"**{s['total_files']}**", "**100%**", f"**{fmt_score(overall)} overall**"])
        out.append(md_table(["File type", "Files", "Share of files", f"Score, {s['latest_label']}"], rows,
                            ["left", "right", "right", "right"]) + "\n")

    # ---- Issues by severity
    for sev in s["severities"]:
        if not sev["rows"]:
            continue
        top = sev["rows"][0]
        out.append(f"## {sev['name']} issues\n")
        out.append(f"{sev['total']:,} {sev['name'].lower()} issues were found; the most common is "
                   f"\"{top['description']}\" in {top['label']} files "
                   f"({top['instances']:,}, {top['share']}).\n")
        rows = [[r["label"], r["description"], f"{r['instances']:,}"] for r in sev["rows"]]
        out.append(md_table(["Format", "Issue", "Instances"], rows, ["left", "left", "right"]) + "\n")

    # ---- Priorities
    out.append("## Where to start\n")
    out.append("Issues ranked by severity, then by number of instances. "
               "Severe issues block screen-reader users and should be fixed first.\n")
    ranked = [f"**{r['severity']} · {r['label']}:** {r['description']} ({r['instances']:,})"
              for r in s["priorities"]]
    out.append("\n".join(f"{i}. {line}" for i, line in enumerate(ranked, 1)) + "\n")

    # ---- Notes
    out.append("## Notes on the data\n")
    out.append("- Scores are cumulative monthly snapshots on a 0–100 scale.\n"
               "- Issue counts are instances, not files: one document can contribute many instances.\n")
    return "\n".join(out)


# --------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build an accessibility report from a course-report JSON export.")
    p.add_argument("inputs", nargs="+", type=Path, help="one or more course-report JSON files")
    p.add_argument("-o", "--out-dir", type=Path, default=Path("reports"), help="output folder (default: reports/)")
    p.add_argument("--course", help="course name for the title (default: taken from the file name)")
    p.add_argument("--no-chart", action="store_true", help="skip the PNG chart")
    args = p.parse_args(argv)

    # PowerShell and cmd don't expand wildcards, so do it here.
    inputs = []
    for path in args.inputs:
        matches = sorted(Path().glob(str(path))) if any(ch in str(path) for ch in "*?[") else []
        inputs += matches or [path]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    status = 0
    for path in inputs:
        try:
            data = load(path)
        except (OSError, json.JSONDecodeError) as e:
            print(f"error: {path}: {e}", file=sys.stderr)
            status = 1
            continue

        course = args.course or course_from_filename(path)
        slug = slugify(course)
        chart_name = None
        if not args.no_chart and make_chart(scored_months(data), args.out_dir / f"{slug}-trend.png"):
            chart_name = f"{slug}-trend.png"

        md_path = args.out_dir / f"{slug}.md"
        md_path.write_text(build_report(data, course, path.name, chart_name), encoding="utf-8")
        print(f"wrote {md_path}" + (f" and {args.out_dir / chart_name}" if chart_name else ""))
    return status


if __name__ == "__main__":
    sys.exit(main())
