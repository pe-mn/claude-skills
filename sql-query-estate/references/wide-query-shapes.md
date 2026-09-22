# Wide query shapes — carrying many facts in one statement

Substitute your own schema and table names. The migration-control names here are real —
`EMS2_TGT` (a landing schema), `MIG_MASTER_TABLE` (the driver table) and `MIG_TABLE_LOG`
(the run log) — because a skeleton reads better against a concrete driver than against a
placeholder, and these are infrastructure rather than anyone's data. The business tables
(`SRC.ORDERS`, `SRC.CUSTOMER`, `SRC.SHIPMENT`) are invented stand-ins.

Engagement-specific facts — which control row carries which patch, what a particular count
settled, which legacy schema the extracts read — belong in a project adapter, never here.

The shapes exist because of the channel limits in `SKILL.md` §4 — one statement, a row cap
on the display, a string-aggregation ceiling. Each one trades *rows* for *width*, which is
the right trade whenever a round trip costs more than a column.

---

## 1. The check-suite — several yes/no questions, one statement

The workhorse. One row per check, a stable label, a number, and a detail string. Fits a
10-row grid, reads like a report, and a human can act on it without asking you what it
means.

```sql
SELECT 'A ROWS ARMED'          AS CHK,
       TO_CHAR(COUNT(*))       AS N,
       NVL(LISTAGG(ID, ' ') WITHIN GROUP (ORDER BY ID), 'none') AS DETAIL
  FROM EMS2_TGT.MIG_MASTER_TABLE WHERE TRIM(ACTIVE_FLAG) = '1'
UNION ALL
SELECT 'B ARMED OUTSIDE KNOWN RANGE', TO_CHAR(COUNT(*)),
       NVL(LISTAGG(ID, ' ') WITHIN GROUP (ORDER BY ID), 'none')
  FROM EMS2_TGT.MIG_MASTER_TABLE
 WHERE TRIM(ACTIVE_FLAG) = '1' AND ID NOT BETWEEN 1000 AND 1999
UNION ALL
SELECT 'C TARGET TABLE MISSING', TO_CHAR(COUNT(*)),
       NVL(LISTAGG(m.TARGET_TABLE, ' ') WITHIN GROUP (ORDER BY m.ID), 'none')
  FROM EMS2_TGT.MIG_MASTER_TABLE m
 WHERE TRIM(m.ACTIVE_FLAG) = '1'
   AND NOT EXISTS (SELECT 1 FROM ALL_TABLES t
                    WHERE t.OWNER = m.TARGET_SCHEMA AND t.TABLE_NAME = m.TARGET_TABLE)
UNION ALL
SELECT 'D RUN STILL OPEN', TO_CHAR(COUNT(*)),
       NVL(LISTAGG(TO_CHAR(ID), ' ') WITHIN GROUP (ORDER BY ID), 'none')
  FROM EMS2_TGT.MIG_TABLE_LOG WHERE STATUS = 'In Progress'
ORDER BY 1
```

**Rules that make it work.**

- **Every branch returns the same types.** A compound query will not mix them, and mixing
  a national-character expression with a plain literal raises a character-set error in
  Oracle. `TO_CHAR` everything, including counts.
- **Label with a sort prefix** (`'A '`, `'B '`). `ORDER BY 1` then gives a stable order,
  and a compound query accepts only *positional* `ORDER BY` — `ORDER BY CHK` is an error.
  Wrap in `SELECT * FROM (...)` if you need to sort by an expression.
- **Three columns, always the same three.** One loader ingests every suite; a human learns
  the shape once.
- **`NVL` every aggregate that can be empty**, or an all-clear check returns `NULL` and
  looks like a failure.
- **Keep it under the row cap.** Six to eight checks is the sweet spot.

### The verdict variant

When the answer is a judgement rather than a number, make the statement do the judging.
The reader should not have to remember which direction is good.

```sql
SELECT 'A GUARD CLAUSE REMOVED' AS CHK,
       CASE WHEN EXTRACT_QUERY LIKE '%SOME_FRAGMENT%'
            THEN 'FAIL - reverted' ELSE 'PASS' END AS VERDICT,
       'len=' || TO_CHAR(LENGTH(EXTRACT_QUERY)) AS DETAIL
  FROM EMS2_TGT.MIG_MASTER_TABLE WHERE ID = 9001
UNION ALL ...
```

This turns a documented manual step ("after a reseed, check that rows 9001 and 3065 still
carry their patches") into something runnable. Any procedure written as prose in a runbook
is a candidate.

---

## 2. Bucket-and-name — a census that also tells you which members

`GROUP BY` alone gives counts; you then need a second query to find out *which*. Put a
`LISTAGG` in the same statement and you never need the second.

```sql
SELECT CASE WHEN c.N = l.EXPECTED THEN 'A MATCH'
            WHEN c.N = 0          THEN 'C EMPTY'
            ELSE                       'B MISMATCH' END AS BUCKET,
       COUNT(*)   AS TABLES_,
       SUM(c.N)   AS ROWS_,
       LISTAGG(CASE WHEN c.N <> l.EXPECTED
                    THEN c.T || '(' || TO_CHAR(c.N) || '/' || TO_CHAR(l.EXPECTED) || ')'
               END, ' ') WITHIN GROUP (ORDER BY c.T) AS OFFENDERS
  FROM (...) c JOIN (...) l ON ...
 GROUP BY CASE WHEN c.N = l.EXPECTED THEN 'A MATCH'
               WHEN c.N = 0          THEN 'C EMPTY'
               ELSE                       'B MISMATCH' END
 ORDER BY 1
```

The `CASE` inside `LISTAGG` returning `NULL` for the healthy rows is deliberate — the
"A MATCH" bucket names nothing, the offending buckets name everything. Three rows out,
complete information.

**Watch the aggregation ceiling.** String aggregation raises an error past ~4000 bytes
rather than truncating. Three defences, in order of preference:

1. Aggregate something short — an id, not a qualified name.
2. Use the overflow clause where the version supports it:
   `LISTAGG(x, ' ' ON OVERFLOW TRUNCATE '...' WITHOUT COUNT)`.
3. Accept it: when the list is of things expected to be *empty*, an overflow is itself the
   finding. Say so in the expected-result note.

---

## 3. Multi-fact projection — many unrelated scalars, one row

When the facts do not share a shape, put each in its own scalar subquery.

```sql
SELECT (SELECT COUNT(*) FROM SRC.ORDERS   WHERE STATUS = 'OPEN') AS OPEN_ORDERS,
       (SELECT COUNT(*) FROM SRC.CUSTOMER WHERE CREATED > DATE '2020-01-01') AS NEW_CUSTOMERS,
       (SELECT MAX(SHIP_DATE) FROM SRC.SHIPMENT) AS LAST_SHIPMENT,
       USER AS CONNECTED_AS,
       SYS_CONTEXT('USERENV', 'DB_NAME') AS DB_NAME
  FROM DUAL
```

Compact and easy to write, but two cautions:

- **A wide single row is easy to clip** in a grid or a paste. Past four or five facts,
  prefer the check-suite (§1): rows survive copy-paste better than columns.
- **A scalar subquery containing an aggregate, inside an outer query that is itself a
  single-group aggregate, is an error** in Oracle. Keep the outer query `FROM DUAL`, or
  push the grouping into its own branch.

### The compact string variant

Where the channel returns one cell cleanly, concatenating is often the most readable
thing a human can paste back:

```sql
SELECT 'rows=' || TO_CHAR(COUNT(*))
    || ' distinct=' || TO_CHAR(COUNT(DISTINCT NATURAL_KEY))
    || ' dupes='    || TO_CHAR(COUNT(*) - COUNT(DISTINCT NATURAL_KEY))
    || ' nulls='    || TO_CHAR(COUNT(CASE WHEN NATURAL_KEY IS NULL THEN 1 END))
       AS RESULT
  FROM EMS2_TGT.ORDERS
```

**`dupes` is the point, not `rows`.** A total alone cannot see duplication: if two parents
each reference the same child, the count is unchanged and the duplicates are still there.
Any grain check must compare a count to a *distinct* count.

---

## 4. Dictionary-driven census — every table, exact counts, one statement

The highest-leverage shape in this file. You want a real `COUNT(*)` for every table
matching a pattern. Optimiser statistics (`ALL_TABLES.NUM_ROWS`) are stale and sometimes
absent, and dynamic SQL means a PL/SQL block, which many channels refuse.

Oracle's XML generator solves it inside a plain `SELECT`:

```sql
SELECT t.TABLE_NAME,
       x.PHYS AS PHYSICAL_ROWS,
       m.ID   AS CONTROL_ID,
       l.EXPECTED,
       CASE WHEN l.EXPECTED IS NULL  THEN 'D NEVER LOADED'
            WHEN x.PHYS = l.EXPECTED THEN 'A MATCH'
            WHEN x.PHYS = 0          THEN 'C EMPTY'
            ELSE                          'B MISMATCH' END AS VERDICT
  FROM ALL_TABLES t
  LEFT JOIN EMS2_TGT.MIG_MASTER_TABLE m
         ON m.TARGET_TABLE = t.TABLE_NAME AND TRIM(m.TARGET_SCHEMA) = 'EMS2_TGT'
  LEFT JOIN (SELECT TABLE_NAME,
                    MAX(LOADED_ROWS) KEEP (DENSE_RANK LAST ORDER BY RUN_ID) AS EXPECTED
               FROM EMS2_TGT.MIG_TABLE_LOG WHERE STATUS = 'Success' GROUP BY TABLE_NAME) l
         ON l.TABLE_NAME = TRIM(m.SOURCE_SCHEMA) || '.' || TRIM(m.OBJECT_NAME),
       XMLTABLE('/ROWSET/ROW'
                PASSING XMLTYPE(DBMS_XMLGEN.GETXML(
                          'SELECT COUNT(*) C FROM EMS2_TGT."' || t.TABLE_NAME || '"'))
                COLUMNS PHYS NUMBER PATH 'C') x
 WHERE t.OWNER = 'EMS2_TGT'
   AND t.TABLE_NAME LIKE 'STG\_%' ESCAPE '\'
 ORDER BY t.TABLE_NAME
```

**Why it is worth the ugliness.** It replaces N per-table queries with one, and the
comparison that matters — physical rows against what the log *claims* was loaded — becomes
a column instead of a manual reconciliation. Run once, it establishes the entire state of
a load: what matched, what never ran, what is empty, what disagrees.

**Notes.**

- `DBMS_XMLGEN.GETXML` runs the inner text as SQL. It is a **read-only census over names
  taken from the data dictionary**; never build it from user input.
- Quote the table name (`"' || t.TABLE_NAME || '"`) so unusual identifiers survive.
- `COUNT(*)` always returns a row, so the generator always returns a document — empty
  tables still appear.
- `KEEP (DENSE_RANK LAST ORDER BY ...)` picks the value from the *latest* run without a
  self-join or a window, so a re-run does not double-count.
- Requires `EXECUTE` on the XML generator package (normally public) and `SELECT` on the
  tables. It is slower than reading statistics — it genuinely scans — so scope the
  `LIKE` pattern.
- Other engines have their own idiom for this; the principle transfers even where the
  syntax does not.

---

## 5. Coverage and orphan checks without a second query

**Does every child resolve to a parent?**

```sql
SELECT 'child=' || TO_CHAR(COUNT(*))
    || ' orphans=' || TO_CHAR(COUNT(CASE WHEN p.ID IS NULL THEN 1 END)) AS RESULT
  FROM EMS2_TGT.SHIPMENT c
  LEFT JOIN EMS2_TGT.ORDERS p ON TO_CHAR(p.ID) = TO_CHAR(c.ORDER_ID)
```

`TO_CHAR` on both sides is not paranoia: landed columns are frequently a different type or
character set from the source key they came from, and comparing them raw raises a
character-set error or an invalid-number error on the first bad value.

**Did any column arrive entirely empty?** `COUNT(col)` skips nulls, so `COUNT(col) = 0`
means every row is null. One statement covers a whole table:

```sql
SELECT 'ORDERS' AS T, COUNT(*) AS N,
       RTRIM(CASE WHEN COUNT(ORDER_NO)  = 0 THEN 'ORDER_NO '  END ||
             CASE WHEN COUNT(CUSTOMER_ID)= 0 THEN 'CUSTOMER_ID ' END ||
             CASE WHEN COUNT(TOTAL)     = 0 THEN 'TOTAL '     END) AS ALL_NULL_COLUMNS
  FROM EMS2_TGT.ORDERS
```

**Did anything truncate at the declared width?** Rows sitting *exactly* on the declared
length are the signature — a genuine distribution rarely piles up on the boundary:

```sql
SELECT 'ORDERS.NOTES' AS COL, 200 AS CUT_AT, COUNT(*) AS N,
       COUNT(NOTES) AS POPULATED,
       SUM(CASE WHEN LENGTH(NOTES) = 200 THEN 1 ELSE 0 END) AS AT_THE_LIMIT,
       MAX(LENGTH(NOTES)) AS MAX_LEN
  FROM EMS2_TGT.ORDERS
```

**Were decimals preserved?** A pipeline that silently rounds looks identical to a source
with no decimals — until you compare:

```sql
SELECT 'rows=' || TO_CHAR(COUNT(*))
    || ' with_decimals=' || TO_CHAR(COUNT(CASE WHEN AMOUNT <> ROUND(AMOUNT, 0) THEN 1 END))
    || ' max=' || TO_CHAR(MAX(AMOUNT)) AS RESULT
  FROM EMS2_TGT.ORDERS
```

---

## 6. Reading a long value through a narrow grid

When a single column is longer than the display will show, chunk it in the query rather
than asking for it repeatedly:

```sql
SELECT m.OBJECT_NAME AS T, c.n AS SEQ,
       SUBSTR(m.BIG_TEXT, (c.n - 1) * 600 + 1, 600) AS CHUNK
  FROM EMS2_TGT.MIG_MASTER_TABLE m
 CROSS JOIN (SELECT LEVEL n FROM DUAL CONNECT BY LEVEL <= 7) c
 WHERE m.ID IN (9001, 9002)
   AND (c.n - 1) * 600 < LENGTH(m.BIG_TEXT)
 ORDER BY m.ID, c.n
```

Keep `ids × chunks` under the row cap or the tail is silently lost — which looks exactly
like a value that ends there.

---

## 7. Verifying a change landed, when the writer reports nothing

Where a channel does not return an affected-row count, a write that matched nothing is
indistinguishable from one that worked. A search-and-replace that matched no text
*succeeds*. So every write is followed by a read-back — and the read-back must check the
right thing:

```sql
-- length is NOT enough: a doubled function call costs five bytes and hides in a length check
SELECT ID,
       LENGTH(BIG_TEXT) AS LEN,
       (LENGTH(BIG_TEXT) - LENGTH(REPLACE(BIG_TEXT, '(', '')))
     - (LENGTH(BIG_TEXT) - LENGTH(REPLACE(BIG_TEXT, ')', ''))) AS PAREN_BALANCE,
       CASE WHEN BIG_TEXT LIKE '%EXPECTED_FRAGMENT%' THEN 'PRESENT' ELSE 'ABSENT' END AS FRAG
  FROM EMS2_TGT.MIG_MASTER_TABLE WHERE ID IN (9001, 9002) ORDER BY ID
```

Paren balance catches a whole class of malformed edit that a length comparison misses.
Fingerprinting a whole range at once — `LISTAGG(ID || ':' || LENGTH(t) || ':' ||
SUBSTR(STANDARD_HASH(t, 'MD5'), 1, 8))` — compares the live state against a generated file
in one row, and catches a same-length different-text edit that length alone cannot.
