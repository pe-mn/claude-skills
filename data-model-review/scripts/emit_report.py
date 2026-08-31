#!/usr/bin/env python
"""Turn findings.json into a reviewable workbook and a Markdown summary.

    python emit_report.py findings.json -o review.xlsx [--md review.md]

This creates a NEW workbook, so openpyxl is the right writer and the `excel-editing`
skill's dispatch does not apply — that skill governs editing a workbook you did not
create, where a round-trip can destroy macros, pivots or conditional formats. If you
later need to update a review workbook someone has annotated, stop and load
`excel-editing` first: this script overwrites, and it will take their comments with it.

Any existing target is backed up to a `_backups/` sibling before being overwritten,
timestamped from the file's own mtime rather than the clock, so re-running is safe and
the backup name reflects the content it holds.

Sheet layout, in reading order:
  Summary          the one screen a sponsor reads
  Scorecard        Hoberman categories, with NOT_ASSESSABLE shown as such
  Dimensions       the detailed axis, extensions flagged as ours
  Findings         BLOCKER first, one row per finding, with source and remediation
  Adjudicate       tier-B candidates awaiting a reviewer's judgement
  Not Applicable   rules the paradigm excludes, so silence is not read as a pass
  Input Gaps       what the review could not see
  Sources          the citation registry, so a challenged finding is traceable
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

SEV_FILL = {
    "BLOCKER": "FFC7CE",   # light red
    "MAJOR": "FFD9A0",     # light amber
    "MINOR": "FFF2CC",     # light yellow
    "NOTE": "E7E6E6",      # light grey
}
STATUS_FILL = {"NOT_ASSESSABLE": "DDEBF7", "SCORED": "FFFFFF"}
HEADER_FILL = "1F3864"


def backup(path):
    """Timestamped copy into a _backups/ sibling, named from the file's own mtime."""
    if not os.path.exists(path):
        return None
    d = os.path.join(os.path.dirname(os.path.abspath(path)) or ".", "_backups")
    os.makedirs(d, exist_ok=True)
    stem, ext = os.path.splitext(os.path.basename(path))
    stamp = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(d, f"{stem}_{stamp}{ext}")
    shutil.copy2(path, dest)
    return dest


def load_sources():
    """{source_id: (status, citation_first_line)} from references/sources.md."""
    p = os.path.join(ROOT, "references", "sources.md")
    out = {}
    if not os.path.exists(p):
        return out
    with open(p, encoding="utf-8") as fh:
        text = fh.read()
    for m in re.finditer(r"^###\s+(SRC-[A-Z0-9\-]+)\s+—\s+`(\w+)`\s*\n+(.+?)$",
                         text, re.M):
        out[m.group(1)] = (m.group(2), re.sub(r"\s+", " ", m.group(3)).strip())
    return out


# --------------------------------------------------------------------------------------

def write_xlsx(data, path):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    sources = load_sources()
    wb = Workbook()

    def sheet(title, headers, widths):
        ws = wb.create_sheet(title)
        ws.append(headers)
        for i, (h, w) in enumerate(zip(headers, widths), start=1):
            c = ws.cell(row=1, column=i)
            c.font = Font(bold=True, color="FFFFFF", size=10)
            c.fill = PatternFill("solid", fgColor=HEADER_FILL)
            c.alignment = Alignment(vertical="center", wrap_text=True)
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = None
        return ws

    def finish(ws, wrap_cols=()):
        """Row heights capped at four lines, per house rule, and wrap only where needed."""
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(vertical="top",
                                        wrap_text=c.column_letter in wrap_cols)
        if ws.max_row > 1:
            ws.auto_filter.ref = f"A1:{get_column_letter(ws.max_column)}{ws.max_row}"

    # ---------------- Summary ----------------
    ws = wb.active
    ws.title = "Summary"
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 96
    card = data["scorecard"]
    c = data["counts"]
    rows = [
        ("Data model", data.get("model") or "(unnamed)"),
        ("Input format", data.get("source_format") or "?"),
        ("Paradigm applied", f"{data['paradigm']} — {data['canon_applied']}"),
        ("Paradigm confidence", data.get("paradigm_confidence") or "?"),
        ("Why that paradigm", "; ".join(data.get("paradigm_evidence") or [])),
        ("Canon deliberately NOT applied", "; ".join(data.get("canon_not_applied") or [])),
        ("", ""),
        ("Tables / columns", f"{c['tables']} / {c['columns']}"),
        ("Rules applied", f"{c['rules_applicable']} applicable to this paradigm"),
        ("Rules not applicable", f"{c['rules_not_applicable']} — see 'Not Applicable'; "
                                 f"their silence is not a pass"),
        ("", ""),
        ("BLOCKER", c["blocker"]),
        ("MAJOR", c["major"]),
        ("MINOR", c["minor"]),
        ("NOTE", c["note"]),
        ("Awaiting adjudication", c["candidates_for_adjudication"]),
        ("", ""),
        ("Score", f"{card['percent']}% of assessable weight "
                  f"({card['earned']}/{card['possible']})"
                  if card["percent"] is not None else "not computed"),
        ("Grade", card.get("grade") or "—"),
        ("Categories excluded", ", ".join(card["excluded_categories"]) or "none"),
        ("Weighting", card["weights_note"]),
    ]
    for k, v in rows:
        ws.append([k, v])
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
        row[0].font = Font(bold=True, size=10)
        row[1].alignment = Alignment(vertical="top", wrap_text=True)
    ws["A1"].fill = PatternFill("solid", fgColor=HEADER_FILL)
    ws["A1"].font = Font(bold=True, color="FFFFFF", size=10)

    # ---------------- Scorecard ----------------
    ws = sheet("Scorecard", ["Hoberman category", "Weight (ours)", "Score", "Deducted",
                             "Findings", "Status", "Why not assessable"],
               [26, 14, 10, 11, 10, 18, 74])
    for r in card["rows"]:
        ws.append([r["category"], r["weight"],
                   "—" if r["score"] is None else r["score"],
                   r["deducted"], r["findings"], r["status"], r.get("reason") or ""])
        if r["status"] == "NOT_ASSESSABLE":
            for cell in ws[ws.max_row]:
                cell.fill = PatternFill("solid",
                                        fgColor=STATUS_FILL["NOT_ASSESSABLE"])
    finish(ws, wrap_cols=("G",))

    # ---------------- Dimensions ----------------
    ws = sheet("Dimensions", ["Dimension", "Beyond Hoberman?", "Rules applicable",
                              "Findings", "BLOCKER", "MAJOR", "MINOR", "NOTE",
                              "Awaiting adjudication", "Verdict"],
               [20, 17, 16, 10, 10, 9, 9, 8, 20, 22])
    for d in data["dimensions"]:
        ws.append([d["dimension"], "ours" if d["is_our_extension"] else "Hoberman",
                   d["rules_applicable"], d["findings"], d["blocker"], d["major"],
                   d["minor"], d["note"], d["candidates_for_adjudication"],
                   d["verdict"]])
    finish(ws)

    # ---------------- Findings ----------------
    ws = sheet("Findings", ["Severity", "Rule", "Dimension", "Hoberman", "Object",
                            "What is wrong", "Evidence in this model",
                            "Failure scenario", "Remediation", "Verdict",
                            "Confidence", "Source"],
               [11, 10, 15, 14, 34, 40, 52, 52, 52, 26, 11, 16])
    for f in data["findings"]:
        ws.append([f["severity"], f["rule"], f["dimension"], f["hoberman"],
                   f["object"], f["title"], f["evidence"], f["failure_scenario"],
                   f["remediation"], f["verdict"], f["confidence"], f["source"]])
        ws.cell(row=ws.max_row, column=1).fill = PatternFill(
            "solid", fgColor=SEV_FILL.get(f["severity"], "FFFFFF"))
    finish(ws, wrap_cols=("F", "G", "H", "I"))

    # ---------------- Adjudicate ----------------
    ws = sheet("Adjudicate", ["Rule", "Dimension", "Object", "What to decide",
                              "Evidence found", "Why it matters", "If confirmed, fix",
                              "Source", "Reviewer verdict", "Reviewer evidence"],
               [10, 15, 34, 40, 52, 52, 52, 16, 30, 44])
    for f in data["candidates_for_adjudication"]:
        ws.append([f["rule"], f.get("dimension"), f.get("object"), f.get("title"),
                   f.get("evidence"), f.get("rationale"), f.get("remediation"),
                   f.get("source"), "", ""])
    if ws.max_row == 1:
        ws.append(["—", "", "", "Nothing requires adjudication.", "", "", "", "", "", ""])
    finish(ws, wrap_cols=("D", "E", "F", "G", "J"))

    # ---------------- Not Applicable ----------------
    ws = sheet("Not Applicable", ["Rule", "Dimension", "What it checks", "Why skipped"],
               [10, 16, 60, 52])
    for r in data["rules_not_applicable"]:
        ws.append([r["rule"], r["dimension"], r["title"], r["reason"]])
    finish(ws, wrap_cols=("C", "D"))

    # ---------------- Input Gaps ----------------
    ws = sheet("Input Gaps", ["Area", "What the review could not see"], [24, 110])
    for gap in data["review_input_gaps"]:
        ws.append([gap["category"], gap["why"]])
    if ws.max_row == 1:
        ws.append(["—", "No input gaps recorded."])
    finish(ws, wrap_cols=("B",))

    # ---------------- Sources ----------------
    ws = sheet("Sources", ["Source id", "Status", "Citation", "Rules citing it"],
               [22, 12, 96, 40])
    cited = {}
    for f in data["findings"] + data["candidates_for_adjudication"]:
        cited.setdefault(f.get("source"), set()).add(f["rule"])
    for sid in sorted(sources):
        status, citation = sources[sid]
        ws.append([sid, status, citation,
                   ", ".join(sorted(cited.get(sid, ()))) or "—"])
    finish(ws, wrap_cols=("C", "D"))

    b = backup(path)
    wb.save(path)
    return b


# --------------------------------------------------------------------------------------

def write_md(data, path):
    card = data["scorecard"]
    c = data["counts"]
    L = []
    a = L.append
    a(f"# Data model review — {data.get('model') or '(unnamed)'}")
    a("")
    a(f"**Paradigm:** `{data['paradigm']}` ({data.get('paradigm_confidence')}) — "
      f"{data['canon_applied']}  ")
    a(f"**Basis:** {'; '.join(data.get('paradigm_evidence') or [])}  ")
    a(f"**Scope:** {c['tables']} tables, {c['columns']} columns, "
      f"{c['rules_applicable']} rules applied "
      f"({c['rules_not_applicable']} not applicable to this paradigm)")
    a("")
    if card["percent"] is not None:
        a(f"## {card['percent']}% of assessable weight — {card['grade']}")
    a("")
    a(f"{c['blocker']} BLOCKER · {c['major']} MAJOR · {c['minor']} MINOR · "
      f"{c['note']} NOTE · {c['candidates_for_adjudication']} awaiting adjudication")
    a("")
    if card["excluded_categories"]:
        a(f"> **Not assessable from these inputs:** "
          f"{', '.join(card['excluded_categories'])}. These are excluded from the "
          f"denominator rather than scored zero — they record what the review could "
          f"not see, not a defect in the model.")
        a("")
    a(f"> {card['weights_note']}")
    a("")

    a("## Scorecard")
    a("")
    a("| Category | Weight | Score | Findings | Status |")
    a("|---|---:|---:|---:|---|")
    for r in card["rows"]:
        score = "—" if r["score"] is None else f"{r['score']:g}"
        a(f"| {r['category']} | {r['weight']} | {score} | {r['findings']} | "
          f"{r['status']} |")
    a("")

    a("## Dimensions")
    a("")
    a("| Dimension | Axis | Rules | Findings | B/M/m/N | Verdict |")
    a("|---|---|---:|---:|---|---|")
    for d in data["dimensions"]:
        a(f"| {d['dimension']} | {'ours' if d['is_our_extension'] else 'Hoberman'} | "
          f"{d['rules_applicable']} | {d['findings']} | "
          f"{d['blocker']}/{d['major']}/{d['minor']}/{d['note']} | {d['verdict']} |")
    a("")

    if data["review_input_gaps"]:
        a("## Review input gaps")
        a("")
        for gap in data["review_input_gaps"]:
            a(f"- **{gap['category']}** — {gap['why']}")
        a("")

    a("## Findings")
    a("")
    if not data["findings"]:
        a("No mechanical findings. That is a real result, not a formatting error — but "
          "read the input gaps above before treating it as a clean bill of health.")
        a("")
    seen_sev = None
    for f in data["findings"]:
        if f["severity"] != seen_sev:
            seen_sev = f["severity"]
            a(f"### {seen_sev}")
            a("")
        a(f"**{f['rule']} · {f['object']}** — {f['title']}  ")
        a(f"*Found:* {f['evidence']}  ")
        a(f"*Fails when:* {f['failure_scenario']}  ")
        a(f"*Fix:* {f['remediation']}  ")
        a(f"*Basis:* `{f['source']}` · {f['dimension']} / {f['hoberman']} · "
          f"{f['verdict']} · confidence {f['confidence']}")
        a("")

    if data["candidates_for_adjudication"]:
        a("## Awaiting adjudication")
        a("")
        a("These need a judgement about meaning, so they carry no score until resolved. "
          "Record a verdict and the evidence for it.")
        a("")
        for f in data["candidates_for_adjudication"]:
            a(f"**{f['rule']} · {f.get('object')}** — {f.get('title')}  ")
            a(f"*Found:* {f.get('evidence')}  ")
            a(f"*Why it matters:* {f.get('rationale')}  ")
            a(f"*Basis:* `{f.get('source')}`")
            a("")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("findings")
    ap.add_argument("-o", "--out", default="review.xlsx")
    ap.add_argument("--md", default=None, help="also write a Markdown summary here")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    with open(args.findings, encoding="utf-8") as fh:
        data = json.load(fh)

    b = write_xlsx(data, args.out)
    if args.md:
        write_md(data, args.md)

    if not args.quiet:
        if b:
            print(f"backed up : {b}")
        print(f"workbook  : {args.out}")
        if args.md:
            print(f"markdown  : {args.md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
