# Source registry

Every rule in `scripts/rules.py` carries a `source` field that must resolve to an ID
below. `scripts/selftest.py` fails the build if a rule cites an ID that is not here, or
cites nothing. That is the mechanism that keeps the rubric honest: a rule with no
provenance cannot ship.

## Verification status

| Status | Meaning | May a rule cite it? |
|---|---|---|
| `VERIFIED` | Fetched and read during authoring. The summary below reflects what the source actually says. | Yes |
| `BOOK` | Canonical print source, cited by title/edition/ISBN. Not machine-fetchable. Rules citing a `BOOK` source restrict themselves to claims that are load-bearing and uncontroversial in that work. | Yes |
| `UNVERIFIED` | Could not be retrieved. Recorded here so the gap stays visible. | **No** |

If you extend the rubric, add the source here first. Prefer `VERIFIED`: fetch the page,
read it, and write down what it actually says rather than what you remember it saying.

---

## Scorecard frame

### SRC-HOB-SC — `BOOK`

Hoberman, Steve. *Data Model Scorecard: Applying the Industry Standard on Data Model
Quality*. Technics Publications, 2015. ISBN 978-1634620826.

Ten categories, each phrased as a question. Names and questions confirmed against
<https://tedamoh.com/en/academy/secret-spice/coaching/295-why-use-the-data-model-scorecard>
(`VERIFIED`):

1. **Correctness** — Does the model meet the requirements?
2. **Completeness** — Is the model complete, but without "gold plating"?
3. **Scheme** — Does the model correspond to its schema (conceptual/logical/physical)?
4. **Structure** — Is the model consistent, does it have integrity, does it follow the basic rules?
5. **Abstraction** — Is the balance between generalization and specialization right?
6. **Standards** — Does the model follow the available rule and naming standards?
7. **Readability** — Is the model presented in a readable layout?
8. **Definitions** — Are the definitions correct, complete and unambiguous?
9. **Consistency** — Does the model use the same structure and terminology throughout?
10. **Data** — Has a data profile been created, and do the attributes correspond to reality?

> **The weights are ours, not Hoberman's.** The scorecard totals 100, but the
> per-category point allocation is published only inside the book and could not be
> verified. `assets/weights.json` therefore carries **our** weights, labelled as such.
> Never attribute those numbers to Hoberman in a report.

### SRC-SIMSION — `BOOK`

Simsion, Graeme and Witt, Graham. *Data Modeling Essentials*, 3rd ed. Morgan Kaufmann,
2004. ISBN 978-0126445510. Section 1.6, "What makes a good data model?" — quality
criteria including Completeness, Non-Redundancy, Enforcement of Business Rules, Data
Reusability, Stability and Flexibility, Elegance, Communication, Integration. Chapter 16
covers criteria specific to warehouse and mart models.

### SRC-DAMA — `BOOK`

DAMA International. *DAMA-DMBOK: Data Management Body of Knowledge*, 2nd ed. Technics
Publications, 2017. Chapter 5, "Data Modeling and Design". Governance, stewardship,
classification and metadata expectations.

---

## Relational and normalization

### SRC-CODD-70 — `BOOK`

Codd, E. F. "A Relational Model of Data for Large Shared Data Banks."
*Communications of the ACM* 13(6), 1970.

### SRC-DATE — `BOOK`

Date, C. J. *An Introduction to Database Systems*, 8th ed. Addison-Wesley, 2003. Normal
forms 1NF through 5NF/BCNF and their justification.

### SRC-KAR-SAP1 — `VERIFIED`

Karwin, Bill. *SQL Antipatterns, Volume 1: Avoiding the Pitfalls of Database
Programming*. Pragmatic Bookshelf.
<https://pragprog.com/titles/bksap1/sql-antipatterns-volume-1/>

Chapter list confirmed. Logical design: **Jaywalking** (comma-separated lists),
**Naive Trees** (adjacency list misuse), **ID Required** (surrogate key on everything),
**Keyless Entry** (no FK constraints), **Entity-Attribute-Value**, **Polymorphic
Associations**, **Multicolumn Attributes** (tag1, tag2, tag3), **Metadata Tribbles**
(table-per-year). Physical design: **Rounding Errors** (FLOAT for money), **31 Flavors**
(enum hard-coded in DDL), **Phantom Files**, **Index Shotgun**. Queries: **Fear of the
Unknown** (NULL mishandling), **Ambiguous Groups**, **Random Selection**, **Poor Man's
Search Engine**, **Spaghetti Query**, **Implicit Columns**. Application: **Readable
Passwords**, **SQL Injection**, **Pseudokey Neat-Freak**, **See No Evil**, **Diplomatic
Immunity**, **Standard Operating Procedures**.

---

## Dimensional and warehouse

### SRC-KIM-DMT — `VERIFIED`

Kimball Group. "Dimensional Modeling Techniques."
<https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/>

Roughly 100 named techniques. Load-bearing here: the four-step design process;
**Grain**; dimension **surrogate keys**; natural, durable and supernatural keys;
degenerate dimensions; denormalized flattened dimensions; junk dimensions; snowflaked
and outrigger dimensions; conformed dimensions and the enterprise bus matrix;
transaction, periodic snapshot, accumulating snapshot, factless and consolidated fact
tables; additive, semi-additive and non-additive facts; nulls in fact tables; **SCD
Types 0 through 7** (Retain original, Overwrite, Add new row, Add new attribute, Add
mini-dimension, Mini-dimension plus Type 1 outrigger, Type 1 attributes on a Type 2
dimension, Dual Type 1 and Type 2); fixed-depth, slightly ragged and ragged
hierarchies; **centipede fact table**; multiple currency facts; multiple units of
measure; multivalued dimensions and bridge tables; multiple time zones; audit
dimensions; supertype and subtype schemas for heterogeneous products.

### SRC-KIM-DWT — `BOOK`

Kimball, Ralph and Ross, Margy. *The Data Warehouse Toolkit*, 3rd ed. Wiley, 2013.
ISBN 978-1118530801. The narrative behind SRC-KIM-DMT.

### SRC-INM — `BOOK`

Inmon, W. H. *Building the Data Warehouse*, 4th ed. Wiley, 2005. Corporate Information
Factory: a normalized enterprise warehouse feeding departmental marts.

### SRC-DV2 — `BOOK`

Linstedt, Dan and Olschimke, Michael. *Building a Scalable Data Warehouse with Data
Vault 2.0*. Morgan Kaufmann, 2015. ISBN 978-0128025109. Hub (business keys), Link
(relationships), Satellite (descriptive attributes and history); hash keys; load-date
and record-source as mandatory metadata.

---

## Naming and style

### SRC-ISO-11179-5 — `VERIFIED`

ISO/IEC 11179-5:2015, *Information technology — Metadata registries (MDR) — Part 5:
Naming principles*. <https://www.iso.org/standard/60341.html>

A data element name is composed of an **object class term**, a **property term**, a
**representation term**, and optional **qualifier terms**. All data elements that are
characteristics of the same object class begin with the same object class term
(everything about Person begins with `Person`). The representation term semantically
signals the value domain.

### SRC-SQLSG — `VERIFIED`

Holywell, Simon. *SQL Style Guide*. <https://www.sqlstyle.guide/>

Identifiers at most 30 bytes; begin with a letter, never end in an underscore; letters,
numbers and underscores only; no consecutive underscores. Avoid camelCase. Avoid
descriptive prefixes and Hungarian notation such as `sp_` or `tbl`. Column names
singular. **"Avoid simply using `id` as the primary identifier for the table."** Never
give a table the same name as one of its columns, or the reverse. Uniform suffixes:
`_id`, `_status`, `_total`, `_num`, `_name`, `_seq`, `_date`, `_tally`, `_size`,
`_addr`. Prefer `NUMERIC` and `DECIMAL` over `REAL` and `FLOAT` unless floating-point
maths is genuinely required. Every table must have at least one key. Use `CHECK()` to
validate ranges and formats.

### SRC-CEL-SPS — `BOOK`

Celko, Joe. *Joe Celko's SQL Programming Style*. Morgan Kaufmann, 2005.
ISBN 978-0120887972.

---

## Layered and analytics engineering

### SRC-DBT-STRUCT — `VERIFIED`

dbt Labs. "How we structure our dbt projects."
<https://docs.getdbt.com/best-practices/how-we-structure/1-guide-overview>

Staging, then intermediate, then marts, moving data from source-conformed to
business-conformed. `stg_` prefix; one staging model per source table. Explicit
principle: consistent, documented conventions matter more than the perfect structure,
and any deviation should have its reasoning written down.

### SRC-DBT-STG — `VERIFIED`

dbt Labs. "Staging: Building a foundation."
<https://docs.getdbt.com/best-practices/how-we-structure/2-staging>

Staging models may **only** rename, cast, do basic computation such as cents to
dollars, and categorise into buckets or booleans. **No joins** — they duplicate
computation and confuse downstream relationships. **No aggregations** — they change the
grain. IDs suffixed `_id`; monetary units carried in the column name, e.g.
`subtotal_cents`.

---

## Integrity, temporality, evolution

### SRC-SQL2011 — `VERIFIED`

ISO/IEC 9075:2011 temporal features. <https://en.wikipedia.org/wiki/SQL:2011>

Two distinct mechanisms. **System-versioned** tables use `PERIOD FOR SYSTEM_TIME` with
`WITH SYSTEM VERSIONING`; the system maintains validity. **Application-time period**
tables use `PERIOD FOR` with automatic period splitting, temporal primary keys, and a
**`WITHOUT OVERLAPS`** constraint. Query syntax: `AS OF`, `BETWEEN ... AND`,
`FROM ... TO`.

### SRC-FOW-TIME — `VERIFIED`

Fowler, Martin. "Patterns for things that change with time."
<https://martinfowler.com/eaaDev/timeNarrative.html>

**Audit Log** — record changes; cheap to write, awkward to query. **Effectivity** — an
explicit validity period on the object; queryable but every consumer must understand
the temporal dimension. **Temporal Property** — an accessor parameterised by date.
**Snapshot** — state at a point in time. **Temporal Object** — explicit versions with a
contract class holding the history. **Bitemporal** — actual time versus record time,
required wherever retroactive correction happens, as in payroll and billing.

### SRC-SOFTDEL — `VERIFIED`

Brandur Leach, "Soft deletion probably isn't worth it" <https://brandur.org/soft-deletion>;
Cultured Systems, "Avoiding the soft delete anti-pattern"
<https://www.cultured.systems/2024/04/24/Soft-delete/>

Soft deletion systematically misleads the database. Foreign keys can no longer express
"this parent exists". Unique constraints stop matching intent — a user who deletes an
account cannot re-register with the same email. The delete flag leaks into nearly every
query, and forgetting it produces silently wrong results rather than an error. The
stated position, which this rubric adopts: a **blanket** soft-delete policy is the
antipattern; soft deletion chosen deliberately for a specific need is legitimate.
Alternatives named: a separate relation for deleted rows, mirror history tables, or
database temporal tables.

### SRC-PROTO-UPD — `VERIFIED`

Protocol Buffers, "Language Guide (proto3)", *Updating A Message Type*.
<https://protobuf.dev/programming-guides/proto3/>

Never change a field number — it is equivalent to delete-and-recreate. Deleted field
numbers must never be reused; mark them `reserved`. Adding fields and appending enum
values are safe. The first enum value must be `0` and is the default. Numeric widening
is wire-compatible but may truncate.

### SRC-OMOP-CONV — `VERIFIED`

OHDSI. "OMOP CDM Conventions."
<https://ohdsi.github.io/CommonDataModel/dataModelConventions.html>

Every coded value is carried three ways: `*_source_value` (verbatim source text,
explicitly **not for analytics** — ETL and QA only), `*_source_concept_id` (the source
vocabulary's concept), and `*_concept_id` (the standard concept, used by all analytics).
Concept IDs are persistent, centrally maintained numeric identifiers. Unmapped free text
is not stored in clinical tables. Non-required standard concept fields should be
**NULL, not zero**, when no source value exists.

### SRC-OMOP-FIELD — `VERIFIED`

OHDSI CDM field-level specification. <https://github.com/OHDSI/CommonDataModel>

Every field carries eleven metadata columns: `cdmTableName`, `cdmFieldName`,
`isRequired`, `cdmDatatype`, `userGuidance`, `etlConventions`, `isPrimaryKey`,
`isForeignKey`, `fkTableName`, `fkFieldName`, and `fkDomain`/`fkClass`. This is the
target shape for a machine-readable data dictionary: identity, cardinality, type,
relationship, business guidance **and** population guidance.

### SRC-FRICT-TS — `VERIFIED`

Frictionless Data, *Table Schema*. <https://datapackage.org/standard/table-schema/>

Field descriptors with `name` (required, unique), `type`, `format`, `title`,
`description`, `constraints`. Constraint vocabulary: `required`, `unique`, `uniqueKeys`,
`minLength`/`maxLength`, `minimum`/`maximum`, `exclusiveMinimum`/`exclusiveMaximum`,
`pattern`, `enum`, `jsonSchema`. Plus `primaryKey` and `foreignKeys`. `missingValues`
declares how absence is represented, per schema or per field.

### SRC-FHIR-ARCH — `VERIFIED`

HL7 FHIR, "Architecture." <https://www.hl7.org/fhir/overview-arch.html>

The **80/20 rule**: a resource covers the 20% of requirements that satisfy 80% of
interoperability needs; the remainder arrives through extensions and profiles rather
than new resources or schema change. Strongly typed, with terminology linkage and
validation built in. Resources are highly composable through references — and FHIR
itself flags the absence of strict rules about what may reference what as an open issue,
which is worth remembering before treating reference freedom as a virtue.

---

## Observed convention in exemplar schemas

### SRC-MSFT-WWI — `VERIFIED`

Microsoft. "WideWorldImporters OLTP database catalog", Design considerations section.
<https://learn.microsoft.com/en-us/sql/samples/wide-world-importers-oltp-database-catalog>

Cited because the rationale is documented, not merely inferable. All tables have
**single-column primary keys for join simplicity**. All schemas, tables, columns,
indexes and check constraints carry a **`Description` extended property**. **All foreign
keys are indexed** unless another nonclustered index already leads with the same column.
Auto-numbering uses **sequences rather than `IDENTITY`**, which travels better across
linked servers, and one sequence may be shared by sibling tables. Tables commonly
queried together are collocated in a schema to reduce join complexity. Data schemas are
not exposed to applications; access runs through separate view and procedure schemas.
The schema was **code-generated from metadata tables** specifically to obtain naming
consistency and completeness.

### SRC-PAGILA — `VERIFIED`

Pagila, the PostgreSQL port of the Sakila sample schema.
<https://github.com/devrimgunduz/pagila>

Observed conventions: singular snake_case table names such as `customer` and
`film_actor`; primary key named `{table}_id`; FK constraints named
`{table}_{column}_fkey`; a `last_update timestamptz DEFAULT now()` audit column on every
table, maintained by trigger; ENUM and DOMAIN types for constrained values
(`mpaa_rating`, `year`); composite primary keys on associative tables, e.g.
`film_actor(actor_id, film_id)`; range partitioning by month on the high-volume
`payment` table.

### SRC-CHINOOK — `BOOK`

Chinook sample database. <https://github.com/lerocha/chinook-database>

Cited only to establish that a different, internally consistent convention exists
(PascalCase tables, `{Table}Id` keys). This is why the rubric's rule is "pick one
convention and hold it", not "use snake_case".

---

## Mendix low-code domain model

Mendix is a **distinct paradigm**, not a SQL dialect. Several relational rules invert
there. See `references/mendix.md` and the applicability matrix in
`references/paradigms.md`.

### SRC-MDX-DM — `VERIFIED`

Mendix. "Domain Model." <https://docs.mendix.com/refguide/domain-model/>

Entity kinds: **Persistable** (stored in the database), **Non-persistable** (memory
only, session-scoped), **External** (data owned by another app or service), and **View**
(the result of a stored OQL query; beta). Associations, validation rules, event
handlers, indexes, access rules, calculated attributes and generalization are all
first-class model objects. Each module carries its own domain model.

### SRC-MDX-ASSOC — `VERIFIED`

Mendix. "Association Properties." <https://docs.mendix.com/refguide/association-properties/>

Multiplicity: one-to-one, one-to-many (the default), many-to-many. **Owner** is either
`Default` (X refers to Y) or `Both` (mutual). Delete behaviour, with the exact option
names: **"Keep associated object(s)"** — the default — **"Delete associated object(s) as
well"**, and **"Delete only if not associated"**, which requires an error message.
Storage is an association table by default, or a column in the owning entity;
column storage is unavailable for many-to-many.

### SRC-MDX-ATTR — `VERIFIED`

Mendix. "Attributes." <https://docs.mendix.com/refguide/attributes/>

Types: AutoNumber (persistable entities only), Binary (persistable only), Boolean, Date
and time (millisecond accuracy, with a toggleable **Localize** property), **Decimal** —
at most 20 integral and 8 fractional digits, and the documentation says explicitly
*"use this type to represent amounts of money"* — Enumeration, **Hashed string** (hashed
using the algorithm in app settings, suitable for passwords, not filterable), Integer,
Long, and String with a **default maximum length of 200**, configurable, optionally
unlimited. There is no Currency type. Binary and calculated attributes are not sortable.

### SRC-MDX-SYSMEM — `VERIFIED`

Mendix. "Entities", system members section. <https://docs.mendix.com/refguide/entities/>

`Store 'createdDate'`, `Store 'changedDate'`, `Store 'owner'` and `Store 'changedBy'`
are each **opt-in per entity and default to false**. `owner` and `changedBy` are
**associations to the system `User` entity**, not strings — that is the platform's
answer to "who created this row", and a string username column is a deviation from it.

### SRC-MDX-VALID — `VERIFIED`

Mendix. "Validation Rules." <https://docs.mendix.com/refguide/validation-rules/>

Rule types: **Required**, **Unique**, **Equals**, **Range**, **Regular expression**,
**Maximum length**. **`Unique` is enforced by the database.** `Unique` cannot be applied
to an inherited attribute in a specialization. The limitation that matters most for a
reviewer: validation rules run on **commit**, so direct database modification and Java
actions bypass them entirely.

### SRC-MDX-INDEX — `VERIFIED`

Mendix. "Indexes." <https://docs.mendix.com/refguide/indexes/>

Mendix indexes the entity ID, stored `owner` and `changedBy`, and association storage
**automatically**. `createdDate` and `changedDate` are **not** automatically indexed.
Attribute order in the index must match the `WHERE` clause order. Search fields whose
`Comparison` property is `Contains` do not benefit from an index. Indexes are disabled
for non-persistable entities and read-only for external entities.

### SRC-MDX-NAMING — `VERIFIED`

Mendix. "Naming Convention Best Practices."
<https://docs.mendix.com/refguide/naming-convention-best-practices/>

Modules UpperCamelCase. **Entities PascalCase and singular** — the stated reason is that
"the entity is the blueprint of the object, not a list of objects". **No abbreviations,
no underscores, no special characters** in entity names; a module named `Customer`
containing an entity named `customer` is a **Java compilation error** that stops the app
running. Attributes PascalCase; attributes that are technical rather than
business-related **start with an underscore**, and the stated test is whether you would
capture it in a paper process. Association names are auto-generated and the
auto-generated form *is* the best practice; where several associations join the same
pair of entities, extend the name with the purpose, e.g. `Person_Address_Delivery`.
Enumerations prefixed `ENUM_`. Calculated-attribute microflows prefixed `CAL_`; entity
event microflows `BCO_`, `ACO_`, `BCR_`, `ACR_`, `BDE_`, `ADE_`, `BRO_`, `ARO_`;
validation microflows `VAL_`.

### SRC-MDX-MXP — `VERIFIED`

Mendix. "Performance Best Practices", the MxAssist Performance Bot rule set.
<https://github.com/mendix/docs/blob/development/content/en/docs/refguide9/modeling/mx-assist-studio-pro/mx-assist-performance-bot/performance-best-practices.md>

Named, numbered rules from a shipped linter, which makes this the most directly citable
Mendix rule set. Domain-model relevant entries:

- **MXP001** — calculated attribute used in a data container; convert to a stored
  attribute and set it in a microflow before commit.
- **MXP002** — unused calculated attribute; it still executes on retrieve. Delete it.
- **MXP003** — attribute used in a sort bar has no index.
- **MXP007** — attribute used in an XPath has no index. Applies to read-intensive
  entities over roughly 10,000 records; order XPath expressions with indexed attributes
  first.
- **MXP009** — excessive inheritance. **Limit to two levels**; prefer enumerations,
  one-to-one associations, or non-persistable entities.
- **MXP010** — duplicated entity access rules; consolidate, and move state validation
  into microflows.
- **MXP013** — negating XPath access rules such as `not()` or `= false()`.
- **MXP015** — suboptimal XPath predicate ordering; cheapest and most selective first.

### SRC-MDX-PERF — `VERIFIED`

Mendix. "Community Best Practices for App Performance."
<https://docs.mendix.com/refguide/community-best-practices-for-app-performance/>

Index entities over roughly 100 records that are searched by anything other than Mendix
references or IDs. Cover search and sort clauses within a single index. Avoid duplicate
indexes leading with the same attribute. **At most three index attributes**, five as an
outside limit. Lead with the most selective attribute. **Minimize reference sets** —
Mendix retrieves IDs per row on list retrieves. **Avoid multiple associations between
the same two entities**, especially with different access levels; instead use an
enumeration on one entity, or an intermediary entity carrying an enumeration of the
association type. Do not put temporary associations on persistable entities; use
non-persistable entities for UI state. Minimize calculated attributes — they run on
every retrieve, per row. Denormalization by copying attribute values is legitimate where
data changes rarely, **provided the sync logic is built**. Avoid multiple inheritance
levels on high-volume entities, especially under XPath access rules. Minimize event
handlers. Rewrite `not` and unequal XPath as positive statements. Archive when volume
grows.

### SRC-MDX-GENASSOC — `VERIFIED`

Mendix. "Generalization and Association."
<https://github.com/mendix/docs/blob/development/content/en/docs/refguide/modeling/domain-model/generalization-and-association.md>

Inheritance **locks the generalization entity on write**, which can block retrieves
across the whole hierarchy; one-to-one associations confine locking to specific tables.
Prefer one-to-one associations under high transaction volume, or where the entity types
share few attributes. Prefer inheritance for intensive searching and sorting on
associated attributes, which benefits from clustered indexing. Microflows retrieve
**all** attributes of generalizations, specializations and associated parents; page
widgets retrieve only what is shown. The decisive warning: once inheritance is applied
it is difficult to remove while keeping the data, and removing a generalization loses
relationships permanently — so settle this before production data is loaded.

### SRC-MDX-STORAGE — `VERIFIED`

Mendix. "Generalization vs One-to-One Associations"
<https://docs.mendix.com/refguide/generalization-and-association/>, plus the Mendix Forum
thread "Query behavior for Generalization/Specialization"
<https://forum.mendixcloud.com/link/questions/90112>

**Class-table inheritance.** An instance is *partially stored in the generalization table
and partially in the specialization table*, joined internally by Mendix on a shared id.
Reading a specialization's own attributes hits the specialization table; reading inherited
attributes hits the generalization table.

Three consequences a reviewer needs:

- Inheritance costs **joins, not storage**. Nothing is duplicated, so an N-level chain is
  an N-table join on every read. This is why Mendix caps the recommendation at two levels
  (`SRC-MDX-MXP`, MXP009).
- The shared id is simultaneously the specialization's **primary key and its foreign key**
  to the generalization. There is no separate parent-id column.
- A write locks the **generalization** entity, so contention concentrates at the top of
  the hierarchy and can block retrieves across all of it.

The reviewing consequence: an attribute declared on a generalization has exactly ONE
physical column, on the generalization's table. A model or mapping that repeats it on the
child is describing a column that does not exist.

### SRC-MDX-ACCESS — `VERIFIED`

Mendix. "Access Rules." <https://docs.mendix.com/refguide/access-rules/>

Two facts that are counterintuitive in opposite directions, and a reviewer who assumes
either wrongly will write a confident false finding:

- Rules **are additive**: "if multiple access rules apply to the same module role, all
  access rights of those rules are combined for that module role." Permissions expand;
  they never restrict.
- Rules are **not inherited**: "Access rules are not inherited from an entity's
  generalization, because the security for every entity is specified explicitly." A
  specialization with no rules of its own is *unprotected*, not protected by its parent —
  which is the opposite of the assumption most reviewers arrive with.
- **Exception:** `System.User`'s built-in platform-enforced rules *do* apply to all its
  specializations and cannot be overridden by specialization-level XPath.

### SRC-MDX-TYPECHANGE — `VERIFIED`

Mendix. "Generalization vs One-to-One Associations"
<https://docs.mendix.com/refguide/generalization-and-association/> plus the Mendix Forum
thread "Create specialization objects from existing generalization objects"
<https://forum.mendixcloud.com/link/questions/91910>

**An object's entity type is fixed for its lifetime.** A specialization object cannot be
converted into a different specialization, or into its generalization: you must create a
new object of the target type, copy every attribute, and re-point every association —
typically by deep clone or a hand-written microflow. The design consequence is decisive:
anything that *changes over time* — a role, a lifecycle stage, a status — must not be
modelled as a specialization, because the model then forbids the transition the business
performs routinely. Use an enumeration or a one-to-one association instead.

### SRC-MDX-DEVBP — `VERIFIED`

Mendix. "Best Practices for Development."
<https://docs.mendix.com/refguide10/dev-best-practices/>

Persistability chosen deliberately rather than by default. View entities to abstract
add-on module data and decouple APIs. Attribute type migration requires a runtime schema
change, so plan it. Filter self-referencing association queries to avoid circular
retrieval. Entity access rules with XPath. Validation rules at entity level. Modules as
bounded contexts.

---

## Localisation

### SRC-I18N-DB — `VERIFIED`

Survey of multilingual schema designs.
<https://dev.to/dwarvesf/database-designs-for-multilingual-apps-4jb6> and
<https://dev.to/arctype/how-to-design-a-multi-language-database-1pid>

Three approaches with stated trade-offs. **Parallel columns** (`title_en`, `title_fr`):
simplest, best query performance, but the column count grows with the language count and
adding a language becomes a schema change — acceptable only when the language set is
small and fixed. **Translation table**: adding a language needs no schema change and no
content is duplicated, at the cost of joins. **JSON column**: flexible, with the weakest
constraint enforcement. The recommendation is explicitly conditional on whether the
language set is fixed, which is why the rubric's threshold sits at more than two
languages rather than at any parallel column.

### SRC-HIJRI — `VERIFIED`

Hijri and Gregorian storage practice. <https://pypi.org/project/hijridate/>, plus the
`UmAlQuraCalendar` guidance surfaced in
<https://raresql.com/2013/05/08/sql-server-how-to-convert-gregorian-dates-to-hijri-date-with-formatting/>

Keep the **Gregorian date canonical** in a real date type. Derive the Hijri
representation for display, and persist it only as a derived text value or an integer
year/month/day triple when it must be indexed or filtered. Tabular Hijri approximations
differ from the Saudi **Umm al-Qura** table — where official government dates must match
exactly, the Umm al-Qura mapping is required and a generic algorithm will drift.

### SRC-EID — `VERIFIED`

Emirates ID number format.
<https://economymiddleeast.com/news/uae-emirates-id-why-does-the-number-begin-with-784/>
and <https://gist.github.com/geordee/e51d111426de675c0c0f8503c2003047>

Fifteen digits in four parts: `784-YYYY-NNNNNNN-C`. `784` is the UAE ISO country code;
the second group is typically the birth year; the third is seven random digits; the last
is a check digit. Note the honest caveat from the validation gist — the check digit is
**not** a plain Luhn over the full fifteen digits — so any model claiming to validate an
Emirates ID must name the algorithm it actually uses.

---

## Recorded gaps

Sought and not obtained. No rule may cite these.

### SRC-SNOWPLOW-SCHEMAVER — `UNVERIFIED`

Snowplow SchemaVer, `MODEL-REVISION-ADDITION`. The documentation URL returned a redirect
loop during authoring, so the exact increment semantics were never confirmed.
Schema-evolution rules cite `SRC-PROTO-UPD` instead, which was verified.

### SRC-HOB-WEIGHTS — `UNVERIFIED`

Hoberman's per-category point allocation, published only inside SRC-HOB-SC. This gap is
the reason `assets/weights.json` is labelled as our own weighting.

### SRC-GITLAB-SQL — `UNVERIFIED`

GitLab's data-team SQL style guide. Both handbook URLs returned navigation chrome rather
than article content. Its conventions overlap SRC-SQLSG and SRC-DBT-STG, both verified,
so no rule depends on it.
