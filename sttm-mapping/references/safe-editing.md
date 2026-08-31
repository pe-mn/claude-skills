# Safe workbook editing

> **The generic method now lives in the `excel-editing` skill** (writer dispatch,
> preflight probe, zip patcher, COM helpers, measurements). Load that for *how* to
> write a workbook safely; this file keeps only what is specific to STTM
> engagements. Where the two disagree, `excel-editing` wins — it is measured, and
> §1's "openpyxl fine on a plain .xlsx" advice below is weaker than its preflight.

The mapping content is only as good as its survival in the file. Spreadsheet
corruption in an STTM engagement is usually silent: the save succeeds, and
days later someone notices the macros, checkboxes, or a reviewer's cells are
gone. These rules exist because each one was learned from a real loss or
near-loss.

## 1. Choose the tool by what the file contains

| Workbook | Read | Write |
|---|---|---|
| Plain `.xlsx`, no controls | anything | openpyxl fine (keep formulas: never `data_only=True` on a file you'll save) |
| `.xlsm`, form controls, ActiveX, shapes-with-macros | anything | **COM (Excel automation) or xlwings ONLY** |

A middle path exists for an `.xlsx` whose ONLY fragile content is form-control
checkboxes (no macros): openpyxl writes are permissible **if a COM redraw pass
re-adds the checkboxes as the pipeline's last step, every time** — encode the
redraw in the pipeline driver, never rely on remembering it.

**The rebuild-chain data-loss trap (2026-07-29, a real loss):** once a module has
BOTH a live macro workbook (.xlsm) and a plain source (.xlsx) that a build chain
regenerates it from, EVERY chain run silently discards whatever the user typed
into the .xlsm since the last sync. A one-time "no edits yet" check does NOT
license later runs — the gate must be IN the build script, every run: diff the
two files cell-by-cell, abort on any difference (explicit --force flag to
override), and back up the .xlsm before overwriting. Content tweaks to a live
workbook go surgically via COM; the rebuild chain is for full regeneration only.

**Zombie-sweep discipline (refined 2026-07-29):** kill only WINDOWLESS Excel
processes (`MainWindowTitle -eq ""` = orphaned automation instances) — a blanket
taskkill murders the user's open session and their unsaved work. And expect
`wb.Close(False)` to occasionally throw a late-binding error right AFTER a
successful `Save()` — the save is already on disk; catch, quit, sweep windowless.

**COM driver choice (2026-07-28):** on hosts where PowerShell's COM adapter
misbehaves (Sheets/Worksheets intermittently project as null, property sets
fail with "property cannot be found" on valid objects), write COM passes in
**python/pywin32** (`win32com.client.DispatchEx("Excel.Application")`) — it has
none of those projection quirks. And ALWAYS sweep zombie EXCEL.EXE processes
before AND after a COM pass: every failed run leaves an invisible instance that
LOCKS the workbook, and the next `Workbooks.Open` then returns null SILENTLY
(no exception) — presenting as baffling null-method errors one line later.

openpyxl does not model VBA projects or form controls: loading and saving
such a file silently drops them. It is still fine for throwaway artifacts
(extracts, prototypes) built from a COPY — but nothing openpyxl saves may
ever be copied over the live file.

openpyxl gotcha even on throwaways: merged banner cells are `MergedCell`
objects whose value is read-only — iterating rows and writing without an
`isinstance(cell, MergedCell)` guard raises
`AttributeError: 'MergedCell' object attribute 'value' is read-only`
(banner rows are merged in most STTM-style workbooks).

## 2. COM session hygiene (PowerShell / pywin32 / xlwings)

- **Lock check first**: try opening the file for exclusive write; if locked,
  the user has it open — ask them to close, never force.
- Open with `AutomationSecurity=1` (macros don't fire), `DisplayAlerts=false`,
  `EnableEvents=false`; run `Calculate()` after changes that formulas read.
- **Save, sleep briefly, then Close** — closing immediately after `SaveAs`
  on a macro workbook can throw RPC_E_CALL_REJECTED and leave a zombie
  EXCEL.EXE holding the file. If a zombie appears, kill only the process
  whose window title matches your temp file — the user may have other
  workbooks open.
- OneDrive-synced paths can make `Workbooks.Open` return null (cloud lock):
  copy to a local temp path, edit, copy back.
- Excel's path limit (~218 chars) breaks opens from deep temp dirs — use a
  short working path when needed.

## 3. Bulk I/O discipline

- Read/write whole ranges as 2-D `Value2` arrays; per-cell COM calls are
  ~100x slower and each one is a marshalling failure point.
- **Guard extent lookups**: `UsedRange`-derived last-rows can come back
  empty/garbage on small sheets, producing invalid addresses like `"AD5:AD"`
  (0x800A03EC). Fall back to a fixed headroom (e.g. 400).
- **Re-initialise per-sheet buffers inside loops**: a failed read leaves the
  previous sheet's arrays in the variables, and the next conditional write
  can pour sheet A's data into sheet B. Fail loudly, not silently.
- Formulas written programmatically: functions newer than the base file
  format need the `_xlfn.` prefix when written by file-level tools
  (`_xlfn.TEXTJOIN(...)`) or they render as `#NAME?`; COM `Range.Formula`
  does not need it.
- **Type coercion eats enum values**: Excel parses writes like `1:1` as a
  TIME and `3-1` as a date; the write "succeeds" and the cell silently holds
  a serial number. Set `NumberFormat="@"` on enum/text columns BEFORE
  writing, and audit for numeric residues after.
- **Transient RPC_E_CALL_REJECTED can drop exactly one write** mid-bulk-loop
  while everything else lands. Never trust an apparently-complete apply:
  finish every write session with a full cell-by-cell READ-BACK AUDIT
  against the intended values (cheap, and it also catches coercion).
- Agent-produced JSON may deliver literal ` \n` (backslash-n) instead of
  newlines in some rows and real newlines in others — sweep written cells
  for the literal substring and replace with the real character.
- **A per-cell `.Value2 = $null` clear loop can silently void a later write in
  the SAME row.** Clearing cols 2..N of a row with `for($c=2..){Cells(r,c).Value2=$null}`
  and THEN writing `Cells(r,1).Value2 = $txt` left col-1 empty (no error; the
  font/interior sets on that same cell DID persist, so it isn't a dropped RPC).
  Removing the clear loop fixed it. Don't null-clear cells you're about to write
  beside; if a row genuinely needs clearing, use one `Range(...).ClearContents()`
  call, and always READ-BACK the write.

## 3b. Cross-sheet reference conversion (single-source-of-truth mirrors)

To make a mirror row a live echo of its source ("edit in one place"), write
formula references (`='Sheet'!$AD$15`) into the mirror cells. Build the address
with the cell's own `.Address($true,$true,1)` — NEVER hand-roll a column-letter
helper (an int/double cast bug silently truncates `AD`→`D`, producing
valid-but-wrong references with no `#REF`).

The real trap is Excel's ASYNCHRONOUS calculation, which makes verification
lie. After writing hundreds of cross-sheet formulas, a forced
`CalculateFullRebuild` returns before the background calc thread finishes, so
an immediate `.Value2` read shows a random 1–3 cells holding a NEIGHBORING
cell's value (off-by-one-column) — a *different* cell each run. This is a READ
race, not stored corruption. Defenses, in order:
1. `Application.Calculation = xlCalculationManual` (-4135) while writing (only
   settable with a workbook open) so writes don't thrash.
2. After writing, `CalculateFullRebuild()` then **poll
   `Application.CalculationState` until 0 (xlDone)** before reading.
3. The AUTHORITATIVE audit is a **normal-calc open** (let Excel recalc
   naturally) or reading **cached values with NO forced recalc** — both
   reliable; forced-rebuild-then-immediate-read is not. Compare each
   reference's resolved value to the value captured at write time.
4. For a cell that stays wrong after a settled recalc, **heal it to the
   correct literal** (it equals the source anyway — that's why it's a mirror);
   the live link is lost for that one cell but the data is right.
5. A transient `RPC_E_CALL_REJECTED` mid-loop doesn't only DROP a write — it can
   also STORE a **column-shifted** formula (`$AA$34` landing in the cell that
   should hold `$X$34`). A value-only audit misses these when the neighbouring
   column's value looks plausible. Since a column-for-column mirror always
   references the SAME column letter it sits in, audit that invariant: every
   `='Sheet'!$<letter>$<row>` cell must have `<letter>` equal to the target
   cell's own column. Heal deterministically — the row number in the wrong
   formula is still right, so rewrite with the correct column letter, same row.
Also: text-formatted columns (`NumberFormat="@"`) store a written formula as
literal TEXT instead of evaluating it — set the target to `General` before
writing a reference. Keep a `mirror of <key>` pointer via a CHAR(10)-joined
formula so the marker survives.

## 4. Structural edits (insert/delete columns or rows)

- Do them via COM so the application auto-adjusts every formula, chart
  series, conditional format, validation and merged banner across sheets.
  File-level editors adjust nothing.
- Before: snapshot the numbers that must not move (dashboard KPIs, state
  counts). After: recompute and reconcile — identical unless the edit
  legitimately changes them, and then you must be able to say why.
- Update the project adapter's column map and any scripts holding column
  letters in the same change; note the shift in the engagement log.

## 5. After every write session

Run the integrity checklist from the adapter, typically:
- control count (e.g. expected checkbox count), VBA modules present,
  chart count, dashboards recalculate;
- state-distribution counts match expectation;
- spot-read 3–5 edited cells back;
- human-owned columns byte-identical (compare against the pre-write backup
  extract if in doubt).

## 6. Backups & recovery

- Timestamped backup to scratch before every write session; keep at least
  the last few.
- Restoring HUMAN columns from a backup is a user decision, never automatic
  — the live workbook may contain newer human edits than any backup
  (the user edits between sessions).
- If a bad write is discovered late, reconstruct per-column from backups and
  present a diff for approval rather than wholesale rollback.
