# The query estate — asking once, and being able to prove it

This is the half of the loop that stops the other half repeating. It covers recovering
what has already been asked, why the obvious de-duplication does not work, and what a
query log needs on it to be worth maintaining.

---

## 1. The symptom, and what it actually is

The complaint arrives as *"you keep asking me the same queries"*. It is worth measuring
before acting, because the measurement changes the fix.

A real count, taken across 103 session transcripts on one engagement: **377 sends of 271
distinct statements.** Sixteen statements had been sent three or more times and one had
been sent **eight times**.

The obvious reading is "de-duplicate them". That reading is wrong, and the data says so:

| de-duplication level | 271 statements collapse to |
|---|---|
| exact text | 271 |
| ignoring literals and numbers | 194 shapes |
| also ignoring object names | 189 shapes |
| also ignoring aliases | 187 shapes |

Structural de-duplication buys almost nothing — and what little it buys is concentrated in
the DML (35 patch statements shared one shape). The read queries, which are the ones you
actually re-run, were near-all singletons: 53 verification `SELECT`s, almost no two alike.

**Because the waste was not repetition. It was narrowness.** Twenty-three pre-run
statements turned out to be *six questions*, and six of those twenty-three were "how many
rows are armed" wearing different projections — `COUNT(*) AS ACTIVE_ROWS`, `COUNT(*) AS
ACTIVE_NOW`, `'active=' || COUNT(*)`, the same with a `LISTAGG` appended, and so on. No
two were textually identical, so no de-duplicator would ever have merged them. They were
one question asked six ways because nobody had written the question down.

**So: organise the estate by the QUESTION, not by the statement.** That is the whole
insight. 271 statements became roughly 34 reusable checks plus a pile of one-off probes.

---

## 2. Recovering what has already been asked

If the answers live in chat logs, mine them; it is a couple of hours and it is the only
way to know what you already have.

- **Filter cheaply first.** A transcript line without one of your distinctive schema or
  control-table tokens cannot hold a relevant statement. Skipping the JSON parse on the
  other ~99% is what makes a multi-hundred-megabyte scan finish in under a minute.
- **Extract fenced code blocks**, keep the ones that start with a SQL verb *and* mention
  your tokens.
- **Split a multi-statement block back into statements.** If the channel takes one at a
  time, a block of four was really four asks and should count as four.
- **Normalise for exact de-duplication**: strip comments, collapse whitespace, upper-case,
  drop a trailing semicolon. Count occurrences — the repeat count is the evidence that
  justifies the whole exercise, so keep it.
- **Group into versions with a looser key**: also replace string literals and numbers with
  placeholders. The latest member of a version group is current; earlier ones are
  superseded.

**Do not let version-grouping fuse things that only look alike.** A one-row patch
targeting control row 9001 and another targeting 3065 share a shape but are different
work. For statements that target a specific object, add the object — the id, the table
name, the searched-for fragment — to the grouping key. Without that guard, 51 distinct
patches collapse into a handful of groups and 45 real statements get mislabelled as
superseded.

**Freeze the ids you issue.** Once a log or a pack cites `V042`, a re-harvest must not
renumber it. Keep a hash→id map in a hand-maintained file and assign new ids only to
statements the map does not know.

---

## 3. Curated and harvested must be separate files

The harvester regenerates its output wholesale. Anything curated that lives in that file
is destroyed on the next run — silently, because a regenerated file looks fine.

```
  harvest_queries.py   ->  query_log_data.py     REGENERATED. Never hand-edit.
  (hand-written)           query_log_meta.py     CURATED. Never machine-written.
                                │
                                └──> build_query_log.py -> the workbook / the pack
```

The curated file holds: the question each check answers, when to run it, what a healthy
answer looks like, the parameters, which statements rolled up into it, lifecycle
overrides, and the evidence ledger. The harvested file holds only what was recovered.

Two failure modes worth knowing, both observed:

- **A status curated in the wrong file** changes nothing on the output, because the
  builder derives status from the harvested side. The tell is one build printing two
  different counts for the same thing — when a build disagrees with itself, suspect the
  curated dictionary, not the data.
- **A duplicate key in a curated dictionary silently wins.** A duplicate key in a Python
  dict literal is legal and the *last* one takes effect, so a second entry added by
  someone else can quietly override yours. Assert the key count after editing, and *import
  the module and print the value* to prove it — a successful `.replace()` proves nothing,
  because string replacement does not fail when it matches nothing.

---

## 4. What the log needs on it

Aim it at one goal: **a reader should know where to go by reading the first page, and
should never need to search.**

**An index first.** Not a rationale page — a router. Three blocks: *what you came here to
do* → the sheet and the exact id; *what each section holds*, with counts; *what each band
of checks covers*. Anyone who has to read an essay to find a query will write their own
query instead.

**A run order.** For anything procedural, the operating path as a numbered checklist,
each step naming the check to run and — the column that matters — the condition that means
*stop*. A checklist without stop conditions is a list; with them it is a gate.

**Checks, keyed by the question.** One row per question, not per statement. The columns
that earn their place:

| column | why |
|---|---|
| the question, phrased as a question | you scan questions, not SQL |
| when to run it | turns a library into a procedure |
| the object it touches | makes "what do I have on table X" a filter, not a search |
| the SQL | one statement, channel-legal |
| parameters, each explained | a `:name` nobody can resolve is not reusable |
| the expected answer, with the measured number | an expectation with no number is a hope |

**Suites.** Where several checks are always run together, carry the concatenated
one-statement version as a first-class row (`references/wide-query-shapes.md` §1). This is
where the two halves of the skill meet: the estate is what tells you *which* checks always
co-occur, and the wide shapes are what let you fuse them.

**An evidence ledger.** One row per measurement that settled something: id, date,
environment, the question, the result, **what it settles**, and the source. This is the
sheet people actually cite. Rules:

- Every row names its environment and date, or it settles nothing later.
- Record the *finding*, not just the number. "857 rows" is a number; "857 rows / 857
  distinct documents / 0 duplicates, so the scope change removed duplicates without losing
  anything" is evidence.
- Where a result overturned something previously believed, say so in the row. That is the
  most valuable kind and the easiest to lose.

**An archive.** Every recovered statement verbatim, banded, marked current or superseded,
with what replaced it. Nothing is ever deleted — a superseded query that has a result is
still dated evidence. You come here only when no check covers what you need.

**Generate all of it.** The log is built from the two source files, so a hand edit to the
output is destroyed by the next build. Say that on the first page, in bold, or someone
will spend an afternoon on an edit that evaporates.

---

## 5. Keeping it honest

- **A suggested roll-up is a suggestion.** Machine-matching a recovered statement to the
  check it was an instance of (token overlap within a band works well enough) is useful,
  but mark it as unconfirmed — a guess presented as fact gets inherited. Confirm by hand
  into the curated file.
- **Assert both directions periodically.** Every open question should have a check or a
  probe; every check should trace to a question someone actually has. Drift shows up as
  checks nobody runs.
- **Promote on the second ask.** A query you have now written twice is a check. That is
  the rule that keeps the estate from re-growing, and it is the one that gets skipped.
- **Record the channel's limits beside the queries**, not in someone's head. They are the
  reason a statement is shaped the way it is, and without them the next person
  "simplifies" it into something that fails.
