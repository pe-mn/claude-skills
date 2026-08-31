#!/usr/bin/env python
"""Excel COM helpers — for the edits only Excel's engine can do correctly.

Use this for structure and nothing else: inserting/deleting/moving rows and
columns, sorting, autofilter, autofit, recalculation. Those rewrite every cell
reference, CF range, validation, merge, defined name, chart series and drawing
anchor in the file; that is not a job to hand-roll (see references/structural-edits.md).

Everything else — values, text, fills, fonts, widths, heights, CF rules — is
faster and safer through xlsx_patch.py, which cannot disturb what it does not touch.

    with Excel() as app:
        wb = open_book(app, "book.xlsm")        # raises if it opened read-only
        ws = wb.Worksheets("EM01")
        insert_column(ws, "H")
        save_copy_replace(wb, "book.xlsm")      # never wb.Save()

Requires pywin32.
"""
from __future__ import annotations

import os
import shutil
import time
from datetime import datetime
from pathlib import Path

import win32com.client as win32
import win32process

__all__ = ["Excel", "open_book", "save_copy_replace", "insert_column",
           "delete_column", "sort_range", "autofit", "row_heights",
           "set_row_heights", "sweep_windowless", "ExcelError",
           "com_retry", "recalc_and_save"]

XL_CALC_MANUAL, XL_CALC_AUTOMATIC = -4135, -4105
XL_ASCENDING, XL_YES = 1, 1
MSO_SECURITY_FORCE_DISABLE = 3


class ExcelError(RuntimeError):
    pass


#: HRESULTs Excel raises when it is merely BUSY, not broken.
#: -2147418111 = 0x800AC472 / RPC_E_CALL_REJECTED, surfaced as
#: "Call was rejected by callee." 0x8001010A = RPC_E_SERVERCALL_RETRYLATER.
_BUSY = ("rejected by callee", "0x8001010", "800ac472", "retrylater")


def com_retry(fn, what: str = "COM call", tries: int = 6, wait: float = 1.5):
    """Call `fn`, retrying while Excel says it is busy. Re-raises anything else.

    Excel rejects an incoming call whenever it is mid-operation. That is a BUSY
    signal, not a failure, and it is provoked by exactly what automation does:
    write to a cell that many formulas depend on, and the recalculation cascade
    can leave the NEXT call rejected — even a call as trivial as
    ``wb.Worksheets(name)``.

    The failure this prevents is not the exception itself, it is the MISREADING of
    it. Observed: ``Save`` succeeded, the following ``Close`` was rejected, the
    exception escaped the ``finally`` block, and a run that had correctly written
    the file exited non-zero. A false failure is worse than a slow one — it invites
    re-running a pass that already applied.

    Two companions in the same spirit:
      * set ``Application.Calculation`` to manual around a write loop, which stops
        the cascade that causes most rejections (``Excel(manual_calc=True)``);
      * if a run does die mid-write, check the target's MTIME before concluding
        anything was lost — the save may well have landed.
    """
    last = None
    for attempt in range(tries):
        try:
            return fn()
        except Exception as exc:                      # pywintypes.com_error
            last = exc
            if not any(s in str(exc).lower() for s in _BUSY):
                raise
            time.sleep(wait * (attempt + 1))
    raise ExcelError(f"{what}: Excel stayed busy after {tries} attempts") from last


def recalc_and_save(path: str | Path, *, macros: bool = False,
                    tag: str = "recalc") -> Path:
    """The pass that must follow a zip patch: rebuild formulas, then persist.

    A patch cannot recalculate, so every formula DEPENDING on a patched cell still
    holds its old cached value on disk. Excel refreshes them for a human who opens
    the file; a machine reader (``openpyxl data_only=True``, a downstream
    generator, your own verifier) reads the stale value until this runs.

    One open, one rebuild, one save — batch all patches first, then call this once.
    """
    path = Path(path)
    with Excel(macros=macros) as app:
        wb = open_book(app, path)
        com_retry(app.CalculateFullRebuild, "CalculateFullRebuild")
        return save_copy_replace(wb, path, tag=tag)


class Excel:
    """A dedicated, hidden Excel instance that always gets cleaned up.

    Never attaches to a running Excel (``Dispatch`` would): quitting a shared
    instance closes the user's own workbooks. ``DispatchEx`` always starts a
    private process, and we remember its pid so a failed Quit can be resolved
    without a blanket taskkill.
    """

    def __init__(self, visible: bool = False, macros: bool = False,
                 manual_calc: bool = False):
        self.visible, self.macros, self.manual_calc = visible, macros, manual_calc
        self.app = None
        self.pid: int | None = None

    def __enter__(self):
        self.app = win32.DispatchEx("Excel.Application")
        self.app.Visible = self.visible
        self.app.DisplayAlerts = False
        self.app.EnableEvents = False
        self.app.ScreenUpdating = False
        self.app.AskToUpdateLinks = False
        self.app.AutomationSecurity = (1 if self.macros else MSO_SECURITY_FORCE_DISABLE)
        if self.manual_calc:
            self.app.Calculation = XL_CALC_MANUAL
        try:
            _, self.pid = win32process.GetWindowThreadProcessId(self.app.Hwnd)
        except Exception:
            self.pid = None
        return self.app

    def __exit__(self, *exc):
        app, self.app = self.app, None
        if app is None:
            return False
        try:
            for wb in list(app.Workbooks):
                try:
                    wb.Close(SaveChanges=False)
                except Exception:
                    pass
            app.Quit()
        except Exception:
            pass
        del app
        # A refused Quit leaves a process holding the file; the next Open then
        # returns a read-only book, which is how edits get silently discarded.
        if self.pid and _alive(self.pid):
            time.sleep(1)
            if _alive(self.pid):
                os.system(f"taskkill /F /PID {self.pid} >nul 2>&1")
        return False


def _alive(pid: int) -> bool:
    import subprocess
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                         capture_output=True, text=True).stdout
    return str(pid) in out


def sweep_windowless() -> int:
    """Kill orphaned automation instances — those with NO window — and nothing else.

    A blanket ``taskkill /IM EXCEL.EXE`` murders the user's open session and their
    unsaved work. An automation instance is windowless; a human's is not.
    """
    import subprocess
    ps = ("Get-Process EXCEL -ErrorAction SilentlyContinue | "
          "Where-Object { $_.MainWindowTitle -eq '' } | "
          "ForEach-Object { $_.Id; Stop-Process -Id $_.Id -Force }")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True).stdout
    return len([l for l in out.splitlines() if l.strip().isdigit()])


def open_book(app, path: str | Path, *, read_only: bool = False):
    """Open a workbook and REFUSE to continue if Excel handed back a read-only copy.

    This guard is the whole point of the function. When the file is held by
    anything else — the user's Excel, an orphaned automation instance — Excel
    silently opens it read-only, and then ``Workbook.Save`` RETURNS NORMALLY,
    sets ``wb.Saved = True``, and writes nothing at all. Measured, not theorised.
    Without this check the edit is lost and every in-session read-back still
    agrees with you.
    """
    p = Path(path).resolve()
    if not p.exists():
        raise ExcelError(f"no such workbook: {p}")
    wb = com_retry(
        lambda: app.Workbooks.Open(str(p), UpdateLinks=0, ReadOnly=read_only,
                                   Notify=False), f"Open({p.name})")
    if wb.ReadOnly and not read_only:
        who = wb.WriteReservedBy if hasattr(wb, "WriteReservedBy") else "?"
        wb.Close(SaveChanges=False)
        raise ExcelError(
            f"{p.name} opened READ-ONLY (held by another process; write-reserved by "
            f"{who!r}). Close it, or run sweep_windowless() for orphaned automation "
            f"instances. Saving now would discard every edit with no error.")
    return wb


def save_copy_replace(wb, target: str | Path | None = None, *, backup: bool = True,
                      backup_dir: str | Path | None = None, tag: str = "com",
                      retries: int = 12) -> Path:
    """Persist via ``SaveCopyAs`` + atomic replace. Never calls ``Workbook.Save``.

    Why not Save: on a workbook Excel opened read-only, Save reports success and
    writes nothing. SaveCopyAs writes the edits to a NEW file regardless, so the
    work either lands or fails loudly at the replace step — it is never lost.

    ``os.replace`` (not ``shutil.move``): move onto an existing Windows target
    raises FileExistsError and falls back to a copy; replace overwrites atomically.
    """
    target = Path(target).resolve() if target else Path(wb.FullName)
    if backup and target.exists():
        d = Path(backup_dir) if backup_dir else target.parent / "_backups"
        d.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(target, d / f"{target.stem}_{tag}_{stamp}{target.suffix}")
    tmp = target.with_name(target.stem + ".savecopy" + target.suffix)
    tmp.unlink(missing_ok=True)
    # Retried: a workbook that has just finished a large recalculation rejects the
    # very next call, and losing the save to that would be losing the whole edit.
    com_retry(lambda: wb.SaveCopyAs(str(tmp)), "SaveCopyAs")
    if not tmp.exists():
        raise ExcelError(f"SaveCopyAs produced no file at {tmp}")
    try:
        wb.Close(SaveChanges=False)          # release the target before replacing
    except Exception:
        pass
    for attempt in range(retries):
        try:
            os.replace(tmp, target)
            return target
        except PermissionError:
            # A virus scanner holds the freshly-written file for a moment
            # (WinError 5), then lets go. Retry; never abort.
            if attempt == retries - 1:
                raise
            time.sleep(1)
    return target


# --- structural edits: the reason this module exists -------------------------
def insert_column(ws, at: int | str, count: int = 1) -> None:
    """Insert ``count`` columns before column ``at`` ('H' or 8).

    Excel rewrites every cell reference, formula (including cross-sheet and
    shared/array), CF range, validation, merge, autofilter, defined name, chart
    series and drawing anchor. One insert into a real mapping sheet moves ~15,000
    references across nine parts — do not hand-roll it.
    """
    col = ws.Columns(at)
    for _ in range(count):
        col.Insert()


def delete_column(ws, at: int | str) -> None:
    ws.Columns(at).Delete()


def row_heights(ws, first: int, last: int) -> dict[int, float]:
    """Capture row heights so they can be re-applied after a sort."""
    return {r: ws.Rows(r).RowHeight for r in range(first, last + 1)}


def set_row_heights(ws, heights: dict[int, float]) -> None:
    for r, h in heights.items():
        ws.Rows(r).RowHeight = h


def sort_range(ws, rng: str, key: str, *, header: bool = True,
               ascending: bool = True, keep_row_heights: bool = True) -> None:
    """Sort ``rng`` by column ``key`` using the SortObject form.

    ``Range.Sort(Key1=...)`` — the legacy form — has been seen to rotate a block
    by one row instead of sorting it. The SortFields form is the one that works.
    Always assert afterwards that the key column reads back in order.

    Row heights do NOT travel with a sort: Excel moves values and formats, not
    row geometry. Captured and re-applied permuted unless you opt out.
    """
    r = ws.Range(rng)
    first, last = r.Row, r.Row + r.Rows.Count - 1
    heights = row_heights(ws, first, last) if keep_row_heights else None
    ws.Sort.SortFields.Delete()
    ws.Sort.SortFields.Add(Key=ws.Range(key), Order=XL_ASCENDING if ascending else 2)
    ws.Sort.SetRange(r)
    ws.Sort.Header = XL_YES if header else 2
    ws.Sort.Apply()
    if heights:
        set_row_heights(ws, heights)


def autofit(ws, cols: str, *, max_width: float | None = None) -> None:
    ws.Columns(cols).AutoFit()
    if max_width:
        for c in range(ws.Range(cols.split(":")[0] + "1").Column,
                       ws.Range(cols.split(":")[-1] + "1").Column + 1):
            if ws.Columns(c).ColumnWidth > max_width:
                ws.Columns(c).ColumnWidth = max_width
