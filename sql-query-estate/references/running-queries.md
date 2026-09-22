# Running the queries — the channel, the human, and the environment

You rarely hold a connection yourself. Someone pastes your SQL into a client, or a
pipeline activity runs it, and each round trip costs far more than the query does. This is
how to spend them.

---

## 1. Establish the channel's constraints once, and write them down

Before designing anything, find out — by testing, not assuming:

| question | why it changes the design |
|---|---|
| One statement per call, or many? | A pipeline script activity typically takes exactly one, strips a single trailing `;`, and errors on anything after it. So `UPDATE …; COMMIT;` arrives as two statements and fails. A comment between statements does the same. |
| Autocommit on? Is `COMMIT` allowed? | If autocommit is on and one statement is the limit, `COMMIT` is both unnecessary and fatal. |
| Does a write report rows affected? | Many channels return nothing. Then a DML that matched **nothing** is indistinguishable from one that worked, and every write needs a separate numeric read-back. |
| Is there a row cap, and on **what**? | A displayed grid may truncate where the payload does not. One channel showed 10 rows in its result grid and returned 158 in its JSON — worth one test, because it changes every design after it. |
| Bind variables? | Usually not. Then a parameter is textual substitution; say so, or someone pastes `:id` and gets an error. Avoid `&name` entirely — clients hijack it as a prompt. |
| String aggregation ceiling | Typically ~4000 bytes, and it *raises* rather than truncating. |

Write them where the queries live. They are the reason a statement looks the way it does.

---

## 2. The paste-back contract

Where a human executes and pastes results, design for a person under time pressure:

- **One self-contained statement.** No `;`-chained scripts, no PL/SQL blocks, no bind
  variables, no substitution prompts.
- **Batch facts, don't batch queries.** Query count is the scarce resource; result rows
  are free. One `UNION ALL` returning forty facts beats forty queries returning one. A
  31-table filter audit went from 575 lines (five scans per column, tall shape) to 78
  lines (one scan per table, wide shape) and got *faster*.
- **One uniform, all-`TO_CHAR` result shape** across the whole pack, so one loader ingests
  every export.
- **Self-report the row count** as the first row. A round number in a paste is a client
  *page*, not a population — the tool's default fetch limit truncates silently and the
  export looks complete.
- **Stamp provenance in the result**, not the filename: instance, schema and run time as
  `_ENV` rows. Two undated dumps once cost a round trip to adjudicate. It also lets you
  fingerprint pastes that arrive out of order.
- **Paste the query inline, in full.** Attachments may be unopenable, and abbreviating
  ("…repeat for the other 30 tables") means only what you pasted gets run — measured once,
  a sweep came back covering 1 table of 31. Too long to paste is a signal to **restructure
  the query**, never to summarise it.
- **One statement per ask, in dependency order**, each naming the connection it needs. No
  exception for cheap or instant queries: a block that needs four results is four asks,
  and shipping them together reliably draws the complaint *"you provided many queries at
  once!"*. The next statement should be chosen from the previous answer anyway.
- **Number every ask `N of M`, and announce out loud when M changes.** The person pasting
  has no view of your plan and no idea whether they are a third of the way through. When a
  query has to be re-sent after an error, say "that raises the count to 28" rather than
  silently reusing the number — the count is the only progress bar they have.

**Expect a partial paste.** Where the data is sensitive, rows will be withheld
deliberately. Aggregates, not row dumps, are the authority on counts — and if you need
actual values, ask, rather than assuming the refusal was an oversight.

**The window can close mid-pass, without warning. Assume it will.** The moment access
ends, everything not yet asked is worth exactly what you wrote down about it. Keep a
runbook of unanswered queries ordered by value, updated as you go: full SQL, the
environment it must run in, and a line naming the open question each one closes. The same
file is the right place to record which repairs have actually been *executed* versus
merely written — a distinction that is invisible a week later.

---

## 3. Oracle errors that each cost a round trip

- **ORA-12704 character set mismatch** — an `NVARCHAR2` expression in a `UNION ALL` branch
  beside `VARCHAR2` literals, or mixed inside one `CASE`. Wrap every national-character
  reference in `TO_CHAR`. It is *not* caused by `||`, which is where people usually look
  first.
- **ORA-01785** — a compound query accepts only *positional* `ORDER BY`. Wrap the union in
  `SELECT * FROM (...)` if you need to sort by an expression.
- **ORA-00937 not a single-group group function** — a scalar subquery containing an
  aggregate inside an outer query that is itself a single-group aggregate. Keep the outer
  query `FROM DUAL`, or push the grouping into its own branch's `FROM`.
- **ORA-01722 invalid number** — comparing a text id column to a numeric key, or casting
  free text. Guard with `CASE WHEN VALIDATE_CONVERSION(x AS NUMBER) = 1 THEN TO_NUMBER(x)
  END` (12.2+). Put the guard in the SELECT list, **not** a `WHERE` clause: view merging
  can evaluate a bare `TO_NUMBER` before the filter, and one bad value kills the whole
  statement. Note `VALIDATE_CONVERSION(NULL)` returns 1, so a "convertible" count includes
  nulls — subtract them before concluding a column is numeric.
- **ORA-01489 result of string concatenation is too long** — `LISTAGG` past 4000 bytes.
  See `wide-query-shapes.md` §2.
- **ORA-00933 / ORA-00911** on a channel that takes one statement — almost always a
  trailing semicolon or a second statement, not a syntax error in what you wrote.
- **NULL fall-through in a negated predicate.** `NOT REGEXP_LIKE(col, …)` and `col NOT IN
  (…)` are *unknown*, not true, when `col` is NULL — so the rows you meant to keep vanish.
  Spell the NULL branch out.

**Two mechanical gates, both seconds, both worth it.** Validate every `table.column`
against the schema catalogue — it catches the whole ORA-00904 class. And **parse the
statement** with a parser for the right dialect before sending: "ready" has to mean
runnable, or a round trip is spent on a typo. Two caveats on the catalogue check: a
multi-table union defeats unqualified-column checking, so verify those by hand; and a
validator that resolves aliases naively flags reused subquery aliases (`p`, `c`) as
collisions, which are false positives when each is scoped to its own `EXISTS`.

---

## 4. There is no "clean" copy

Run in every environment you can reach, because defaulting and masking are **per column**
and differ per environment — a column can be real in one and a placeholder in the other:

| column | copy A | copy B |
|---|---|---|
| national id | 53,590 rows / **530 distinct** | 48,809 / **38,399 distinct** |
| home phone | 58,282 / **122 distinct** | 19,293 / **9,521 distinct** |
| mobile | varied | **1 distinct** |

Masking can only *reduce* distinctness, so the copy with more distinct values is the
truthful one **for that column** — and it is not the same copy each time.

- **Agreement across two independent copies is the strongest evidence short of
  production.** Where they agree, treat it as settled.
- **Where they disagree you cannot infer production.** Flag it; do not average, and do not
  take the bigger number.
- **Volumes especially.** On one comparison 26 of 31 tables disagreed by up to +82%. A
  claim that the data was "one snapshot cloned twice" turned out to rest on comparing a
  live count against a catalogue that already described that same copy.
- **Recency beats row count for "is this alive".** A table can hold 20,000 rows and have
  taken no write in six years. Measure activity against each table's **own** max
  timestamp, never the current date — copies have different cut-off dates, and using
  `SYSDATE` ages them all uniformly and falsely.
- **A structural difference between copies is a real risk too**, not just a data one. Do
  not assume two environments have the same columns.

### Two phases, in this order

Where the client withholds real data, the environments split by the *kind* of question,
and running them the wrong way round wastes both:

1. **Values, from the copy you are allowed to read.** Scoped, small, actual column
   contents. This is where a question is *settled*: what a column holds, which of two
   candidate columns is right, code versus free text. Coverage ranks population, not
   meaning — a 100%-populated column can still be the wrong one.
2. **Aggregates, from the larger or more production-like copy.** Counts, sums, distinct
   counts, bucket censuses. Volumes and sparsity come from here. Keep business values out
   of the SELECT list; if you genuinely need a sample from this copy, **ask first**.

Then fix against phase 1, re-measure against phase 2, and stamp environment and date on
both.

**Settle a "which column is it" question BY VALUE, side by side, in ONE statement.** Put
every candidate in the same SELECT over the same rows and read across. One such query over
seven rows once closed six open questions and overturned two picks — one column proved to
be a copy of another while the column that actually held the value sat unmapped, and both
candidates were 100% populated, so no completeness count could have told them apart.

---

## 5. After the run

Build the ingest **before** the window, not after: the export is expensive, the loading
should be free. Check each file's self-reported row count against its actual length on
load — that is the truncation guard doing its job.

Apply findings as a **patch proposal the user approves**, never a direct write. And record
each result as evidence with its environment and date (`query-estate.md` §4) — an answer
that lives only in the conversation will be asked for again.
