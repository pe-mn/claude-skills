# Deriving the query pack from the mapping

> **The general craft of interrogating a database lives in the `sql-queries` skill,
> not here.** Load it for: writing the widest statement that still answers the question,
> the shapes that carry many facts in one statement, the paste-back contract and query
> numbering, the Oracle errors that each cost a round trip, why no environment is a
> "clean" copy and the two-phase values-then-aggregates protocol, and keeping an estate so
> a result becomes citable evidence instead of being re-measured.
>
> What stays below is the part that is specific to a **mapping** engagement: deciding
> which questions are worth a database at all, and what to do with the answers.

You get a few hours against the legacy database, paste-and-export only, and everything you
fail to ask becomes a migration risk. Most of spending it well happens *before* you write
any SQL.

## 1. The window is usually NOT the bottleneck — prove that before you plan

The instinct is to build a large query pack. Derive it from the mapping instead, and the
pack collapses. On one engagement 4,452 open mapping cells decomposed to:

| resolver | cells |
|---|---:|
| internal ruling (ours: PII class, quality rules, validation, confidence) | 2,374 |
| already answered in a prior query pack, never transcribed | 202 |
| whole table already on disk in the lookup workbook | 176 |
| already in the schema catalogue (`data_type`) | 78 |
| **genuinely needs the database** | **99** |

Nine tenths of the "open" work needed no window at all. Four rules follow:

1. **Derive every query from an open cell.** No gap, no query — and assert the reverse
   too: every query must trace back to a cell it will fill. A pack built from what comes
   to mind will miss the boring, high-count questions and invent interesting ones nobody
   asked. Compute the remainder mechanically from the gap register, the rule audits, the
   unresolved multi-column picks and the reject-row census; do not re-derive it by hand
   each revision.
2. **Read the prior packs first.** A 2,290-line running log of previously ANSWERED blocks
   sat on disk; a mention-scan of it against the gap list found 202 cells already settled
   in prose. Asking a live database for a number already written down is the most
   expensive mistake available.
3. **Scope the gap by RESOLVER, not by emptiness.** An empty cell on a row with no legacy
   source, or on a TO-BE→TO-BE reference, is not a database question. Classifying first
   cut one register from 2,078 "DB facts" to 477.
4. **Mine filled cells too, not just empty ones.** A register that only looks at blanks
   misses an uncertainty expressed *inside* a populated cell — `A | B`, "assumed",
   "verify", "which of". Scanning cell CONTENT surfaced 650 further markers on one
   engagement, including 27 unresolved multi-column picks.

## 2. Every query states which cells it settles

A query that cannot name the Mapping_IDs it unblocks is not worth a database window. Carry
that as a line on the query itself (`-- settles: …`), and gate it: a pack entry without one
should fail your own checker.

This is also what makes the answers applicable. When the grid comes back, the cells to
change are already named — you are not re-deriving why the query mattered from the SQL.

## 3. Applying what comes back

- **Fix the mapping against the values, re-measure against the aggregates**, and stamp
  environment and date on both. See the two-phase protocol in `sql-queries`.
- **Apply findings as a patch proposal the user approves**, never a direct write to the
  workbook.
- **A mapping change invalidates its dependants.** A Source edit does not stand alone —
  the transformation, the evidence grade, the confidence and the validation columns on
  that row are all now stale. Sweep them in the same pass.
- **Record the result where the next session will find it**, not in the conversation. An
  answer that exists only in a chat log gets asked for again; that is what the query
  estate in `sql-queries` exists to prevent.
