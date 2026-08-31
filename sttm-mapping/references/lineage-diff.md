# Answering "did we lose anything?" — diffing a mapping workbook against its history

The question arrives as *"check the backups and make sure all the changes are actually
improvements, and nothing correct was removed."* It is answerable, but the naive method
produces a number an order of magnitude too large and buries the real findings.

Measured on one engagement: the naive method reported **556** lost cells; the correct
method reported **68**, all of them justified. Three of the naive method's largest
"losses" were not losses at all.

## Pick ONE real baseline

**A "maximum over all history" is not a baseline.** Taking, for each cell independently,
the last substantive value it ever held builds a composite state that never existed as a
file. It merges losses from every era, so work done last week shows up as damage done
today. Ask which single prior state the user means, diff two files, and state the
baseline's content timestamp in the finding.

Use the composite scan only to *locate* which checkpoint changed a cell — then open that
checkpoint and its predecessor.

**A backup's filename stamp is when it was TAKEN; its content is the state just BEFORE.**
A file named `..._backup_20260818_000647.xlsx` had a content mtime of
`2026-08-17 22:25:21` — it *is* the last state of 17 August, despite the 18th in its
name. Order candidates by `os.path.getmtime`, never by the name, and say which you used.

## Four ways a false positive gets in

1. **Formula cells.** `data_only=True` reads an uncached `=IF($O$291="","",$O$291)` as
   `None`, so an intact inherited reference reads as deleted data. Load **both** views
   and treat a cell as populated if either is. One run produced 16 phantom findings this
   way.
2. **A blunt header alias.** Columns get renamed between eras; aliasing them together is
   necessary, but aliasing two *different* columns together invents losses. A `Notes` →
   `Model Notes` alias manufactured 78 + 158 findings across two modules. What had
   actually happened was a deliberate split: vendor model facts kept one column, reviewer
   provenance moved to another. **Verify a suspected column move from both directions** —
   every value in A must be findable in B, and vice versa — before believing either.
   Era rules usually already exist in the generator (e.g. "a sheet that has a `Comment`
   column uses `Notes` for the vendor fact"); read them rather than guessing.
3. **A rename read as a deletion.** A row that "disappeared" was the target attribute
   renamed. Check the model row inventory and the vendor drop before calling a row gone.
4. **A sentinel scrub.** An explicit `NO LEGACY SOURCE` going blank is usually a stated
   rule ("absence is blank"), not a loss — provided the row still says so somewhere
   (mapping type, rule). Flag only rows where the compensating statement is absent too,
   because there a reader can no longer distinguish *proven to have no source* from
   *nobody looked*.

## Report both directions

A loss count alone is not an answer to "were the changes improvements". Produce the
per-column ledger: cells gained, cells lost, net. One engagement's real answer was
**+4,303 net across 39 columns, with a single column net-down** — and that column turned
out to be the deliberate split above. Without the ledger the same review reads as
"hundreds of losses".

Beware the aggregate hiding the detail: a column can be net-positive while individual
cells were destroyed (66 added, 78 removed). Run both the census and the per-cell diff.

## A placeholder that leaks unevenly is a routing bug, not a data bug

Where the same placeholder token is blank on most rows and present on a few, suspect that
the scrub which is supposed to remove it lives on a *different pipeline path* than the
deliverable being built. Measured: an absence-token scrub existed and was correct, but
ran only on one of two surfaces — so one module showed the token on 72 rows and 13 of its
identity rows, while the sibling module showed 0 of 95. **The sibling module is the
control**: when two deliverables built from one methodology disagree on a convention, the
cleaner one is usually telling you the intended rule.
