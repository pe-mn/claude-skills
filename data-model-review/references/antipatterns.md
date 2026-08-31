# Named anti-patterns

Detection heuristic, why it bites, and the remedy. The names matter: "this is Karwin's
*Polymorphic Associations*" lands where "the foreign keys look odd" does not, because a
named pattern with a citation is arguable and an impression is not.

The spine is `SRC-KAR-SAP1`, whose chapter titles are its taxonomy. Where a rule id
appears, the mechanical check lives in `scripts/checks.py`.

---

## Logical design (Karwin part I)

### Jaywalking — `REL-001`
**Heuristic:** a text column named as a collection (`tag_list`, `role_ids`, `member_codes`)
with no foreign key.
**Why:** a comma-separated list of ids is a many-to-many relationship with no constraint,
no index and no join. `LIKE '%,7,%'` also matches 17 and 70, so membership is wrong in
both directions and looks like it works.
**Remedy:** a junction table with real foreign keys.

### Naive Trees — `INT-004`
**Heuristic:** a self-referencing FK with no check constraint against cycles and no
closure table or materialised path alongside.
**Why:** an adjacency list is fine; an unguarded one is a recursive query waiting to hang.
One data-entry error makes A the parent of B and B the parent of A.
**Remedy:** a cycle-preventing constraint or trigger. For read-heavy deep hierarchies, add
a closure table or path column *alongside* the adjacency list.

### ID Required — `KEY-003`
**Heuristic:** a single numeric or identity primary key that is the table's *only*
uniqueness assertion.
**Why:** the most common way a schema that looks correct admits duplicates. The surrogate
guarantees rows are distinct, which is not the same as guaranteeing the business is
distinct. The same customer loads twice with two ids; both are valid rows; every count is
wrong; merging them later means rewriting every child FK.
**Remedy:** a unique constraint on the business key alongside the surrogate. If no
business key exists, that is the finding — the entity has no identity.
**Not this:** a surrogate key is not itself the anti-pattern. Kimball *requires* one on a
Type 2 dimension. The anti-pattern is the surrogate *displacing* the business key.

### Keyless Entry — `KEY-002`, `INT-001`
**Heuristic:** no primary key at all; or a column named and typed like a key, whose stem
names a real table with a key, and no FK constraint.
**Why:** without a key the table is a bag, not a relation — a retried load inserts every
row twice and nothing stops it. Without an FK, a deleted parent orphans its children, a
later inner join drops them, and a report loses rows nobody can account for.
**Remedy:** declare them. Where a constraint genuinely cannot exist — cross-database,
deliberate staging tolerance — record the decision and the compensating check, so the
absence is a choice on the record rather than an omission.

### Entity-Attribute-Value — `STR-001`
**Heuristic:** an entity reference, an attribute-name column, and a value column, in a
narrow table.
**Why:** the schema moves into the data, so the database can enforce nothing — no type,
no requiredness, no referential integrity on any attribute. A required attribute is simply
absent for some rows and no constraint notices.
**Remedy:** promote known attributes to real columns. Where extension is genuinely
open-ended, isolate it — a typed side table per attribute family, or a JSON column with a
validating schema — so the core stays enforceable.

### Polymorphic Associations — `INT-002`
**Heuristic:** a `(*_type, *_id)` pair, or `(entity_name, entity_id)`.
**Why:** the referenced table is a runtime value, so no foreign key can be declared. A row
references parent 42 in a table with no row 42 and nothing detects it — the join returns
nothing, so the record is invisible rather than erroneous.
**Remedy:** an exclusive-arc set of real nullable FKs with a check constraint permitting
exactly one, or a common supertype table that every target specialises so one real FK
works.

### Multicolumn Attributes — `STR-003`, `EVO-001`
**Heuristic:** three or more columns sharing a stem with a numeric suffix
(`address1..3`, `phone_1..4`); or placeholder columns (`spare1`, `udf3`, `attribute12`).
**Why:** a one-to-many relationship flattened into a fixed number of slots. Searching
means OR-ing across every slot and the N+1th value has nowhere to go. Placeholders are
worse: their meaning is set by convention outside the database, so two teams use `spare2`
for different things and a consolidation query treats them as one column.
**Remedy:** a child table with a type or sequence discriminator. For genuine open
extension, a typed extension table or validated JSON.

### Metadata Tribbles — `STR-004`
**Heuristic:** tables differing only by a year, month or quarter suffix.
**Why:** data values in object names. Every query and DDL change enumerates them, and a
cross-period query silently omits the newest table because nobody updated the `UNION`.
**Remedy:** one table, partitioned by the period column.

---

## Physical design (Karwin part II)

### Rounding Errors — `TYP-003`, `KEY-006`
**Heuristic:** a monetary column, or a key column, in `FLOAT`, `REAL` or
`DOUBLE PRECISION`.
**Why:** binary floating point cannot represent 0.1 exactly. A sum of a thousand invoice
lines is off by a few cents, the ledger does not balance, and the difference is not
reproducible because it depends on summation order. In a key, two ids that differ compare
equal.
**Remedy:** `NUMERIC`/`DECIMAL` with explicit precision and scale, or integer minor units.

### 31 Flavors — `REF-005`
**Heuristic:** five or more literal values in a `CHECK ... IN (...)`, or a long enum type.
**Why:** adding a value becomes a schema migration. The new status is needed on Friday and
the row that needed it is entered wrongly meanwhile.
**Remedy:** move genuinely volatile lists to a reference table. Keep `CHECK` for lists
that are stable by nature — a two-value flag, a fixed regulatory code list. This is a
judgement about volatility, not a blanket rule.

### Index Shotgun — `PER-002`
**Heuristic:** more than eight indexes on one table, or two indexes sharing a leading
column.
**Why:** indexing by hope. Writes slow measurably while the redundant indexes are never
chosen by the planner — a continuous, invisible cost.
**Remedy:** keep the indexes a named access path needs. Drop those whose leading column a
wider index already covers.

---

## Beyond Karwin

### Blanket soft delete — `TEM-003`, `TEM-004`, `TEM-005`
**Heuristic:** a delete flag on some comparable tables and not others; or a unique
constraint that ignores the delete flag.
**Why (`SRC-SOFTDEL`):** soft deletion systematically misleads the database. Foreign keys
can no longer express "this parent exists". Unique constraints stop matching intent — a
user who deletes their account cannot re-register with the same email, and that bug is
reported as a login problem and diagnosed for a week. The flag leaks into nearly every
query, and forgetting it produces silently wrong results rather than an error.
**Remedy:** decide per aggregate, write the decision down, apply it to every table in
that aggregate. Make unique constraints partial (`unique WHERE deleted_at IS NULL`), or
move deleted rows to a separate relation, or use the platform's temporal tables.
**Not this:** soft deletion chosen deliberately for a stated need is legitimate. The
*blanket* policy is the anti-pattern.

### Sentinel for unknown — `NUL-001`, `NUL-003`
**Heuristic:** `DEFAULT -1`, `'N/A'`, `'UNKNOWN'`, `'1900-01-01'`, `'9999-12-31'`; or
`NOT NULL` with a default that means absence.
**Why (`SRC-OMOP-CONV`):** OMOP states it directly — a field with no source value should
be NULL, not zero. A sentinel participates in aggregates and joins as though it were
real, so `AVG()` returns a plausible number that is not the average of anything. Worse,
`NOT NULL DEFAULT 'UNKNOWN'` launders absence into presence: a completeness metric reads
100% because every row has a value, and every value is the default.
**Remedy:** NULL for unknown. Where a real "not applicable" member is needed, model it as
a reference-data row with a documented meaning.
**Careful:** a bare `0` is not automatically a sentinel. `credit_limit NOT NULL DEFAULT 0`
means no credit, and flagging it is a confident false positive. The check only treats `0`
as a sentinel in a key or reference column, which is exactly where OMOP asserts it.

### One generic lookup table — `REF-002`
**Heuristic:** a discriminator column (`domain_type_id`, `list_name`, `code_type`) plus
value columns, often named `DOMAIN_DATA`, `LOOKUP`, `CODES` or `LOV`.
**Why:** EAV applied to reference data. No foreign key can point at a *subset* of it, so
no column can be constrained to the right code list. An order status column accepts a
country code — it resolves, joins, and displays as a country in a status field.
**Remedy:** one table per code list, each referenced by a real FK. Where the volume of
tiny tables is genuinely the problem, constrain per column with a `CHECK` or an FK to a
typed view.

### Label as identity — `REF-003`, `REF-004`
**Heuristic:** a lookup table with a surrogate id and a label but no stable code column;
or code and display text in one column.
**Why (`SRC-OMOP-CONV`):** the string a user sees and the token a system joins on have
different lifecycles. Someone fixes a typo in a status label and every stored reference
and report filter matching on it breaks at once — and afterwards there is no way to tell
whether this is the same concept as the one in last year's extract.
**Remedy:** an immutable code, unique and never edited, separate from a mutable label.
Join on the code, display the label.

### Overlapping effective dates — `TEM-005`
**Heuristic:** a `valid_from`/`valid_to` pair with no exclusion constraint and no unique
constraint including the period start.
**Why (`SRC-SQL2011`):** SQL:2011 provides `WITHOUT OVERLAPS` for exactly this. Two
versions of a price are simultaneously valid on the same day, the lookup returns whichever
the optimiser reaches first, and the invoiced amount is non-deterministic.
**Remedy:** an exclusion or `WITHOUT OVERLAPS` constraint on (business key, period). If
the platform lacks it, a trigger — and say that is what you did.

### Type 2 dimension keyed on its natural key — `KEY-008`
**Heuristic:** an effective-dated period plus a single natural-key primary key.
**Why (`SRC-KIM-DMT`):** surrogate keys exist so a dimension can hold several rows for one
natural key over time. The second version violates the primary key, so the load fails or
overwrites — turning an intended Type 2 into a Type 1 and destroying the history it was
built to keep.
**Remedy:** surrogate PK, natural key as a non-unique indexed column, effective dates, and
a current-row flag.

### Centipede fact table — `REL-003`
**Heuristic:** more than twenty dimension keys on a fact table.
**Why (`SRC-KIM-DMT`):** usually hierarchy levels modelled as separate dimensions. Query
performance collapses and the model becomes unreadable, so analysts build their own
extracts and the conformed dimensions stop being conformed.
**Remedy:** collapse hierarchy levels into their natural dimensions; junk dimensions for
low-cardinality flags.

### Fan-out on sibling children — `REL-004`
**Heuristic:** two one-to-many children of the same parent aggregated across one join.
**Why:** joining them multiplies rows before aggregation. Three children in A and four in
B produce twelve rows, and summing either measure gives a number several times too
large — and a plausible one.
**Remedy:** aggregate each child separately then join the aggregates (Kimball's multipass
SQL), or a bridge table with an allocation factor.

### Readable passwords — `GOV-002`, `MDX-009`
**Heuristic:** a column named `password`, `secret`, `pin`, `token` in a plain text type.
**Why:** recoverable by anyone who can read the table or a backup of it. One support
query exposes every user's password at once.
**Remedy:** a salted hash, never the password. In Mendix, the `Hashed string` type. For
tokens and secrets, a secret store rather than a table column.

### Asymmetric or unbounded localisation — `LOC-001`, `LOC-002`
**Heuristic:** parallel language columns beyond two languages; or a `*_ar` with no `*_en`
where the model uses both elsewhere.
**Why (`SRC-I18N-DB`):** parallel columns are acceptable only while the language set is
small and fixed, because each new language is a schema change touching every table
carrying a label, plus every view and loader over them. And an asymmetric pair means some
screens render in one language and not the other, with no constraint that would have
caught it at build time.
**Remedy:** a translation table keyed by (entity, attribute, language) past two languages.
Constrain both sides of a pair to be present together where the label is required at all.

### Two writable calendars — `LOC-003`, `LOC-004`
**Heuristic:** a Hijri date with no Gregorian column to anchor it; or both stored as
independently writable columns with no derivation.
**Why (`SRC-HIJRI`):** two writable representations of one instant diverge, and nothing
says which is right. Compounded by the fact that generic Hijri algorithms differ from the
Umm al-Qura table used for official dates — so a document printed from the record can
carry a date that does not match the register.
**Remedy:** Gregorian canonical in a real date type; Hijri derived, via a generated
column, a trigger, or a documented and tested derivation. Where official dates must match
exactly, name Umm al-Qura specifically.

### Formatted identifier as a number — `TYP-008`
**Heuristic:** a national id, phone number or account number in a numeric type.
**Why (`SRC-EID`):** these are digit strings, not quantities. An Emirates ID is
`784-YYYY-NNNNNNN-C` — the grouping carries meaning and the last digit is a check digit.
A leading zero is dropped on load, the identifier stops validating, and the row cannot be
matched against the authoritative register.
**Remedy:** a bounded character type with a `CHECK` on the pattern. If a check-digit rule
is claimed, **name the algorithm** — the Emirates ID check digit is not a plain Luhn over
all fifteen digits, and a model asserting otherwise is asserting something false.

---

## Mendix-specific

See `references/mendix.md` for the full picture. The four that matter most:

- **Delete behaviour left at "Keep associated object(s)"** on a composition — `MDX-002`.
  Orphan tolerance arrived at by not choosing.
- **No `Unique` validation rule anywhere** — `MDX-001`. Identity is undeclared, and the
  domain model diagram does not show it.
- **Inheritance deeper than two levels** — `MDX-004` (MXP009). Writes lock the
  generalisation, blocking retrieves across the hierarchy, and the decision is
  near-irreversible once production data exists.
- **Calculated attribute in a grid** — `MDX-007` (MXP001). A microflow per row per
  retrieve, invisible in the diagram.
