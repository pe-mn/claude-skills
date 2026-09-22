#!/usr/bin/env python
"""Preflight probe: what is in this workbook, and which writer may touch it.

Run this BEFORE any edit. It answers the only question that matters first —
*what would I silently destroy?* — by reading the zip directory, not by trusting
a library to tell you what it understands.

    py xl_probe.py "book.xlsx"                 # inventory + writer verdict
    py xl_probe.py "book.xlsx" --roundtrip     # also PROVE what openpyxl drops
    py xl_probe.py "book.xlsx" --json          # machine-readable

`--roundtrip` copies the file to a temp dir, loads and saves it with openpyxl,
and diffs the zip part list. That is the decisive test: it measures this file
against this openpyxl version instead of guessing from a hardcoded list.

Stdlib only, except --roundtrip which needs openpyxl.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

# --- fragile features, keyed by the zip part that proves them ----------------
# severity: FATAL   = losing it destroys function the user can see
#           SERIOUS = real content loss, sometimes tolerable
#           MINOR   = cosmetic or rebuilt by Excel
FEATURES = [
    ("cell_controls",  "FATAL",   r"^xl/featurePropertyBag/",           "modern cell controls (in-cell checkbox / dropdown)",
     "openpyxl DESTROYS this - no error, no warning. Bound per CELL FORMAT, so per-cell restyling is also a risk"),
    ("vba",            "FATAL",   r"^xl/vbaProject\.bin$",              "VBA macros",
     "openpyxl needs keep_vba=True; a plain round-trip drops them"),
    ("activex",        "FATAL",   r"^xl/activeX/",                      "ActiveX controls",
     "openpyxl does not model these"),
    ("pivots",         "FATAL",   r"^xl/pivotCache/|^xl/pivotTables/",  "pivot tables",
     "openpyxl does not model pivot layout"),
    ("slicers",        "FATAL",   r"^xl/slicers/|^xl/timelines/",       "slicers / timelines",
     "openpyxl does not model these"),
    ("richdata",       "FATAL",   r"^xl/richData/",                     "rich data (linked data types, image-in-cell)",
     "openpyxl does not model these"),
    ("sigs",           "FATAL",   r"^_xmlsignatures/",                  "digital signatures",
     "ANY programmatic write invalidates them"),
    ("form_controls",  "SERIOUS", r"^xl/ctrlProps/",                    "legacy form controls (checkbox/button objects)",
     "parts survive an openpyxl round-trip; the sheet linkage may not - verify by opening"),
    ("vml",            "SERIOUS", r"vmlDrawing\d*\.vml$",               "VML drawings (control anchors, legacy comments)",
     "openpyxl does not model these"),
    ("charts",         "SERIOUS", r"^xl/charts/",                       "charts",
     "openpyxl re-generates charts from its own model - formatting degrades with no part-list change"),
    ("threaded",       "SERIOUS", r"^xl/threadedComments/",             "threaded comments",
     "openpyxl does not model these"),
    ("drawings",       "SERIOUS", r"^xl/drawings/drawing\d*\.xml$",     "drawings / images / shapes",
     "openpyxl support is partial"),
    ("extlinks",       "SERIOUS", r"^xl/externalLinks/",                "external workbook links",
     "openpyxl support is partial"),
    ("customxml",      "SERIOUS", r"^customXml/",                       "custom XML (SharePoint / document metadata)",
     "openpyxl drops it; invisible in Excel, but a governed document may depend on it"),
    ("tables",         "MINOR",   r"^xl/tables/",                       "ListObject tables",
     "modelled, but a structural edit must keep the table ref in step"),
    ("printer",        "MINOR",   r"^xl/printerSettings/",              "printer settings",
     "openpyxl drops them - page setup reverts to default"),
]
SEVERITY = {k: sev for k, sev, *_ in FEATURES}
#: Parts whose loss is benign: Excel rebuilds them, or openpyxl swaps the mechanism.
BENIGN_LOSS = {
    "xl/calcChain.xml": "Excel rebuilds the calc chain on open",
    "xl/sharedStrings.xml": "openpyxl writes strings inline instead (no data loss, larger file)",
}
#: Lost parts that match nothing above and are still cosmetic.
MINOR_LOSS_PAT = r"^xl/worksheets/_rels/|^docProps/"


def _grade(part: str) -> str:
    for _, sev, pat, *_ in FEATURES:
        if re.search(pat, part):
            return sev
    return "MINOR" if re.search(MINOR_LOSS_PAT, part) else "SERIOUS"


def _unescape(s: str) -> str:
    for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
                 ("&apos;", "'"), ("&amp;", "&")):
        s = s.replace(a, b)
    return s

CF_XFPB_URI = "{C7286773-470A-42A8-94C5-96B5CB345126}"  # xf -> featurePropertyBag


def _sheets(z: zipfile.ZipFile) -> list[tuple[str, str]]:
    """[(sheet name, part), ...] in workbook order."""
    wbx = z.read("xl/workbook.xml").decode("utf-8", "replace")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8", "replace")
    target = {m.group(1): m.group(2) for m in
              re.finditer(r'<Relationship[^>]*Id="([^"]+)"[^>]*Target="([^"]+)"', rels)}
    out = []
    for m in re.finditer(r"<sheet\b[^>]*>", wbx):
        tag = m.group(0)
        name = re.search(r'name="([^"]*)"', tag)
        rid = re.search(r'r:id="([^"]*)"', tag)
        state = re.search(r'state="([^"]*)"', tag)
        if not (name and rid) or rid.group(1) not in target:
            continue
        part = "xl/" + target[rid.group(1)].lstrip("/").replace("../", "")
        out.append((_unescape(name.group(1)), part, state.group(1) if state else "visible"))
    return out


def _checkbox_xfs(styles: str) -> set[int]:
    """cellXfs indices carrying an xfComplement ext — i.e. bound to a cell control."""
    m = re.search(r"<cellXfs[^>]*>(.*?)</cellXfs>", styles, re.S)
    if not m:
        return set()
    # Self-closing FIRST: an <xf> with children holds nested '/>' tags, so a
    # single non-greedy '.*?(/>|</xf>)' would stop inside the element and throw
    # every later index off by the number of such elements.
    xfs = re.findall(r"<xf\b[^>]*/>|<xf\b[^>]*>.*?</xf>", m.group(1), re.S)
    return {i for i, xf in enumerate(xfs)
            if CF_XFPB_URI in xf or "xfComplement" in xf}


def _freeze(x: str) -> str | None:
    """`R<rows>/C<cols>` actually frozen, plus the saved scroll cell."""
    m = re.search(r"<pane[^>]*/?>", x)
    if not m or "frozen" not in m.group(0):
        return None
    y = re.search(r'ySplit="(\d+)"', m.group(0))
    xs = re.search(r'xSplit="(\d+)"', m.group(0))
    tl = re.search(r'topLeftCell="([^"]+)"', m.group(0))
    bits = []
    if y and y.group(1) != "0":
        bits.append(f"{y.group(1)} row(s)")
    if xs and xs.group(1) != "0":
        bits.append(f"{xs.group(1)} col(s)")
    out = " + ".join(bits) or "none"
    return out + (f" (scrolled to {tl.group(1)})" if tl else "")


def probe(path: Path, roundtrip: bool = False) -> dict:
    rep: dict = {"file": str(path), "size_bytes": path.stat().st_size,
                 "ext": path.suffix.lower()}
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        rep["parts"] = len(names)
        rep["features"] = [
            {"key": k, "severity": sev, "label": lbl, "note": note,
             "parts": [n for n in names if re.search(pat, n)]}
            for k, sev, pat, lbl, note in FEATURES
            if any(re.search(pat, n) for n in names)
        ]
        styles = (z.read("xl/styles.xml").decode("utf-8", "replace")
                  if "xl/styles.xml" in names else "")
        cb_xfs = _checkbox_xfs(styles)
        rep["style"] = {
            "cellXfs": int((re.search(r'<cellXfs count="(\d+)"', styles) or [0, 0])[1]),
            "dxfs": int((re.search(r'<dxfs count="(\d+)"', styles) or [0, 0])[1]),
            "control_bound_xfs": sorted(cb_xfs),
        }
        wbx = z.read("xl/workbook.xml").decode("utf-8", "replace")
        rep["defined_names"] = len(re.findall(r"<definedName\b", wbx))

        sheets, cb_cells = [], 0
        for name, part, state in _sheets(z):
            if part not in names:
                continue
            x = z.read(part).decode("utf-8", "replace")
            cf = re.findall(r"<conditionalFormatting\b[^>]*>", x)
            bound = 0
            if cb_xfs:
                bound = sum(1 for m in re.finditer(r'<c r="[A-Z]+\d+"[^>]*?\ss="(\d+)"', x)
                            if int(m.group(1)) in cb_xfs)
                cb_cells += bound
            sheets.append({
                "name": name, "state": state, "part": part,
                "dimension": (re.search(r'<dimension ref="([^"]+)"', x) or [None, "?"])[1],
                "rows": len(re.findall(r"<row\b", x)),
                "cells": len(re.findall(r"<c\b", x)),
                "formulas": len(re.findall(r"<f[ >]", x)),
                "cf_blocks": len(cf),
                "cf_rules": len(re.findall(r"<cfRule\b", x)),
                "data_validations": len(re.findall(r"<dataValidation\b(?!s)", x)),
                "merges": len(re.findall(r"<mergeCell\b(?!s)", x)),
                "autofilter": (re.search(r'<autoFilter ref="([^"]+)"', x) or [None, None])[1],
                "hidden_cols": len(re.findall(r'<col[^>]*hidden="1"', x)),
                "hidden_rows": len(re.findall(r'<row[^>]*hidden="1"', x)),
                # THE FREEZE IS ySplit/xSplit, NOT topLeftCell. topLeftCell is
                # merely where the sheet was last SCROLLED to when it was saved,
                # so it wanders on every save (A2, A41, A54, A487, A619 all seen
                # on one file) while the frozen rows never change. Reporting it
                # as "freeze" made a routine Excel save look like lost layout
                # and cost a round trip chasing damage that did not exist.
                "freeze": _freeze(x),
                "control_cells": bound,
            })
        rep["sheets"] = sheets
        rep["control_cells"] = cb_cells

    if roundtrip:
        rep["roundtrip"] = _roundtrip(path)
    rep["verdict"] = _verdict(rep)
    return rep


def _roundtrip(path: Path) -> dict:
    """Prove what openpyxl would drop, on a throwaway copy."""
    import shutil
    import tempfile
    import time
    import openpyxl
    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / path.name
        shutil.copy2(path, dst)
        with zipfile.ZipFile(dst) as z:
            before = set(z.namelist())
        t0 = time.perf_counter()
        kw = {"keep_vba": True} if dst.suffix.lower() in (".xlsm", ".xltm") else {}
        try:
            wb = openpyxl.load_workbook(dst, **kw)
            wb.save(dst)
        except Exception as exc:                       # a crash is also an answer
            return {"error": f"{type(exc).__name__}: {exc}"}
        secs = time.perf_counter() - t0
        with zipfile.ZipFile(dst) as z:
            after = set(z.namelist())
        lost = [n for n in sorted(before - after) if n not in BENIGN_LOSS]
        return {"seconds": round(secs, 2),
                "size_after": dst.stat().st_size,
                "destroys": {n: _grade(n) for n in lost},
                "benign": {n: BENIGN_LOSS[n]
                           for n in sorted(before - after) if n in BENIGN_LOSS}}


def _verdict(rep: dict) -> dict:
    rt = rep.get("roundtrip") or {}
    destroyed = rt.get("destroys") or {}
    fatal = sorted({f["label"] for f in rep["features"] if f["severity"] == "FATAL"})
    serious = sorted({f["label"] for f in rep["features"] if f["severity"] == "SERIOUS"})
    proven_fatal = sorted(n for n, s in destroyed.items() if s == "FATAL")
    proven_serious = sorted(n for n, s in destroyed.items() if s == "SERIOUS")

    if fatal or proven_fatal:
        why = ("round-trip PROVEN to destroy " + ", ".join(proven_fatal) if proven_fatal
               else "workbook holds " + "; ".join(fatal))
        write = ("PATCH for values+formatting; COM for structure. "
                 "openpyxl WRITE IS FORBIDDEN on this file.")
        forbidden = True
    elif serious or proven_serious:
        why = ("round-trip destroys " + ", ".join(proven_serious[:3])
               + (f" (+{len(proven_serious) - 3} more)" if len(proven_serious) > 3 else "")
               if proven_serious else "workbook holds " + "; ".join(serious))
        write = ("PATCH preferred; COM for structure. openpyxl write only if that loss "
                 "is acceptable AND the user has agreed to it.")
        forbidden = False
    else:
        why = "no fragile parts detected" + (" (only cosmetic parts lost)" if destroyed else "")
        write = ("PATCH preferred (fastest, byte-preserving); openpyxl write acceptable; "
                 "COM for structure.")
        forbidden = False
    return {"read": "openpyxl read_only=True (no Excel process)",
            "write": write, "why": why, "openpyxl_write_forbidden": forbidden}


def render(rep: dict) -> str:
    L = [f"{Path(rep['file']).name}  --  {rep['size_bytes']:,} bytes, "
         f"{rep['parts']} zip parts, {rep['ext']}", ""]
    L.append("PRESERVATION RISK")
    if not rep["features"]:
        L.append("  (none detected -- plain cells, styles and formulas only)")
    for f in rep["features"]:
        flag = {"FATAL": "!!", "SERIOUS": "! ", "MINOR": "  "}[f["severity"]]
        L.append(f"  {flag} {f['severity']:<8}{f['label']}  [{len(f['parts'])} part(s)]")
        L.append(f"              {f['note']}")
    st = rep["style"]
    L.append("")
    L.append(f"STYLES  cellXfs={st['cellXfs']}  dxfs={st['dxfs']}"
             + (f"  control-bound xfs={len(st['control_bound_xfs'])}"
                f" -> {rep['control_cells']} cells carry a cell control"
                if st["control_bound_xfs"] else ""))
    L.append(f"NAMES   definedName={rep['defined_names']}")
    L.append("")
    L.append("SHEETS")
    L.append(f"  {'sheet':<26}{'dims':<12}{'rows':>6}{'cells':>7}{'form':>6}"
             f"{'CF':>8}{'DV':>4}{'mrg':>5}{'hid':>5}  filter / freeze / controls")
    for s in rep["sheets"]:
        tag = "" if s["state"] == "visible" else f" ({s['state']})"
        extra = []
        if s["autofilter"]:
            extra.append("filter " + s["autofilter"])
        if s["freeze"]:
            extra.append("freeze " + s["freeze"])
        if s["control_cells"]:
            extra.append(f"{s['control_cells']} controls")
        cf = f"{s['cf_blocks']}/{s['cf_rules']}" if s["cf_rules"] else "-"
        L.append(f"  {(s['name'] + tag)[:25]:<26}{s['dimension']:<12}{s['rows']:>6}"
                 f"{s['cells']:>7}{s['formulas']:>6}{cf:>8}{s['data_validations']:>4}"
                 f"{s['merges']:>5}{s['hidden_cols']:>5}  " + ", ".join(extra))
    L.append("  (CF = blocks/rules)")
    if "roundtrip" in rep:
        rt = rep["roundtrip"]
        L.append("")
        L.append("OPENPYXL ROUND-TRIP (measured on a temp copy)")
        if rt.get("error"):
            L.append(f"  crashed: {rt['error']}")
        else:
            L.append(f"  {rt['seconds']}s, {rt['size_after']:,} bytes")
            if rt["destroys"]:
                for sev in ("FATAL", "SERIOUS", "MINOR"):
                    got = [n for n, s in rt["destroys"].items() if s == sev]
                    if got:
                        L.append(f"  DESTROYS ({sev}, {len(got)}): " + ", ".join(got[:6])
                                 + (" ..." if len(got) > 6 else ""))
            else:
                L.append("  DESTROYS: nothing")
            for k, v in rt.get("benign", {}).items():
                L.append(f"  benign loss: {k} -- {v}")
            L.append("  NB a part-list diff catches WHOLESALE loss only. Content"
                     " degradation (chart formatting,")
            L.append("     control linkage) leaves the part list identical -- confirm"
                     " those by opening in Excel.")
    v = rep["verdict"]
    L.append("")
    L.append("VERDICT")
    L.append(f"  READ   {v['read']}")
    L.append(f"  WRITE  {v['write']}")
    L.append(f"  WHY    {v['why']}")
    return "\n".join(L)


def main() -> int:
    try:                                   # sheet names are often non-ASCII
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("workbook")
    ap.add_argument("--roundtrip", action="store_true",
                    help="prove what openpyxl drops (needs openpyxl; ~1-3s)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    p = Path(a.workbook)
    if not p.exists():
        print(f"no such file: {p}", file=sys.stderr)
        return 2
    rep = probe(p, roundtrip=a.roundtrip)
    print(json.dumps(rep, indent=2) if a.json else render(rep))
    return 1 if rep["verdict"]["openpyxl_write_forbidden"] else 0


if __name__ == "__main__":
    sys.exit(main())
