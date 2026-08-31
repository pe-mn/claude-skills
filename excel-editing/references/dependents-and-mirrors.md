# Dependents, mirror cells, and what "verified" means across two workbooks

A cell you write is rarely the only cell that changes meaning. Workbooks that share
a mapping typically carry **mirror cells** (also echo refs, inherited cells): a
child row whose value is a reference to an anchor row, so a human answers once and
the answer flows. Editing such a file is mostly about not breaking that, and
verifying it is mostly about not comparing the wrong things.

## Never write a target cell that holds a formula

A mirror cell's content is a reference. Writing a literal over it severs the
inheritance permanently and silently — the value looks right, and the next edit to
the anchor stops propagating. So when syncing workbook A into workbook B:

> Read B **without** `data_only` so a formula cell shows its formula, and skip it.
> Write only the cells B holds as literals. B's own mirrors then recompute.

This is also why anchor-only writes are *sufficient*: on one real workbook, 17
anchor writes carried 108 edits, because 1,998 mirror cells inherited the rest.
Trying to write all 108 would have destroyed 91 references to achieve nothing.

## A bare reference to an EMPTY cell renders 0, not blank

```
='Sheet1'!$A$1     ← A1 empty  →  displays 0
=IF('Sheet1'!$A$1="","",'Sheet1'!$A$1)   → displays blank
```

This is ordinary Excel semantics and it is the single most common defect in a
mirror column. Measured on one workbook: **1,079 cells** showing a spurious `0`
across six columns — every mirror in a column whose anchors were mostly empty
(329 of 329 in one, 285, 262, 185 in others). Nobody had noticed because two of
the worst columns were hidden.

Rewrite bare-reference mirrors to the `=IF(ref="","",ref)` shape, preserving the
reference text exactly. It is semantically identical except for the blank case.
Do it to **every** mirror column, not only the ones showing zeros today: a column
looks clean only because its anchors happen to be filled, and blanking one anchor
later reintroduces the problem. (Exactly that happened — a sync blanked 7 anchors
and 15 new zeros appeared.)

Guard when the workbook has a dashboard: `=IF(...)` returns `""` (text) where the
old form returned `0` (number), so `COUNT` stops counting those cells while
`COUNTA` still does. Snapshot the dashboard's displayed values before and after and
report the diff; refuse to save if error cells appear.

## The 0 launders into copies as a LITERAL

A generator that reads cached values (`data_only=True`) and writes them into a
derived workbook copies the *rendered* `0`, not the formula — so the artifact
arrives as a hard literal with no reference to explain it. On one pair, 598 literal
zeros landed this way in three columns.

That matters most when the derived copy later becomes the source of truth: syncing
it back pushes those literals over the fix. When you clear such artifacts, clear
**literals only** — a formula that merely *evaluates* to 0 is inheritance working,
and clearing it severs the reference. Restrict the sweep to columns where a `0`
cannot be real (prose, identifiers, cardinality strings); never "any cell that
reads 0".

## Verify what you WROTE, not cell-for-cell

Two workbooks built from one mapping usually do **not** inherit the same columns.
One may mirror a column down to every child row while the other carries it flat.
Then a single value on one anchor legitimately renders on 25 cells in one file and
1 in the other, and a cell-for-cell comparison reports 24 failures that are not
failures.

Compare only the cells the sync is responsible for — those the target holds as
literals — and **print the number you excluded**. A check that silently skips most
of the sheet reads as "everything agrees". A converged module hid this bug
completely: every anchor happened to be blank, so both files agreed trivially and
the gate passed at "0 disagreements" while being wrong.

## A green run on a converged file proves only half the code

Running a sync against an already-synced workbook exercises reading and verifying
and never once takes the write path. Test writes with a **revertible sentinel**:
patch one anchor to a unique string, run the sync, assert the value reached the
target anchor *and* its mirrors, then patch it back and assert zero traces remain
and the gate still passes. Pick a column that is excluded from every summary metric
so the sentinel cannot disturb a number someone reads.

## Recalculate, or the file on disk lies

A zip patch cannot recalculate. Every formula that depends on a patched cell keeps
its **old cached value** on disk. Excel refreshes on open, so a human sees the right
thing while any machine reader — `openpyxl data_only=True`, the next generator, your
own verifier — sees the stale one. Follow the patch with one COM open →
`CalculateFullRebuild()` → `save_copy_replace()`. On a 1.4 MB macro workbook that
pass is ~6s and the patch itself is ~0.5s, so the recalculation dominates and is
irreducible; batch all patches, then recalculate once.
