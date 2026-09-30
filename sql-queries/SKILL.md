---
name: sql-queries
description: Write correct, performant SQL in any dialect (Oracle, PostgreSQL, Snowflake, BigQuery, Redshift, Databricks) and interrogate a database without asking the same question twice. Use when writing, optimizing or translating queries, building analytical SQL with CTEs, window functions or aggregations - and whenever you are about to write SQL to FIND SOMETHING OUT: profiling a legacy schema, verifying a data load or migration run, investigating a defect, answering "how many / how often / does this ever happen", or auditing what a batch job did. Also use when someone else runs your queries (a time-boxed DB window, a paste-back loop, a pipeline script activity) and each round trip is expensive, when a number may already have been measured, or when query sprawl has set in. Covers dialect syntax and patterns, the widest statement that still answers the question (one query for a hundred facts), the shapes that carry many facts, the channel limits that force them, and keeping a query estate so results become citable evidence. NOT for designing a schema or application/ETL code.
---

<!-- Derivative Work of Anthropic's `data` plugin skill `sql-queries` (v1.1.0, Apache-2.0 - LICENSE and NOTICE beside this
     file). MODIFIED 2026-09-30: the upstream body is kept verbatim and in order; added the merged trigger description, the
     "SQL query estate" method (sections 1-6, the reference table, the retrospective, references/), an Oracle dialect
     section and Oracle entries under "Error Handling and Debugging". -->

# SQL Queries Skill

Write correct, performant, readable SQL across all major data warehouse dialects.

This skill has two jobs, and most real tasks need both:

- **Writing SQL** - the dialect reference, the common analytical patterns and the error list below. Reach for these when the
  question is settled and the statement is the work.
- **Finding something out** - the query estate method that follows. Reach for it *before* the statement, whenever the SQL exists
  to answer a question: what is in this schema, did the load land, how often does this happen, what did the batch do. It decides
  what to ask and how wide, so that one round trip settles a hundred facts and the answer is still citable next month.

Read the method first when a question is open; read the dialect sheet first when the question is closed and only the syntax is
in doubt. The checklist in section 6 joins the two.

---

## SQL query estate

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
- [ ] Nested derived-column views: is every level unmergeable (a ROWNUM column) or a CTE the
      optimizer materialises? A merged chain can exhaust compile memory on any row count
      (`references/running-queries.md` §3, ORA-04036).
- [ ] Testing a DELIVERABLE statement (a load extract)? Read it byte for byte out of the
      deliverable and wrap it as a flat count - never re-type it; one heavy extract per statement
      (`references/wide-query-shapes.md` §8).
- [ ] If a human runs it: is it numbered `N of M`, pasted inline in full, self-reporting
      its row count, and stamped with its environment? (`references/running-queries.md`)
- [ ] When the answer comes back: where will it be written down? If the answer is "in this
      conversation", it is not written down.
- [ ] The dialect basics that fail only at run time: every column qualified with its table alias in a join, every division
      guarded with `NULLIF(denominator, 0)`, every cross-type comparison cast explicitly, every non-aggregated column in the
      `GROUP BY` (the error list at the end of this file, read before the round trip, not after it).

---

## Dialect-Specific Reference

### PostgreSQL (including Aurora, RDS, Supabase, Neon)

**Date/time:**
```sql
-- Current date/time
CURRENT_DATE, CURRENT_TIMESTAMP, NOW()

-- Date arithmetic
date_column + INTERVAL '7 days'
date_column - INTERVAL '1 month'

-- Truncate to period
DATE_TRUNC('month', created_at)

-- Extract parts
EXTRACT(YEAR FROM created_at)
EXTRACT(DOW FROM created_at)  -- 0=Sunday

-- Format
TO_CHAR(created_at, 'YYYY-MM-DD')
```

**String functions:**
```sql
-- Concatenation
first_name || ' ' || last_name
CONCAT(first_name, ' ', last_name)

-- Pattern matching
column ILIKE '%pattern%'  -- case-insensitive
column ~ '^regex_pattern$'  -- regex

-- String manipulation
LEFT(str, n), RIGHT(str, n)
SPLIT_PART(str, delimiter, position)
REGEXP_REPLACE(str, pattern, replacement)
```

**Arrays and JSON:**
```sql
-- JSON access
data->>'key'  -- text
data->'nested'->'key'  -- json
data#>>'{path,to,key}'  -- nested text

-- Array operations
ARRAY_AGG(column)
ANY(array_column)
array_column @> ARRAY['value']
```

**Performance tips:**
- Use `EXPLAIN ANALYZE` to profile queries
- Create indexes on frequently filtered/joined columns
- Use `EXISTS` over `IN` for correlated subqueries
- Partial indexes for common filter conditions
- Use connection pooling for concurrent access

---

### Snowflake

**Date/time:**
```sql
-- Current date/time
CURRENT_DATE(), CURRENT_TIMESTAMP(), SYSDATE()

-- Date arithmetic
DATEADD(day, 7, date_column)
DATEDIFF(day, start_date, end_date)

-- Truncate to period
DATE_TRUNC('month', created_at)

-- Extract parts
YEAR(created_at), MONTH(created_at), DAY(created_at)
DAYOFWEEK(created_at)

-- Format
TO_CHAR(created_at, 'YYYY-MM-DD')
```

**String functions:**
```sql
-- Case-insensitive by default (depends on collation)
column ILIKE '%pattern%'
REGEXP_LIKE(column, 'pattern')

-- Parse JSON
column:key::string  -- dot notation for VARIANT
PARSE_JSON('{"key": "value"}')
GET_PATH(variant_col, 'path.to.key')

-- Flatten arrays/objects
SELECT f.value FROM table, LATERAL FLATTEN(input => array_col) f
```

**Semi-structured data:**
```sql
-- VARIANT type access
data:customer:name::STRING
data:items[0]:price::NUMBER

-- Flatten nested structures
SELECT
    t.id,
    item.value:name::STRING as item_name,
    item.value:qty::NUMBER as quantity
FROM my_table t,
LATERAL FLATTEN(input => t.data:items) item
```

**Performance tips:**
- Use clustering keys on large tables (not traditional indexes)
- Filter on clustering key columns for partition pruning
- Set appropriate warehouse size for query complexity
- Use `RESULT_SCAN(LAST_QUERY_ID())` to avoid re-running expensive queries
- Use transient tables for staging/temp data

---

### BigQuery (Google Cloud)

**Date/time:**
```sql
-- Current date/time
CURRENT_DATE(), CURRENT_TIMESTAMP()

-- Date arithmetic
DATE_ADD(date_column, INTERVAL 7 DAY)
DATE_SUB(date_column, INTERVAL 1 MONTH)
DATE_DIFF(end_date, start_date, DAY)
TIMESTAMP_DIFF(end_ts, start_ts, HOUR)

-- Truncate to period
DATE_TRUNC(created_at, MONTH)
TIMESTAMP_TRUNC(created_at, HOUR)

-- Extract parts
EXTRACT(YEAR FROM created_at)
EXTRACT(DAYOFWEEK FROM created_at)  -- 1=Sunday

-- Format
FORMAT_DATE('%Y-%m-%d', date_column)
FORMAT_TIMESTAMP('%Y-%m-%d %H:%M:%S', ts_column)
```

**String functions:**
```sql
-- No ILIKE, use LOWER()
LOWER(column) LIKE '%pattern%'
REGEXP_CONTAINS(column, r'pattern')
REGEXP_EXTRACT(column, r'pattern')

-- String manipulation
SPLIT(str, delimiter)  -- returns ARRAY
ARRAY_TO_STRING(array, delimiter)
```

**Arrays and structs:**
```sql
-- Array operations
ARRAY_AGG(column)
UNNEST(array_column)
ARRAY_LENGTH(array_column)
value IN UNNEST(array_column)

-- Struct access
struct_column.field_name
```

**Performance tips:**
- Always filter on partition columns (usually date) to reduce bytes scanned
- Use clustering for frequently filtered columns within partitions
- Use `APPROX_COUNT_DISTINCT()` for large-scale cardinality estimates
- Avoid `SELECT *` -- billing is per-byte scanned
- Use `DECLARE` and `SET` for parameterized scripts
- Preview query cost with dry run before executing large queries

---

### Redshift (Amazon)

**Date/time:**
```sql
-- Current date/time
CURRENT_DATE, GETDATE(), SYSDATE

-- Date arithmetic
DATEADD(day, 7, date_column)
DATEDIFF(day, start_date, end_date)

-- Truncate to period
DATE_TRUNC('month', created_at)

-- Extract parts
EXTRACT(YEAR FROM created_at)
DATE_PART('dow', created_at)
```

**String functions:**
```sql
-- Case-insensitive
column ILIKE '%pattern%'
REGEXP_INSTR(column, 'pattern') > 0

-- String manipulation
SPLIT_PART(str, delimiter, position)
LISTAGG(column, ', ') WITHIN GROUP (ORDER BY column)
```

**Performance tips:**
- Design distribution keys for collocated joins (DISTKEY)
- Use sort keys for frequently filtered columns (SORTKEY)
- Use `EXPLAIN` to check query plan
- Avoid cross-node data movement (watch for DS_BCAST and DS_DIST)
- `ANALYZE` and `VACUUM` regularly
- Use late-binding views for schema flexibility

---

### Databricks SQL

**Date/time:**
```sql
-- Current date/time
CURRENT_DATE(), CURRENT_TIMESTAMP()

-- Date arithmetic
DATE_ADD(date_column, 7)
DATEDIFF(end_date, start_date)
ADD_MONTHS(date_column, 1)

-- Truncate to period
DATE_TRUNC('MONTH', created_at)
TRUNC(date_column, 'MM')

-- Extract parts
YEAR(created_at), MONTH(created_at)
DAYOFWEEK(created_at)
```

**Delta Lake features:**
```sql
-- Time travel
SELECT * FROM my_table TIMESTAMP AS OF '2024-01-15'
SELECT * FROM my_table VERSION AS OF 42

-- Describe history
DESCRIBE HISTORY my_table

-- Merge (upsert)
MERGE INTO target USING source
ON target.id = source.id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *
```

**Performance tips:**
- Use Delta Lake's `OPTIMIZE` and `ZORDER` for query performance
- Leverage Photon engine for compute-intensive queries
- Use `CACHE TABLE` for frequently accessed datasets
- Partition by low-cardinality date columns

---

### Oracle (11g through 19c / 23ai)

**Date/time:**
```sql
-- Current date/time (session time zone; DATE always carries a time part)
SYSDATE, SYSTIMESTAMP, CURRENT_DATE

-- Date arithmetic (DATE + number = days; DATE - DATE = days as a decimal)
date_column + 7
ADD_MONTHS(date_column, -1)
date_column - INTERVAL '1' HOUR
end_date - start_date

-- Truncate to period
TRUNC(created_on, 'MM')   -- 'IW' = ISO week, 'DD' = midnight of the day

-- Extract parts
EXTRACT(YEAR FROM created_on)
TO_CHAR(created_on, 'DY')  -- day name; TO_CHAR(..., 'D') is NLS-dependent

-- Format / parse
TO_CHAR(created_on, 'YYYY-MM-DD HH24:MI:SS')
TO_DATE('2024-01-15', 'YYYY-MM-DD')
```

**String functions:**
```sql
-- Concatenation (CONCAT takes exactly two arguments; NULL concatenates as empty)
first_name || ' ' || last_name

-- Pattern matching (LIKE is case-sensitive)
UPPER(column) LIKE '%PATTERN%'
REGEXP_LIKE(column, '^[0-9]+$')

-- String manipulation
SUBSTR(str, start, length), INSTR(str, sub), REGEXP_SUBSTR(str, pattern, 1, n)
LISTAGG(column, ', ') WITHIN GROUP (ORDER BY column)   -- raises ORA-01489 past 4000 bytes
LISTAGG(column, ', ' ON OVERFLOW TRUNCATE '...' WITH COUNT) WITHIN GROUP (ORDER BY column)   -- 12.2+
NVL(a, b), COALESCE(a, b, c), NVL2(a, if_not_null, if_null)
```

**Rows, nulls and the dictionary:**
```sql
-- Row limiting
SELECT ... FROM t ORDER BY x FETCH FIRST 10 ROWS ONLY                 -- 12c+
SELECT ... FROM (SELECT ... FROM t ORDER BY x) WHERE ROWNUM <= 10    -- any version; ROWNUM is assigned BEFORE ORDER BY in the same block

-- The empty string IS NULL: col = '' never matches
WHERE col IS NULL

-- A scalar needs a table
SELECT SYSDATE FROM DUAL

-- The data dictionary answers structure without touching the data
ALL_TAB_COLUMNS   (owner, table_name, column_name, data_type, nullable, num_nulls, num_distinct, sample_size)
ALL_CONSTRAINTS / ALL_CONS_COLUMNS   (constraint_type 'P' / 'R'; r_constraint_name = the FK's target key)
ALL_TAB_STATISTICS.NUM_ROWS   -- an optimizer STATISTIC sampled at gather time, not a count: COUNT(*) when the number matters
```

**Performance tips:**
- `EXPLAIN PLAN FOR <query>` then `SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY)` reads the plan without running the query
- Bind variables (`:id`) share cursors; a client that cannot bind substitutes text, so say so wherever the statement is handed over
- `/*+ hints */` are advice, and some channels strip comments before sending: a `ROWNUM` column is the portable way to stop view merging
- `DBMS_STATS.GATHER_TABLE_STATS` keeps the dictionary numbers honest (`ANALYZE ... COMPUTE STATISTICS` is deprecated for that)
- A function on the indexed column in a predicate (`TRUNC(created_on) = DATE '2024-01-15'`) disables the index: use a range instead
- One statement per round trip on a script channel: no trailing `;` after the last statement, no `/`, no `SET` commands

---

## Common SQL Patterns

### Window Functions

```sql
-- Ranking
ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC)
RANK() OVER (PARTITION BY category ORDER BY revenue DESC)
DENSE_RANK() OVER (ORDER BY score DESC)

-- Running totals / moving averages
SUM(revenue) OVER (ORDER BY date_col ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as running_total
AVG(revenue) OVER (ORDER BY date_col ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as moving_avg_7d

-- Lag / Lead
LAG(value, 1) OVER (PARTITION BY entity ORDER BY date_col) as prev_value
LEAD(value, 1) OVER (PARTITION BY entity ORDER BY date_col) as next_value

-- First / Last value
FIRST_VALUE(status) OVER (PARTITION BY user_id ORDER BY created_at ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
LAST_VALUE(status) OVER (PARTITION BY user_id ORDER BY created_at ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)

-- Percent of total
revenue / SUM(revenue) OVER () as pct_of_total
revenue / SUM(revenue) OVER (PARTITION BY category) as pct_of_category
```

### CTEs for Readability

```sql
WITH
-- Step 1: Define the base population
base_users AS (
    SELECT user_id, created_at, plan_type
    FROM users
    WHERE created_at >= DATE '2024-01-01'
      AND status = 'active'
),

-- Step 2: Calculate user-level metrics
user_metrics AS (
    SELECT
        u.user_id,
        u.plan_type,
        COUNT(DISTINCT e.session_id) as session_count,
        SUM(e.revenue) as total_revenue
    FROM base_users u
    LEFT JOIN events e ON u.user_id = e.user_id
    GROUP BY u.user_id, u.plan_type
),

-- Step 3: Aggregate to summary level
summary AS (
    SELECT
        plan_type,
        COUNT(*) as user_count,
        AVG(session_count) as avg_sessions,
        SUM(total_revenue) as total_revenue
    FROM user_metrics
    GROUP BY plan_type
)

SELECT * FROM summary ORDER BY total_revenue DESC;
```

### Cohort Retention

```sql
WITH cohorts AS (
    SELECT
        user_id,
        DATE_TRUNC('month', first_activity_date) as cohort_month
    FROM users
),
activity AS (
    SELECT
        user_id,
        DATE_TRUNC('month', activity_date) as activity_month
    FROM user_activity
)
SELECT
    c.cohort_month,
    COUNT(DISTINCT c.user_id) as cohort_size,
    COUNT(DISTINCT CASE
        WHEN a.activity_month = c.cohort_month THEN a.user_id
    END) as month_0,
    COUNT(DISTINCT CASE
        WHEN a.activity_month = c.cohort_month + INTERVAL '1 month' THEN a.user_id
    END) as month_1,
    COUNT(DISTINCT CASE
        WHEN a.activity_month = c.cohort_month + INTERVAL '3 months' THEN a.user_id
    END) as month_3
FROM cohorts c
LEFT JOIN activity a ON c.user_id = a.user_id
GROUP BY c.cohort_month
ORDER BY c.cohort_month;
```

### Funnel Analysis

```sql
WITH funnel AS (
    SELECT
        user_id,
        MAX(CASE WHEN event = 'page_view' THEN 1 ELSE 0 END) as step_1_view,
        MAX(CASE WHEN event = 'signup_start' THEN 1 ELSE 0 END) as step_2_start,
        MAX(CASE WHEN event = 'signup_complete' THEN 1 ELSE 0 END) as step_3_complete,
        MAX(CASE WHEN event = 'first_purchase' THEN 1 ELSE 0 END) as step_4_purchase
    FROM events
    WHERE event_date >= CURRENT_DATE - INTERVAL '30 days'
    GROUP BY user_id
)
SELECT
    COUNT(*) as total_users,
    SUM(step_1_view) as viewed,
    SUM(step_2_start) as started_signup,
    SUM(step_3_complete) as completed_signup,
    SUM(step_4_purchase) as purchased,
    ROUND(100.0 * SUM(step_2_start) / NULLIF(SUM(step_1_view), 0), 1) as view_to_start_pct,
    ROUND(100.0 * SUM(step_3_complete) / NULLIF(SUM(step_2_start), 0), 1) as start_to_complete_pct,
    ROUND(100.0 * SUM(step_4_purchase) / NULLIF(SUM(step_3_complete), 0), 1) as complete_to_purchase_pct
FROM funnel;
```

### Deduplication

```sql
-- Keep the most recent record per key
WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY entity_id
            ORDER BY updated_at DESC
        ) as rn
    FROM source_table
)
SELECT * FROM ranked WHERE rn = 1;
```

### Many facts in one statement

The funnel above is the general shape for *finding something out*: several yes/no or count questions folded into one pass
with `CASE` inside the aggregate, so one round trip returns every fact. `references/wide-query-shapes.md` extends it to the
check-suite with a verdict column, the bucket-and-name census (`LISTAGG` of the anomalous members), the multi-fact
projection, the dictionary-driven census that counts every table without dynamic SQL, and orphan / coverage checks that
need no second query.

## Error Handling and Debugging

When a query fails:

1. **Syntax errors**: Check for dialect-specific syntax (e.g., `ILIKE` not available in BigQuery, `SAFE_DIVIDE` only in BigQuery)
2. **Column not found**: Verify column names against schema -- check for typos, case sensitivity (PostgreSQL is case-sensitive for quoted identifiers)
3. **Type mismatches**: Cast explicitly when comparing different types (`CAST(col AS DATE)`, `col::DATE`)
4. **Division by zero**: Use `NULLIF(denominator, 0)` or dialect-specific safe division
5. **Ambiguous columns**: Always qualify column names with table alias in JOINs
6. **Group by errors**: All non-aggregated columns must be in GROUP BY (except in BigQuery which allows grouping by alias)

The Oracle errors that each cost a round trip when someone else runs the statement (the full list, with the shapes that avoid
them, is in `references/running-queries.md` §3):

7. **ORA-00904 invalid identifier**: the column or alias does not exist at that scope; Oracle reports only the first one, so validate every `table.column` against the dictionary before sending
8. **ORA-01722 invalid number**: a text column compared to a number, or free text cast; guard with `CASE WHEN VALIDATE_CONVERSION(x AS NUMBER) = 1 THEN TO_NUMBER(x) END` (12.2+) in the SELECT list, never a bare `TO_NUMBER` in the `WHERE` (view merging can run the cast before the filter)
9. **ORA-00937 not a single-group group function / ORA-00979 not a GROUP BY expression**: 00937 = an aggregate beside a raw expression with no `GROUP BY` (including a scalar aggregate subquery inside an outer single-group aggregate); 00979 = an expression missing from the `GROUP BY`, and a `ROWNUM` column in a grouped block is one
10. **ORA-12704 character set mismatch**: a `CASE` or `UNION` mixes NVARCHAR2 and VARCHAR2 branches; it is not the `||` operator, so wrap every national-character reference in `TO_CHAR`
11. **ORA-04036 PGA memory used by the instance exceeds PGA_AGGREGATE_LIMIT**: nested derived-column views merged into one plan; make each level unmergeable (a `ROWNUM` column) or a materialized CTE
12. **ORA-01489 result of string concatenation is too long**: `LISTAGG` past 4000 bytes; add `ON OVERFLOW TRUNCATE`, or return a count and a sample instead of the whole list
13. **ORA-01427 single-row subquery returns more than one row**: the scalar subquery is not unique on its key; prove the key first (`SELECT key, COUNT(*) ... GROUP BY key HAVING COUNT(*) > 1`)
14. **ORA-00933 / ORA-00911 on a one-statement channel**: almost always a trailing `;` or a second statement, not a syntax error in the statement itself

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
