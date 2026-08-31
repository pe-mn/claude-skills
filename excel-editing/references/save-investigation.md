# The hung `Workbook.Save` — investigated, not reproduced

A prior engagement recorded that `Workbook.Save` on a 578×49 workbook with in-cell
checkboxes "took minutes", "hung three times running", and "once killed Excel
outright (RPC failed)", while `SaveCopyAs` + move completed the same work in 4–8s.
The published explanation was that a mass per-cell restyle had minted ~6,800 new
style records and that this was what made Save pathological.

**That explanation is wrong on both counts, and the hang does not reproduce.**

## What was tested

Same workbook (408 KB, 6 sheets, STTM sheet A1:AX581, 1,156 control-bound cells,
7 CF blocks / 24 rules, 12 validations, 28 hidden columns, an active AutoFilter on
`A3:AW581`), on the host where the original failure was recorded. Each case ran as
a subprocess with a wall-clock timeout, killing only the Excel pid the child
reported, so a genuine hang would have been recorded rather than fatal.

| Factor | Values tested | `Save()` |
|---|---|---|
| Edit type | none / one scalar value / 6,811-cell range restyle / one CF rule | 0.20 – 0.27s |
| Per-cell restyle | 6,811 individual COM `Font.Color` writes (96s of *editing*) | 0.30s |
| Cell controls | present in every run (1,156 control-bound cells) | — |
| Instance | hidden / visible | 0.2s / 1.6–1.7s |
| File held elsewhere | free / open in a second Excel / orphan `~$` owner file | 0.26 / 1.36 / 0.28s |
| Opened `ReadOnly` | yes / no | 1.8s — **and silently discarded** |
| `DisplayAlerts` | True / False | no difference |
| Location | local temp dir / the original project folder | 0.22 / 0.25s |
| AutoFilter | active in every run | — |

**24+ Save calls, zero hangs, slowest 1.9s.**

Two published numbers were also wrong:

- The 6,811-cell restyle minted **25 new `cellXfs`** by range, **36** cell-by-cell —
  not ~6,800. Excel de-duplicates style records, so a sweep over thousands of cells
  produces one new record per *distinct* (existing format × new colour) pair.
- The edit was never the cheap half. A **per-cell** loop over those 6,811 cells took
  **96 seconds** (~14 ms per COM round-trip) against 0.21s for the equivalent CF
  rule. Whatever appeared to hang, the per-cell loop is 450× the cost of the rule
  and is the one measurement that reliably reproduces "this is taking forever".

## Two real failure modes found instead

### 1. `Save` on a read-only-opened workbook discards the edit and reports success

When the target is held by anything else — the user's own Excel, an orphaned
automation instance — `Workbooks.Open` returns a **read-only** workbook with no
error. Then:

```
opened ReadOnly=True
in-session read-back: 'SILENT_DISCARD_PROBE'     <- the edit is there
Save() -> RETURNED NORMALLY in 1.89s             <- no exception
wb.Saved after Save: True                        <- Excel says it is saved
on-disk A1 before=None after=None                <- nothing was written
file changed on disk: False
```

Identical with `DisplayAlerts` True or False, hidden or visible. This is the
"the save succeeded, and days later someone notices" failure in its purest form,
and **every in-session verification agrees with you** while it happens.

`SaveCopyAs` from the same read-only workbook wrote the edit correctly (0.20s, copy
contains `COPYAS_PROBE`, original untouched). So:

- **`SaveCopyAs` + `os.replace` can lose the edit only loudly** — either the replace
  succeeds, or it raises (`WinError 32` while the holder still has the target).
- **`Save` can lose it silently.** That, not the unreproduced hang, is the standing
  reason never to call it.
- Guard the open as well: `open_book()` raises when Excel hands back a read-only
  book, which converts the whole failure class into an error message.

### 2. `shutil.move` is the wrong replace

Moving onto an existing Windows target: `os.rename` raises `FileExistsError`
(WinError 183), `shutil.move` then falls back to a *copy*, which raises
`PermissionError` (WinError 32) if anything holds the target. `os.replace`
overwrites atomically. Wrap it in a retry loop: a virus scanner holds the
just-written file for a moment (WinError 5) and lets go on the next attempt.

## Where that leaves the rule

The hang could not be pinned down. Nothing in the workbook's content, the edit, the
instance, the alert setting, the file location or the lock state reproduced it, so
any claim about its cause would be correlation dressed as mechanism — including the
one previously published.

**`SaveCopyAs` + `os.replace` is the standing rule anyway**, on evidence that does
not depend on the hang: it is immune to the read-only silent discard, it never asks
Excel to own the write of the target file, and it was the path that completed when
`Save` did not.

Untested, and worth trying if it ever recurs: a modal dialog left pending in the
automation instance from an earlier failed call (a hidden Excel can never show one);
Excel's AutoRecover colliding with the save; and OneDrive/AutoSave paths, which this
workbook was not on.

## Verifying formatting: read the saved file, not through COM — except for CF

A visual-parity gate for a generated review-pair workbook (STTM project,
2026-08-11) walked every cell of ~21,000 across two workbooks, checking border,
fill, font, number-format and row-height. First cut read everything through COM
— open, then per-cell `.Interior.Color` / `.Borders(...)` / `.Font` / etc. It took
**~480s**.

**The file the gate reads had already been saved by Excel** — a prior stage runs
`CalculateFullRebuild()` and `wb.Save()`, so the bytes on disk are Excel's own
serialisation, not the generator's intent. Reading the STATIC attributes back with
`openpyxl.load_workbook()` (no COM, no Excel process) instead of walking them over
COM:

| | time (both workbooks, ~21,000 cells) |
|---|---|
| every static attribute over COM | ~480s |
| every static attribute from the saved file (openpyxl) | **1.6s** |

**~300×**, not a rounding difference — because COM pays a separate out-of-process
round-trip per attribute per cell (border style/weight/colour × 4 edges, fill,
font name/size/colour/bold, number format), and the file is parsed once.
Re-running both paths against the same files and diffing line-for-line confirmed
they report identical numbers: same fill/font/numfmt/height/border distributions
on every sheet, same coverage percentages, same fill-by-rule breakdown. The one
line that differed was a bug in the COM path's own font-colour read (a themed
"no explicit colour" cell raises over COM instead of returning a value;
openpyxl resolves it fine) — the file-based reader was the more correct of the
two, not just the faster one.

**The one thing a file genuinely cannot testify to is conditional-format
rendering.** A CF rule's colour exists only at *render* time — the dxf record on
disk can look correct while painting nothing (see the `bgColor`-vs-`fgColor`
defect in `cf-fills-need-bgcolor` memory: a rule whose fill sits in the wrong dxf
slot reads fine from either an openpyxl OR a COM *static* read, and only
`Range.DisplayFormat.Interior.Color` proves whether it actually paints). That
part has to stay on COM — but it does not have to run once per cell. Bulk-read
the graded column's values in one range call, then probe `DisplayFormat` only on
**one row per distinct value** — every other row holding that value is painted by
the identical rule, so sampling by distinct value loses no coverage, unlike
sampling by row count. That cut a ~450-cell CF section to ~7 probes per sheet.

**The rule this leaves:** reading a file you did not just write with openpyxl is
not "trusting your own homework" the way reading back your own patch is (that
stays: [[excel-verify-by-opening]] / the `Range.Value = [[...]]` silent-no-op case
above) — it is reading Excel's own saved output, which is exactly what a
COM-based verification would also be reading, at ~300× the cost. Use COM only for
what genuinely cannot be read from bytes: rendered CF/conditional output, and
anything the in-session state has not yet been saved to disk.

## Session hygiene, which the original report is good evidence for

A forced kill leaves orphaned state: the report records `Workbooks.Open` degrading
from 0.7s to 6.6s across one session of killed instances, and stale `~$` owner files
left behind. Sweep **windowless** Excel processes only (`sweep_windowless()`) — a
blanket `taskkill /IM EXCEL.EXE` murders the user's open session and their unsaved
work. An orphan `~$` file did *not* by itself cause a read-only open in testing, but
an orphan *process* does, and that is the one that costs you an edit.
