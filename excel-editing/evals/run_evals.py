#!/usr/bin/env python
"""Evals for the excel-editing skill. Every case runs against a COPY of a real
workbook and reports its own wall-clock time — a correct-but-slow answer fails
the problem this skill exists to solve.

    py run_evals.py --wb-dir "<folder with the three workbooks>"
    py run_evals.py --controls a.xlsx --macro b.xlsm --plain c.xlsx
    py run_evals.py ... --only E1,E3

Needs, by hazard rather than by name:
  --controls  an .xlsx carrying modern cell controls (xl/featurePropertyBag/)
  --macro     an .xlsm with macros, charts, form controls, CF and validations
  --plain     an .xlsx with neither

E1  grey N scattered rows with ONE conditional-format rule; controls survive
E2  fill 362 identifier cells; values exact, "3.30" not coerced to 3.3
E3  insert a column via COM; refs/CF/DV/merge/filter shift, macros intact,
    and Excel opens the result without a repair prompt
E4  the WRONG approach (openpyxl round-trip on the control workbook) is caught
    by the preflight instead of discovered after the damage
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import xl_probe                                    # noqa: E402
import xlsx_patch as xp                            # noqa: E402

GREY = "FF808080"
#: 139 rows in 10 scattered blocks — the shape of a real "grey these rows" job.
BLOCKS = [(20 + 60 * i, 34 + 60 * i) for i in range(9)] + [(560, 563)]
NROWS = sum(b - a + 1 for a, b in BLOCKS)

#: Values that Excel coerces when written through COM without NumberFormat="@":
#: "3.30" -> 3.3, "1:1" -> a time serial, "3-1" -> a date, "0012" -> 12.
TRICKY = ["3.30", "1:1", "3-1", "0012", "1E5", "16.10", "007", "1/2"]


class Eval:
    def __init__(self, name: str, what: str):
        self.name, self.what = name, what
        self.checks: list[tuple[bool, str]] = []
        self.notes: list[str] = []
        self.secs = 0.0

    def check(self, ok: bool, label: str) -> bool:
        self.checks.append((bool(ok), label))
        return bool(ok)

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(ok for ok, _ in self.checks)

    def report(self) -> None:
        head = "PASS" if self.passed else "FAIL"
        print(f"\n{'=' * 74}\n{self.name}  [{head}]  {self.secs:.2f}s wall — {self.what}")
        for ok, label in self.checks:
            print(f"   {'[ok]  ' if ok else '[FAIL]'} {label}")
        for n in self.notes:
            print(f"   .     {n}")


def zparts(p: Path) -> set[str]:
    with zipfile.ZipFile(p) as z:
        return set(z.namelist())


def sheet_xml(p: Path, name: str) -> str:
    bk = xp.Book(p)
    return bk.sheet(name).xml


def data_sheet(p: Path) -> str:
    """The busiest sheet, by cell count. Chosen BY SHAPE, never by name.

    These evals used to address a sheet called `EM01`, which made them runnable
    against exactly one project's workbook — against anything else they died with
    `no sheet named 'EM01'`. Sheet names are project knowledge and belong in a
    project adapter; this skill has to hold for any workbook, and its own tests
    are the first place that has to be true.
    """
    bk = xp.Book(p)
    best, best_n = None, -1
    for name in bk.sheet_names():
        try:
            n = bk.sheet(name).xml.count("<c ")
        except Exception:
            continue
        if n > best_n:
            best, best_n = name, n
    if best is None:
        raise SystemExit(f"{p.name}: no readable worksheet")
    return best


def sheet_referencing(p: Path, target: str) -> str | None:
    """A sheet that cross-references `target`, for checking ref rewrites. None if
    the workbook has no cross-sheet formulas — then the caller skips that check
    instead of failing a workbook that simply has nothing to check."""
    bk = xp.Book(p)
    needle = f"'{target}'!"
    for name in bk.sheet_names():
        if name == target:
            continue
        try:
            if needle in bk.sheet(name).xml:
                return name
        except Exception:
            continue
    return None


def styles_of(p: Path) -> tuple[int, int]:
    with zipfile.ZipFile(p) as z:
        s = z.read("xl/styles.xml").decode("utf-8", "replace")
    return (int((re.search(r'<cellXfs count="(\d+)"', s) or [0, 0])[1]),
            int((re.search(r'<dxfs count="(\d+)"', s) or [0, 0])[1]))


def open_in_excel(p: Path, work: Path, probes: list[str] = (), timeout: int = 90):
    """Ask Excel to open the file for real. Returns (status, output).

    ``CorruptLoad=0`` plus ``DisplayAlerts=True`` in a hidden instance means a file
    Excel dislikes is either refused outright (exit 3) or blocks on a prompt it
    cannot show (timeout). Either way we learn it without a human seeing a dialog.
    """
    pid = work / "openchk.pid"
    cmd = [sys.executable, "-u", str(HERE / "open_check.py"), "--wb", str(p),
           "--pidfile", str(pid)]
    for pr in probes:
        cmd += ["--probe-cell", pr]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return ("clean" if r.returncode == 0 else f"exit {r.returncode}",
                (r.stdout + r.stderr).strip())
    except subprocess.TimeoutExpired as e:
        out = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode()
        if pid.exists():
            subprocess.run(["taskkill", "/F", "/T", "/PID", pid.read_text().strip()],
                           capture_output=True)
        return ("REPAIR PROMPT (blocked)", (out or "").strip())


# ---------------------------------------------------------------- E1
def e1_grey_rows(controls: Path, work: Path) -> Eval:
    ev = Eval("E1 grey rows by rule",
              f"grey {NROWS} scattered rows in a workbook with cell controls")
    p = work / "e1.xlsx"
    shutil.copy2(controls, p)
    before = xl_probe.probe(p)
    xf0, dxf0 = styles_of(p)
    cf0 = len(xp.Book(p).sheet("STTM").cf_blocks())

    t0 = time.perf_counter()
    bk = xp.Book(p)
    sh = bk.sheet("STTM")
    sqref = " ".join(f"A{a}:AW{b}" for a, b in BLOCKS)
    dxf_id = sh.add_rule(sqref, xp.dxf_font(GREY), priority=100)
    bk.save(backup_dir=work / "_backups")
    ev.secs = time.perf_counter() - t0

    after = xl_probe.probe(p)
    xf1, dxf1 = styles_of(p)
    ev.check(ev.secs < 2.0, f"under 2s (took {ev.secs:.2f}s)")
    ev.check(dxf1 == dxf0 + 1, f"exactly ONE new dxf ({dxf0} -> {dxf1}), id {dxf_id}")
    ev.check(xf1 == xf0, f"no new cell styles minted (cellXfs {xf0} -> {xf1})")
    ev.check(len(xp.Book(p).sheet("STTM").cf_blocks()) == cf0 + 1,
             f"one new conditionalFormatting block ({cf0} -> {cf0 + 1})")
    ev.check("xl/featurePropertyBag/featurePropertyBag.xml" in zparts(p),
             "featurePropertyBag part still present")
    ev.check(after["control_cells"] == before["control_cells"] > 0,
             f"all {before['control_cells']} cell controls intact")
    ev.check(zparts(p) == zparts(controls), "zip part list unchanged")
    st, out = open_in_excel(p, work, ["STTM!A5"])
    ev.check(st == "clean", f"Excel opens it: {st}")
    ev.note(f"rule covers {NROWS} rows x 49 cols = {NROWS * 49} cells as 1 rule + 1 dxf")
    ev.note(out.splitlines()[0] if out else "")
    return ev


# ---------------------------------------------------------------- E2
def e2_identifiers(macro: Path, work: Path) -> Eval:
    ev = Eval("E2 362 identifier cells",
              'exact values, no numeric coercion of "3.30", macros intact')
    p = work / "e2.xlsm"
    shutil.copy2(macro, p)
    target = data_sheet(p)
    ev.note(f"data sheet picked by cell count: {target!r}")
    want = {}
    for i in range(362):
        r = 5 + i
        want[f"A{r}"] = TRICKY[i] if i < len(TRICKY) else f"ID-{i + 1:03d}"

    t0 = time.perf_counter()
    bk = xp.Book(p)
    sh = bk.sheet(target)
    sh.set_cells(want)
    bk.save(backup_dir=work / "_backups")
    ev.secs = time.perf_counter() - t0

    s2 = xp.Book(p).sheet(target)
    bad = {r: (v, s2.value(r)) for r, v in want.items() if s2.value(r) != v}
    ev.check(not bad, f"all {len(want)} cells read back byte-exact"
                      + (f" (first bad: {list(bad.items())[:2]})" if bad else ""))
    ev.check(s2.value("A5") == "3.30" and isinstance(s2.value("A5"), str),
             f'"3.30" stayed the string "3.30" (got {s2.value("A5")!r})')
    ev.check(all(isinstance(s2.value(r), str) for r in list(want)[:len(TRICKY)]),
             "every tricky value is a string cell, not a number/date")
    ev.check("xl/vbaProject.bin" in zparts(p), "vbaProject.bin intact")
    ev.check(len([n for n in zparts(p) if n.startswith("xl/ctrlProps/")]) ==
             len([n for n in zparts(macro) if n.startswith("xl/ctrlProps/")]),
             "form-control parts intact")
    ev.check(ev.secs < 5.0, f"under 5s (took {ev.secs:.2f}s)")
    st, out = open_in_excel(p, work, [f"{target}!A5", f"{target}!A6"])
    ev.check(st == "clean", f"Excel opens it: {st}")
    for line in out.splitlines():
        if line.startswith("CELL"):
            ev.note(line)
    # control arm: what COM does to the same value with no NumberFormat guard
    coerced = _com_coercion_arm(macro, work)
    ev.note(f"control arm — same value written through COM: {coerced}")
    return ev


def _com_coercion_arm(macro: Path, work: Path) -> str:
    """Same values through COM, with and without the NumberFormat="@" guard.

    The target range is forced to General first: a column that is ALREADY text
    shows no coercion and would make this arm pass for the wrong reason.
    """
    try:
        sys.path.insert(0, str(SCRIPTS))
        import xl_com
    except Exception as exc:                                   # pywin32 missing
        return f"skipped ({exc})"
    p = work / "e2_com.xlsm"
    shutil.copy2(macro, p)
    try:
        with xl_com.Excel() as app:
            wb = xl_com.open_book(app, p)
            ws = wb.Worksheets(data_sheet(p))
            coerced, kept = [], 0
            for i, v in enumerate(TRICKY):
                a, g = ws.Range(f"AY{300 + i}"), ws.Range(f"AY{340 + i}")
                a.NumberFormat = "General"
                g.NumberFormat = "@"
                a.Value = v
                g.Value = v
                if str(a.Value) != v:
                    coerced.append(f"{v}->{a.Value!r}")
                kept += (g.Value == v)
            wb.Close(SaveChanges=False)
        return (f"General cells COERCED {len(coerced)}/{len(TRICKY)}: "
                f"{', '.join(coerced[:4])}{' ...' if len(coerced) > 4 else ''}"
                f' | NumberFormat="@" first kept {kept}/{len(TRICKY)} exact')
    except Exception as exc:
        return f"skipped ({type(exc).__name__}: {exc})"


# ---------------------------------------------------------------- E3
def e3_insert_column(macro: Path, work: Path) -> Eval:
    ev = Eval("E3 insert a column (COM)",
              "every reference, CF range, validation and macro survives")
    try:
        import xl_com
    except Exception as exc:
        ev.check(False, f"pywin32 unavailable: {exc}")
        return ev
    p = work / "e3.xlsm"
    shutil.copy2(macro, p)
    target = data_sheet(p)
    refsheet = sheet_referencing(p, target)
    ev.note(f"data sheet {target!r}; cross-referencing sheet {refsheet!r}")

    def snap(path: Path) -> dict:
        x = sheet_xml(path, target)
        summary = sheet_xml(path, refsheet) if refsheet else ""
        return {
            "cf": re.findall(r'<conditionalFormatting sqref="([^"]+)"', x),
            "dv": re.findall(r'<dataValidation\b[^>]*sqref="([^"]+)"', x),
            "merge": re.findall(r'<mergeCell ref="([^"]+)"', x),
            "filter": re.findall(r'<autoFilter ref="([^"]+)"', x),
            "hidden": [int(a) for a, _ in
                       re.findall(r'<col[^>]*min="(\d+)"[^>]*max="(\d+)"[^>]*hidden="1"', x)],
            "xref": re.findall(rf"'{re.escape(target)}'!\$([A-Z]+)\$\d+", summary)[:6],
            "parts": zparts(path),
        }

    b = snap(p)
    t0 = time.perf_counter()
    with xl_com.Excel() as app:
        wb = xl_com.open_book(app, p)
        xl_com.insert_column(wb.Worksheets(target), "H")
        xl_com.save_copy_replace(wb, p, backup_dir=work / "_backups")
    ev.secs = time.perf_counter() - t0
    a = snap(p)

    def shift(ref: str) -> str:
        """What the reference should become after inserting one column at H (8)."""
        def bump(m):
            col, row = m.group(1), m.group(2)
            i = xp.col_index(col)
            return f"{xp.col_letter(i + 1) if i >= 8 else col}{row}"
        return re.sub(r"([A-Z]+)(\d+)", bump, ref)

    ev.check([shift(r) for r in b["cf"]] == a["cf"],
             f"CF ranges shifted: {b['cf']} -> {a['cf']}")
    ev.check([shift(r) for r in b["dv"]] == a["dv"],
             f"{len(b['dv'])} validation ranges shifted correctly")
    ev.check([shift(r) for r in b["merge"]] == a["merge"],
             f"merge shifted: {b['merge']} -> {a['merge']}")
    ev.check([shift(r) for r in b["filter"]] == a["filter"],
             f"autofilter shifted: {b['filter']} -> {a['filter']}")
    ev.check(sorted(a["hidden"]) == sorted(c + 1 if c >= 8 else c for c in b["hidden"]),
             f"{len(b['hidden'])} hidden columns still hidden, re-indexed")
    ev.check([xp.col_letter(xp.col_index(c) + 1) if xp.col_index(c) >= 8 else c
              for c in b["xref"]] == a["xref"],
             f"cross-sheet formulas re-pointed: {b['xref']} -> {a['xref']}")
    ev.check("xl/vbaProject.bin" in a["parts"], "vbaProject.bin intact")
    ev.check(len([n for n in a["parts"] if n.startswith("xl/charts/")]) ==
             len([n for n in b["parts"] if n.startswith("xl/charts/")]),
             "chart parts intact")
    ev.check(len([n for n in a["parts"] if n.startswith("xl/ctrlProps/")]) ==
             len([n for n in b["parts"] if n.startswith("xl/ctrlProps/")]),
             "form-control parts intact")
    probes = [f"{target}!I5"] + ([f"{refsheet}!C4"] if refsheet else [])
    st, out = open_in_excel(p, work, probes)
    ev.check(st == "clean", f"Excel opens it with no repair prompt: {st}")
    for line in out.splitlines():
        if line.startswith(("CELL", "vba")):
            ev.note(line)
    return ev


# ---------------------------------------------------------------- E4
def e4_preflight_catches(controls: Path, work: Path) -> Eval:
    ev = Eval("E4 preflight catches the wrong writer",
              "openpyxl round-trip on the control workbook is refused up front")
    p = work / "e4.xlsx"
    shutil.copy2(controls, p)

    t0 = time.perf_counter()
    rep = xl_probe.probe(p, roundtrip=True)          # probe on a throwaway temp copy
    ev.secs = time.perf_counter() - t0

    ev.check(rep["verdict"]["openpyxl_write_forbidden"],
             "verdict forbids an openpyxl write")
    ev.check(any(f["key"] == "cell_controls" and f["severity"] == "FATAL"
                 for f in rep["features"]),
             "cell controls flagged FATAL from the part list alone")
    dest = rep["roundtrip"]["destroys"]
    ev.check(any("featurePropertyBag" in n for n in dest),
             f"round-trip PROVEN destructive: {list(dest)}")
    ev.check(rep["control_cells"] > 0,
             f"{rep['control_cells']} control-bound cells counted before any edit")

    # the probe left the real file untouched; prove the damage it predicted is real
    rt = work / "e4_damaged.xlsx"
    shutil.copy2(controls, rt)
    import openpyxl
    openpyxl.load_workbook(rt).save(rt)
    dmg = xl_probe.probe(rt)
    ev.check("xl/featurePropertyBag/featurePropertyBag.xml" not in zparts(rt)
             and dmg["control_cells"] == 0,
             f"the damage is real: controls {rep['control_cells']} -> "
             f"{dmg['control_cells']} after an openpyxl round-trip")
    ev.check(zparts(p) == zparts(controls) and xl_probe.probe(p)["control_cells"] > 0,
             "the probe itself changed nothing (worked on a temp copy)")
    ev.note("a preflight costs ~2s; rediscovering this after the fact costs the workbook")
    return ev


# ---------------------------------------------------------------- runner
def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--wb-dir", default=os.environ.get("EXCEL_EVAL_WB_DIR"))
    ap.add_argument("--controls")
    ap.add_argument("--macro")
    ap.add_argument("--plain")
    ap.add_argument("--work", default=None)
    ap.add_argument("--only", default="E1,E2,E3,E4")
    a = ap.parse_args()

    def pick(explicit, pattern):
        if explicit:
            return Path(explicit)
        if not a.wb_dir:
            return None
        hits = sorted(Path(a.wb_dir).glob(pattern))
        return hits[0] if hits else None

    controls = pick(a.controls, "*controls*.xls[xm]") or pick(a.controls, "*.xlsx")
    macro = pick(a.macro, "*.xlsm")
    plain = pick(a.plain, "*plain*.xlsx")
    work = Path(a.work) if a.work else Path.cwd() / "_evalwork"
    work.mkdir(parents=True, exist_ok=True)

    print(f"work dir: {work}")
    print(f"controls: {controls}\nmacro:    {macro}\nplain:    {plain}")

    only = {s.strip() for s in a.only.split(",")}
    # Require ONLY the workbooks the selected evals actually open. Demanding all of
    # them unconditionally made `--only E2,E3` impossible to run without a
    # cell-control workbook that those two evals never touch — so a partial run,
    # which is exactly what you want after changing one helper, was blocked.
    NEEDS = {"E1": ("controls", controls), "E4": ("controls", controls),
             "E2": ("macro", macro), "E3": ("macro", macro)}
    for ev in sorted(only):
        if ev not in NEEDS:
            print(f"\nunknown eval {ev!r}; choose from {sorted(NEEDS)}")
            return 2
        label, p = NEEDS[ev]
        if not p or not p.exists():
            print(f"\n{ev} needs --{label}: give it a real workbook "
                  f"(see the docstring)")
            return 2
    evals = []
    t0 = time.perf_counter()
    if "E1" in only:
        evals.append(e1_grey_rows(controls, work))
    if "E2" in only:
        evals.append(e2_identifiers(macro, work))
    if "E3" in only:
        evals.append(e3_insert_column(macro, work))
    if "E4" in only:
        evals.append(e4_preflight_catches(controls, work))
    total = time.perf_counter() - t0

    for ev in evals:
        ev.report()
    print(f"\n{'=' * 74}")
    print(f"{'eval':<38}{'result':<8}{'wall':>8}")
    for ev in evals:
        print(f"{ev.name:<38}{'PASS' if ev.passed else 'FAIL':<8}{ev.secs:>7.2f}s")
    npass = sum(1 for e in evals if e.passed)
    print(f"{'TOTAL':<38}{f'{npass}/{len(evals)}':<8}{total:>7.2f}s")
    return 0 if npass == len(evals) else 1


if __name__ == "__main__":
    sys.exit(main())
