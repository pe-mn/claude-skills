"""Does Excel open this file cleanly, or does it want to repair it?

Run as a SUBPROCESS with a timeout. The trick: a hidden Excel with
``DisplayAlerts = True`` cannot show a repair prompt, so if the file needs one the
Open call blocks and the parent's timeout fires. A clean file returns in seconds.
That gives a mechanical pass/fail for "opens in Excel with no repair prompt"
without a human looking at a dialog.

    exit 0  -> opened clean; prints sheet/cell census
    exit 3  -> Excel raised on Open (rejected the file outright)
    timeout -> Excel wanted a dialog: treat as REPAIR PROMPT
"""
from __future__ import annotations
import argparse, os, sys
from pathlib import Path

import win32com.client as win32
import win32process

ap = argparse.ArgumentParser()
ap.add_argument("--wb", required=True)
ap.add_argument("--pidfile")
ap.add_argument("--probe-cell", action="append", default=[],
                help="Sheet!A1 to read back and print")
a = ap.parse_args()

app = win32.DispatchEx("Excel.Application")
app.Visible = False
app.DisplayAlerts = True          # deliberately ON: a prompt must block, not be swallowed
app.EnableEvents = False
app.AskToUpdateLinks = False
app.AutomationSecurity = 3
if a.pidfile:
    _, pid = win32process.GetWindowThreadProcessId(app.Hwnd)
    Path(a.pidfile).write_text(str(pid))

try:
    wb = app.Workbooks.Open(os.path.abspath(a.wb), UpdateLinks=0,
                            CorruptLoad=0)     # xlNormalLoad: no silent repair path
except Exception as exc:
    print(f"OPEN RAISED {type(exc).__name__}: {exc}", flush=True)
    try:
        app.Quit()
    except Exception:
        pass
    sys.exit(3)

print(f"opened sheets={wb.Worksheets.Count} name={wb.Name}", flush=True)
for spec in a.probe_cell:
    sheet, ref = spec.split("!", 1)
    try:
        c = wb.Worksheets(sheet).Range(ref)
        print(f"CELL {spec} value={c.Value!r} formula={c.Formula!r}", flush=True)
    except Exception as exc:
        print(f"CELL {spec} ERROR {exc}", flush=True)
try:
    print(f"vba={wb.HasVBProject}", flush=True)
except Exception:
    pass
wb.Close(SaveChanges=False)
app.Quit()
print("OK", flush=True)
