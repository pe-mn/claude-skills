---
name: sql-query-estate
description: >-
  Interrogate a database efficiently and never ask the same question twice. Use whenever
  you are about to write SQL to FIND SOMETHING OUT — profiling a legacy schema, verifying
  a data load or migration run, investigating a defect, answering "how many / how often /
  does this ever happen", validating that a patch landed, or auditing what a batch job
  actually did. Also use when someone runs your queries for you (a time-boxed DB window, a
  paste-back loop, a script activity in a pipeline) and each round trip is expensive; when
  a question needs a number that may already have been measured; or when query sprawl has
  set in — the same thing asked repeatedly in slightly different dress, answers living
  only in chat, nobody able to say what has already been settled. Covers writing the
  widest statement that still answers the question (one query for a hundred facts, not a
  hundred queries), the shapes that carry many facts in one statement, the channel limits
  that force them, and keeping a query estate so results become citable evidence. NOT for
  writing application/ETL SQL, tuning a slow query, or designing a schema.
---

# SQL query estate

Two halves of one loop, and they only work together:

1. **Ask wide.** The statement you send should be the widest one that still answers the
   question. One query returning a hundred facts beats a hundred queries returning one.
2. **Record what it settled.** An answer that lives only in a chat log will be asked for
   again. Results become *evidence with provenance*; questions become a small reusable
   estate.

Split them and each half fails. Asking wide without recording means you re-derive the
same wide query next month. Recording without asking wide means you maintain a register
of a hundred narrow queries.

---

## 1. Generic first, then dive

**Census the population before you interrogate a member of it.** The per-object query is
the *second* step, chosen from what the census showed — never the first.

The instinct runs the other way: you have a question about one table, so you query that
table. Then the next one, and the next. Fifty round trips later nobody can say whether
the fifty answers are consistent, and the fifty-first question needs them all again.

A worked case. The question was "did table X load correctly?" The narrow answer is one
count for X. The wide answer — one statement over the data dictionary, joined to the
migration control table and the run log, with a per-table exact count — returned **every**
table's physical count, its control row, its last successful batch and a PASS/FAIL verdict
in a single call. 158 rows. It answered the original question, plus: which tables had
never loaded, which were still armed for the next run, and that a status document had been
wrong for two days. That is ~70 per-table queries and several access windows collapsed
into one ask.

**The discipline, in order:**

| step | question | shape |
|---|---|---|
| 1 | What is the population, and how does it distribute? | `GROUP BY` / bucket census over the whole set |
| 2 | Which members are anomalous? | the same census, `CASE`-bucketed with `LISTAGG` naming the members |
| 3 | What is wrong with *this* member? | now, and only now, a narrow query |

Skipping to step 3 is the error. Step 1 usually answers the question outright, and when it
does not it tells you which member to look at — which you were guessing at before.

**Width is free; narrowness is not.** The cost of a query is the round trip and the
attention of whoever runs it, not its byte count. Adding a column costs nothing. Adding a
second ask costs a round trip, and if a human is pasting results back, it costs their
patience too.

> Read `references/wide-query-shapes.md` before writing the statement. It holds the
> concrete patterns — the check-suite, the bucket-and-name, the multi-fact projection, and
> the dictionary-driven census that counts every table without dynamic SQL.

### When narrow is right

Do not force width where it does not belong:

- **A value sample.** Reading actual values to decide what a column *means* is inherently
  narrow. Put every candidate column in ONE statement and read across the row — but that
  is one narrow query, not a census.
- **A dependency chain.** When statement 2's shape depends on statement 1's answer, they
  are genuinely two asks. Do not guess the second one to save a round trip.
- **Anything that would exceed a hard limit.** See §4.

---

## 2. Three kinds of query, and they are not interchangeable

Sorting queries by this is what makes an estate navigable. The mistake is treating them
as one list.

| kind | what it is | its value is | re-run it? |
|---|---|---|---|
| **CHECK** | a reusable question, parameterised | its **SQL** | yes, that is the point |
| **PROBE** | a one-off measurement answering a specific question | its **RESULT** | no |
| **EVIDENCE** | a probe's result, with provenance, that settled something | the **finding** | never |

A CHECK is "is anything armed that should not be?" — you run it before every batch. A
PROBE is "how many rows in this table have a non-numeric value in that column?" — asked
once, to decide a cast. Its answer becomes EVIDENCE: *"101,632 of 341,836 are
non-numeric, measured on <instance> on <date>, therefore the column stays text."*

**Evidence without provenance settles nothing.** Every recorded result names its
instance/environment and its date, because six weeks later the only question that matters
is "was that measured on the copy we are actually migrating, and was it before or after
the fix?" A number with no answer to that has to be re-measured, which means it was never
evidence.

---

## 3. Do not ask what has already been answered

Before drafting anything, check what is already known. In order of cost:

1. **Reference data you already hold.** A lookup table exported to a workbook, a schema
   catalogue on disk, a data dictionary. Asking a live database for a value sitting in a
   file is the most expensive mistake available.
2. **The estate's own evidence.** If you keep one (§2), this is a filter, not a search.
3. **Prior answers in prose.** Session notes, runbooks, handover documents. These are
   where answers go to be forgotten — they were written as narrative, so nobody thinks to
   look there for a number. Scan them.
4. **Derive the remaining set mechanically**, not from memory. Every query should trace
   back to a specific open question, and every open question should have a query — assert
   *both* directions. A pack built from what comes to mind misses the boring high-count
   questions and invents interesting ones nobody asked.

On one engagement this turned 4,452 apparently-open items into 99 that genuinely needed
the database. On another, 377 query-sends turned out to be 271 distinct statements, of
which the reusable core was about 34 questions.

> `references/query-estate.md` covers building and maintaining the estate: recovering
> what has already been asked, why de-duplicating by SQL *shape* fails, and what a query
> log needs on it to be worth keeping.

---

## 4. Know your channel's limits before you design around them

Every channel has two or three hard constraints, and the wide-query shapes exist to
respect them. Establish them **first**; designing for the wrong limit wastes a round trip
as surely as a syntax error.

Ask, for whatever runs your SQL:

- **One statement, or many?** A pipeline "script" activity typically takes exactly one,
  strips a single trailing `;`, and fails on anything after it. A human in a SQL client
  takes many.
- **Is there a row cap, and on what?** A displayed grid may truncate where the underlying
  payload does not — worth testing once, because it changes every subsequent design. One
  channel showed 10 rows in its grid and returned 158 in its JSON.
- **Does a write report how many rows it changed?** Many do not. Where it does not, a DML
  that matched nothing is indistinguishable from one that worked, so **every write needs a
  numeric read-back** as a separate step.
- **Transaction semantics.** Autocommit on? Is `COMMIT` allowed, or does it break the
  one-statement rule?
- **Are bind variables available?** Often not. Then a "parameter" is textual substitution
  and you must say so, or someone will paste `:id` and get an error.
- **Aggregation limits.** String aggregation typically caps around 4000 bytes; overflow
  raises rather than truncates unless you ask it to truncate.

Write these down where the queries live. They are the reason a statement looks the way it
does, and without them the next person "simplifies" it back into something that fails.

> `references/running-queries.md` covers the human-in-the-loop channel (the paste-back
> contract, numbering, provenance rows), the Oracle errors that each cost a round trip,
> and why no environment is a "clean" copy.

---

## 5. The loop

```
  establish the channel's limits        (§4, once per environment)
            │
  check what is already answered        (§3)
            │
  census the population, wide           (§1 step 1-2)
            │
  dive on what the census flagged       (§1 step 3)
            │
  record the result as EVIDENCE         (§2 — instance + date + what it settles)
            │
  promote anything you will ask again into a CHECK
```

The last step is the one that gets skipped, and it is the one that stops the loop
repeating. A query you have now written twice is a CHECK; write it down as one.

---

## 6. Before you send a statement

- [ ] Is this the **widest** statement that still answers the question?
- [ ] Has it already been answered — in reference data, in the estate, in prose? (§3)
- [ ] Does it fit the channel: statement count, row cap, aggregation limit? (§4)
- [ ] Does every `table.column` exist? Validate against the catalogue mechanically — it
      takes seconds and catches the whole "invalid identifier" class.
- [ ] Does it **parse**? Run it through a parser for the right dialect. "Ready" has to
      mean runnable, or the round trip is spent on a typo.
- [ ] If a human runs it: is it numbered `N of M`, pasted inline in full, self-reporting
      its row count, and stamped with its environment? (`references/running-queries.md`)
- [ ] When the answer comes back: where will it be written down? If the answer is "in this
      conversation", it is not written down.

---

## Reference files

| file | read it when |
|---|---|
| [references/wide-query-shapes.md](references/wide-query-shapes.md) | Writing the statement. The check-suite, bucket-and-name, multi-fact projection, dictionary-driven census, and the verdict column — with runnable skeletons |
| [references/query-estate.md](references/query-estate.md) | Query sprawl has set in, or you are building a log. Recovering what was already asked, why shape-based de-duplication fails, and what a usable estate looks like |
| [references/running-queries.md](references/running-queries.md) | A human or a constrained runner executes your SQL. The paste-back contract, Oracle round-trip killers, and why no environment is a clean copy |

---

## Retrospective

When an engagement ends, fold the *generic* lessons back into these files: a new query
shape that carried more facts than you expected, a channel limit that cost a round trip,
a class of question that turned out to be a CHECK rather than a PROBE.

**Keep them generic.** Real table names, column names, system names and measured figures
tied to an identifiable client belong in a project adapter or the engagement's own
artifacts — never in this skill. Genericize a worked example with invented names before it
goes in; a method that only makes sense if you know the client is not a method.
