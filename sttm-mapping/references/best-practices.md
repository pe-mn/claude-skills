<!-- Generated 2026-07-22 by a verified web-research workflow (6 lenses; 60 raw findings; 12 notable claims independently fact-checked, 2 killed; 58 findings kept; 44 distinct sources). Design-agnostic; citations inline. -->

# Source-to-Target Mapping (STTM): Best-Practices Reference

A source-to-target mapping document is the contract between business SMEs, data engineers, and testers for a data migration or integration. In classic warehousing it is Kimball's "logical data map" — the spreadsheet that combines source definitions, the target model, and "the exact manipulation required of the source data," serving as the ETL developer's implementation spec, not documentation written after the fact ([ETL Tools / Kimball extraction](https://www.etltools.org/extraction.html)). This reference distills what separates a production-grade STTM from a column-name list.

---

## 1. Canonical STTM Column Inventory

The canonical row is organized into three blocks read left-to-right: **Source → Transformation → Target** ([Elvity](https://www.elvity.ai/articles/etl-source-to-target-mapping-template)). Kimball's original layout is deliberately target-first, because the map is built backward from a finished target model ([ETL Tools](https://www.etltools.org/extraction.html)) — a real tradeoff: use target-first ordering when the target schema is fixed and coverage of it is the completeness criterion; use source-first when readers reason from legacy data outward. Either way, keep the block structure.

**Core columns** (every professional STTM):

| Block | Column | Notes |
|---|---|---|
| Identity | `mapping_id` | Stable unique row key; makes the doc traceable into QA ([Sourcetable synthesis](https://sourcetable.com/excel-templates/data-mapping)) |
| Source | `source_system`, `source_table`, `source_column` | |
| Source | `source_datatype`, `source_length`, `source_nullable` | |
| Source | `sample_values` | Real data **including problem values**, not idealized examples ([Elvity](https://www.elvity.ai/articles/etl-source-to-target-mapping-template)) |
| Semantics | `description` / business meaning | |
| Transform | `transformation_rule` (plain English) | For SMEs |
| Transform | `transformation_expression` (pseudo-SQL / tool expression) | For engineers |
| Transform | `join/lookup reference`, `filter condition` | |
| Transform | `default_value`, null-handling rule | |
| Target | `target_table`, `target_column`, `target_datatype`, `target_length`, `target_nullable` | |
| Target | key/FK indicator | |
| Lifecycle | `mapping_type` (direct / rename / derived / lookup / constant / not-mapped) | |
| Lifecycle | `mapping_status` (controlled vocabulary) | |
| Lifecycle | `owner`, `comments/notes` | |

**Optional but high-value columns:**

- `test_id` / validation rule per row — turns the STTM into a test spec ([Data Ladder](https://dataladder.com/source-to-target-mapping-best-practices/), [dbt data tests](https://docs.getdbt.com/reference/resource-properties/data-tests))
- Cardinality (1:1, 1:many split, many:1 coalesce) and dependency/lineage annotation ([Data Ladder](https://dataladder.com/source-to-target-mapping-best-practices/))
- Hard-vs-soft quality-rule classification: hard violations reject the row, soft ones flag and load ([Elvity](https://www.elvity.ai/articles/etl-source-to-target-mapping-template))
- On-error disposition: {Fail, Ignore/Default, Reject}, per SSIS's per-column model, with truncation treated as a separate decision from error ([Microsoft SSIS](https://learn.microsoft.com/en-us/sql/integration-services/data-flow/error-handling-in-data?view=sql-server-ver16))
- SCD type **per column**, not per table — within one dimension, one attribute may be Type 2 while another is Type 1; fact rows leave it blank ([Kimball Design Tip #152](https://www.kimballgroup.com/2013/02/design-tip-152-slowly-changing-dimension-types-0-4-5-6-7/))
- Confidence/risk grade, reviewer, approval date, version ([dbSeer](https://dbseer.com/blog/data-migration-validation-how-to-prove-accuracy-completeness-and-parity/), [Data Ladder](https://dataladder.com/source-to-target-mapping-best-practices/))
- For ongoing integration (not one-shot migration): load frequency, FK relationships, denormalization requirements, date-format specifications, and rules for missing/duplicate/conflicting/unknown-member data ([Hevo](https://hevodata.com/learn/source-to-target-mapping/))
- Governance metadata such as masking rules and null-test flags carried as first-class columns, which can drive code generation directly ([ddl2dbt](https://github.com/ais-open/ddl2dbt))

The summary differentiator list: explicit transformation logic (not bare pairs), real sample data, first-class null/default handling, hard-vs-soft validation, per-row status/owner/test-id, changelog discipline, and one row per target column. Mediocre templates are source/target name lists with a free-text comments column ([Elvity](https://www.elvity.ai/articles/etl-source-to-target-mapping-template)).

---

## 2. Granularity and Keying Rules

**One row per target column.** The map is grained at the target-column level: every column of every target table gets a row tracing it to its source column(s) and transformation ([ETL Tools](https://www.etltools.org/extraction.html)). Enforce full target coverage as an invariant — dbt contracts refuse to build if any column lacks a declared name and type, with no partial contracts allowed; the STTM analog is that every target column appears as a row even if its disposition is "not mapped / default" ([Xebia](https://xebia.com/blog/data-contracts-and-schema-enforcement-with-dbt/)).

**Blank cells must be states, not omissions.** In Kimball's convention a blank Transformation cell *means* "direct move" — but only because the convention is declared ([Elvity](https://www.elvity.ai/articles/etl-source-to-target-mapping-template)). Better: impose a closed disposition vocabulary — Mapped / Constant-Default / Not Mapped (with reason) / Deferred (with owner) — so a blank logic cell is a validation error, not a silent gap. Vendor tools never leave a target column's fate ambiguous; published templates are weakest exactly here ([SSIS](https://learn.microsoft.com/en-us/sql/integration-services/data-flow/error-handling-in-data?view=sql-server-ver16), [Duncan template](https://www.slideshare.net/AlanDDuncan/06-transformation-logic-template-source-to-target)).

**Multi-source rows.** Many-to-one and one-to-many relationships are legitimate per-row ([Duncan](https://www.slideshare.net/AlanDDuncan/06-transformation-logic-template-source-to-target)); the NIEM convention handles 1:N by repeating the requirement row per target property ([NIEM](https://niem.github.io/reference/iepd/artifacts/mapping-spreadsheet/)). Record cardinality explicitly, since it drives transformation complexity and reconciliation strategy ([Data Ladder](https://dataladder.com/source-to-target-mapping-best-practices/)).

**Role-distinct columns are not duplicates.** Two source columns of the same type pointing at the same lookup table (two person FKs → PERSON, two org FKs → COMPANY) are two *roles* until proven otherwise, and collapsing them onto one target attribute rewrites the very fact they exist to distinguish. Legacy schemas rarely document the distinction, so it has to be established, not assumed. Three cheap tests, in ascending strength: (1) **the TO-BE model** — a redesigned model often already carries the discriminator, as paired `<RoleA>ID`/`<RoleB>ID` attributes or a literal `<RoleA>Not<RoleB>` boolean; a flag like that is the target side telling you the roles diverge in practice; (2) **the legacy application's own views** — a view that resolves both columns through *separate* joins to the same lookup and surfaces both as output columns is the vendor declaring design intent, not redundancy; (3) **a bucket reconciliation** against live data (see [validation.md](validation.md)) to measure how often they actually differ. Divergence in the low single-digit percent is still a ruling, not noise — it is precisely the rows a collapsed mapping would corrupt.

**Stable keys.** The natural row key is (target table, target column). Keep it stable so the sheet can be diffed and regenerated programmatically — in practice document and implementation must be reconcilable in both directions ([infa-s2t-gen](https://github.com/samik-saha/infa-s2t-gen)).

**Normalize the shared stuff out of rows:**

- **Source inventory tab**: catalog each source table once (system, schema, row count, extract timestamp, PK) rather than repeating source metadata on every row — the sources.yml pattern ([Y42](https://www.y42.com/learn/dbt/dbt-sources)).
- **Per-target-table population rule**: driving table, joins, filters, row-selection logic, documented once per table with column rows inheriting it. Automated column-level lineage explicitly cannot capture columns used only in joins or filters — this is where a spreadsheet STTM genuinely beats mapping-as-code ([dbt CLL](https://docs.getdbt.com/docs/explore/column-level-lineage)).
- **Shared rules sheet**: rule ID, definition, parameters; mapping rows cite rule IDs by name (the mapplet/Knowledge Module pattern) — restated inline logic is where copies drift ([Oracle ODI](https://docs.oracle.com/en/middleware/fusion-middleware/data-integrator/12.2.1.3/odidg/creating-and-using-mappings.html)).

**Workbook layout**: Changelog tab, Notes/assumptions tab, one mapping tab per business object, and a Transformations tab for multi-step logic that won't fit a cell ([Future Processing](https://www.future-processing.com/blog/source-to-target-mapping-using-excel/)).

---

## 3. Transformation Specification

This layer is "where most of the real work lives" and is the single biggest differentiator of a professional STTM ([Elvity](https://www.elvity.ai/articles/etl-source-to-target-mapping-template)).

**Three precision levels, two columns.** Carry both a plain-English rule for SMEs and a one-line executable/pseudo-SQL expression for engineers (e.g., "lowercase and trim" + `TRIM(LOWER(email))`). Kimball's bar: precise enough that a developer implements it without interpretation — usually SQL or pseudo-code ([ETL Tools](https://www.etltools.org/extraction.html)). The litmus test: "if two engineers could reasonably interpret a mapping differently, it's not production-grade" ([Data Ladder](https://dataladder.com/source-to-target-mapping-best-practices/)). Every vendor uses a deterministic expression language, never prose: Informatica expressions, Talend Java expressions per column, SSIS derived-column expressions, ODI declarative-rule SQL. Write expressions with explicit function names, operand columns, and NULL semantics — `IIF(ISNULL(x), 'N', x)` — reserving prose for business rationale. "Convert as appropriate" cells are the classic failure mode ([Informatica](https://docs.informatica.com/integration-cloud/data-integration/current-version/mappings/mappings/mapping-templates.html)).

Tension worth noting: sqlmesh's lesson is that parallel "logic" and "description" columns drift apart; where possible generate the human-readable description from the expression (or keep one authoritative cell that scripts render both ways) ([Tobiko Data](https://www.tobikodata.com/blog/column-level-lineage-for-dbt)). The dual-column convention remains dominant, but treat the expression as authoritative and audit prose against it.

**Notation conventions:**

- **Lookups/decodes**: enumerate code-translation value pairs explicitly with their valid domains. Every lookup declares: lookup source, join keys, match cardinality (unique/first/all matches), and an explicit **on-no-match action** — reject / default / NULL / abort. Talend deliberately distinguishes lookup-miss rejects from business-filter rejects; never leave lookup-miss behavior implicit ([Talend/Qlik](https://help.qlik.com/talend/en-US/studio-user-guide/7.3/lookup-inner-join-rejection)). For FK lookups specifically, record which of the two sanctioned dispositions applies: reject the child row, or auto-create a placeholder "<UNKNOWN>" parent and proceed (the late-arriving-dimension choice) ([ODI CKM](https://docs.oracle.com/middleware/1212/odi/ODIKD/ckm.htm)).
- **Defaults and nulls**: explicit `default_value` and null-handling rule per row, plus canonicalization of legacy magic values ('0000-00-00', 9999, empty string) stated before build ([Data Ladder](https://dataladder.com/source-to-target-mapping-best-practices/)).
- **Multi-candidate/multi-source**: document conditional precedence and dedup/survivorship rules across sources explicitly ([Data Ladder](https://dataladder.com/source-to-target-mapping-best-practices/)).
- **Composite/derived fields**: note dependencies on other fields and intermediate transformations; complex multi-step logic goes to the Transformations tab, referenced by ID ([Future Processing](https://www.future-processing.com/blog/source-to-target-mapping-using-excel/)).
- **Layer tagging**: split (or at least tag) each transformation as "source cleanup" (trim, cast, LoV decode) vs "business rule" (conditional logic, merge/survivorship) — dbt's staging/marts split. This keeps mechanical conversions from burying the few genuinely risky business-rule mappings during review ([dbt best practices](https://docs.getdbt.com/best-practices/best-practice-workflows)).

A compact DSL model worth borrowing notationally: arrow syntax (`CUST_ID -> customer_id { uuid_v5(...) }`), value maps (`map { A: true, I: false }`), pipe chains (`trim | lowercase | validate_email | null_if_invalid`), with free-text natural-language blocks as an escape hatch for business rules — deterministic structure for parseable facts, NL where needed ([satsuma-lang](https://github.com/EqualExperts/satsuma-lang)). Named, reusable transform objects referenced by ID (rather than free text repeated per row) make the mapping executable rather than documentation-only ([soumilshah1995](https://github.com/soumilshah1995/source-to-target-mapping-python)).

Standardize semantics with a data-domain vocabulary (Amount, Code, Date, Quantity, Rate, Status…) appended to the workbook ([Duncan](https://www.slideshare.net/AlanDDuncan/06-transformation-logic-template-source-to-target)).

---

## 4. Evidence and Profiling

**Profile before you map.** Legacy data quality is always worse than business users assume; profiling grounds the spec in fact. Profile four categories: numerics (invalids, negatives, zeros, min/max, totals), character fields (distinct values with frequencies — this is how you discover both 'EA' and 'EACH' as unit codes), dates (invalids, blanks, ranges), and format patterns. Every discovered variant must be explicitly handled in the transformation rule so none is "inadvertently missed" ([Definian](https://www.definian.com/articles/a-primer-on-data-profiling-on-data-migration-projects)). In the Kimball Lifecycle, profiling precedes modeling, which precedes the map — the STTM presupposes source analysis is done ([Kimball/MS DW Toolkit](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/books/microsoft-data-warehouse-dw-toolkit/), [ETL Tools](https://www.etltools.org/extraction.html)).

**Sample-value corroboration.** Carry real sample values, including problem values, on the row itself ([Elvity](https://www.elvity.ai/articles/etl-source-to-target-mapping-template)). Per-column profile output (null rate, distinct count, top-N values, min/max) belongs in or beside the STTM, and the mapping row should enumerate all observed source domain values for coded fields ([Definian](https://www.definian.com/articles/a-primer-on-data-profiling-on-data-migration-projects)).

**The legacy application's own views are the highest-grade join evidence available.** A view's `ON` clause is the vendor's declared join path, written by people who had the requirements; it outranks an ERD line, a naming convention, and any inference from column names. Harvest view lineage (view → source table → source column → join/filter condition) into a greppable extract early: it settles join keys, reveals the discriminators a join needs, and — when a view resolves one lookup table through several aliased joins — documents role distinctions the base schema leaves implicit. It also bounds scope cheaply: if exactly one view joins two tables, that predicate is the only link the application uses.

**A static catalog extract is a snapshot, and it goes stale.** Optimizer statistics (`NUM_DISTINCT`, `NUM_NULLS`, `SAMPLE_SIZE`) are an estimate from whenever stats were last gathered, and on a sampled column they do not even sum to the table's row count. They are fine for shape — is this column populated at all, is it high or low cardinality — and unsafe for anything volume-bearing. Measured drift on one engagement: a key column recorded as 947 non-null rows was 1,376 live, +45%. Size migration volumes, effort estimates and acceptance thresholds off a live `COUNT(*)`, and note in the sheet which numbers came from the extract.

**Reference/LoV data.** Domain checks belong at review time, not run time: does every source code value have a target translation? Are target lengths and ranges sufficient? Record source and target types, precision/scale (precision errors surface later as aggregate rounding drift), encodings, and time-zone normalization needs per row ([dbSeer](https://dbseer.com/blog/data-migration-validation-how-to-prove-accuracy-completeness-and-parity/)).

**Confidence grading and risk tiers.** Grade each mapping's confidence (High/Medium/Low, with evidence) and classify each element as exact-match-required vs tolerance-based. Agree thresholds with stakeholders **before** cutover — "defining tolerances in advance prevents the post-migration debate." High-risk elements get dual sign-off and row-by-row diffs; low-risk get sampling ([dbSeer](https://dbseer.com/blog/data-migration-validation-how-to-prove-accuracy-completeness-and-parity/)). Capture decision rationale in a notes column: why the mapping was chosen, not just what it is ([Data Ladder](https://dataladder.com/source-to-target-mapping-best-practices/)).

**Confidence sub-codes (engagement-derived option; one user deferred it, none rejected it).** The Medium band hides heterogeneous remediation paths. A one-token sub-code column — `H`, `M1` (join confirmed / column inferred), `M2` (column confirmed / join inferred), `M3-cap` (policy-capped), `L1-speculative`, `L2-representation-mismatch`, `NA-netnew` — makes remediation batches groupable ("rows that flip to High if the DB team confirms one join") instead of buried in prose rationales.

---

## 5. Validation and QA

**Write validation into the mapping itself.** Define checks alongside each mapping as it's created — domain coverage, code-translation validity, key uniqueness after dedup, record-count expectations, aggregation tolerances — so the STTM doubles as the test spec ([Data Ladder](https://dataladder.com/source-to-target-mapping-best-practices/)). The dbt habit generalizes: every mapping assertion is also a check (`unique`, `not_null`, `accepted_values`, `relationships`), and a machine-readable Validation Rule column lets reconciliation scripts be generated straight from the sheet ([dbt data tests](https://docs.getdbt.com/reference/resource-properties/data-tests)). Distinguish structural enforcement (blocks before load, like a dbt contract) from content validation (runs after load) ([Xebia](https://xebia.com/blog/data-contracts-and-schema-enforcement-with-dbt/)). ODI's model is instructive: declare constraints (PK, AK, FK, CK, NN) per target table rather than as per-column prose, land rejects in a conventionally named error table carrying all original columns plus error metadata (constraint name, type, message, timestamp, run/session ID), and set an explicit reject threshold in the spec header ([ODI CKM](https://docs.oracle.com/middleware/1212/odi/ODIKD/ckm.htm)).

**Two-tier review.** Technical peer review (counts, types) plus business/SME validation (does the data make sense, do the rules hold) — both required; regulated domains add dual sign-off before promotion. Acceptance gate: every row marked Accepted by a business owner, reconciliation within agreed tolerance, and all exceptions triaged — resolved or documented out-of-scope with mitigation ([Quinnox](https://www.quinnox.com/blogs/data-migration-validation-best-practices/), [AccountableHQ](https://www.accountablehq.com/post/the-ultimate-guide-to-healthcare-data-mapping-standards-examples-and-best-practices)). A mapping-type taxonomy (passthrough/rename/transform/derived) makes review triage trivial — reviewers concentrate on "transform" rows and descriptions auto-inherit for passthroughs ([dbt CLL](https://docs.getdbt.com/docs/explore/column-level-lineage)).

**Reverse coverage of sources.** Silent data loss lives in unmapped fields — legacy systems hold fields nobody currently uses that contain business-relevant history; if the mapping doesn't account for them, the history disappears unnoticed until needed. Require a disposition for 100% of source columns: mapped, intentionally-dropped-with-reason (business signed off), or open question. A coverage report listing source columns with no mapping row is the cheapest high-value automated QA check ([Tale of Data](https://www.taleofdata.com/blog/data-migration-legacy-systems)).

**Layered reconciliation.** (1) Row counts per table, with every discrepancy traced to an explicit rule (filter, dedup) rather than waved off; (2) checksums/hashes over concatenated values to catch silently modified rows; (3) aggregate comparisons on key business figures against baselines; (4) row-by-row diff only on critical tables; plus referential-integrity checks for orphans. Automate all of it — manual spot checks don't scale and leave no audit trail ([dbSeer](https://dbseer.com/blog/data-migration-validation-how-to-prove-accuracy-completeness-and-parity/)). Counts alone are explicitly a metric *not* to rely on — they miss value corruption. Sample ~10% of rows for field-by-field comparison, use stochastic checksumming at scale, and drive fixes from value-level diffs (which column, which rows) across six dimensions: completeness, accuracy, consistency, timeliness, conformity, uniqueness ([Datafold](https://www.datafold.com/blog/data-reconciliation-best-practices/)). Trace N sample records end-to-end per table, comparing each mapped column's transformed source value to the target value.

**Baseline symmetry and rehearsal.** Script a pre-migration baseline (counts, checksums, completeness rates, distributions, duplicates, orphans, constraint violations) and compare the target against the *recorded* baseline, not a source that may have changed since ([Quinnox](https://www.quinnox.com/blogs/data-migration-validation-best-practices/), [Airbyte](https://airbyte.com/data-engineering-resources/validate-data-integrity-after-migration)). Rehearse with representative test migrations; pipelines must be idempotent so validation is reproducible; failed validations produce structured exception reports (which rule, which rows) feeding the triage loop ([dbSeer](https://dbseer.com/blog/data-migration-validation-how-to-prove-accuracy-completeness-and-parity/)).

---

## 6. Lifecycle and Governance

**Placement in the lifecycle.** Profiling → target model complete → STTM drafted → ETL specification (which wraps the mapping) → development. Sign-off happens when the spec is reviewed with source-system owners and the modeling team before development begins, and the engineer who will build the pipeline should sit in the modeling sessions so the *rationale* is understood, not just the mechanics ([Kimball](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/books/microsoft-data-warehouse-dw-toolkit/)).

**Living artifact.** "If your mapping document is older than your last pipeline change, it's already wrong." Version the mapping with the pipeline, record change rationale, assess downstream impact before edits, and route changes through review-and-approval like code ([Data Ladder](https://dataladder.com/source-to-target-mapping-best-practices/)). Kimball's Lineage and Dependency subsystem (#29) sets the bar: for any element, show its ultimate sources and every intermediate transformation (lineage) and every downstream dependent affected by a change (impact) ([Kimball ETL subsystems](https://www.kimballgroup.com/2007/10/subsystems-of-etl-revisited/)).

**Practical spreadsheet governance:** version, author/owner, reviewer/approver, and approval-date columns; a Changelog tab; file version history enabled; a new versioned sheet when the *source structure itself* changes, with right-side mapping edits logged in the changelog ([Future Processing](https://www.future-processing.com/blog/source-to-target-mapping-using-excel/)). Controlled status vocabularies (Draft/Reviewed/Approved, or In Progress/Validated/Failed) let the sheet double as a progress dashboard ([Elvity](https://www.elvity.ai/articles/etl-source-to-target-mapping-template)). Name an owner per mapping row or section.

**Breaking changes are visible events.** dbt's model-versioning lesson: never silently overwrite; publish v2 alongside v1 so consumers migrate deliberately. In spreadsheet terms: keep one live authoritative sheet, stamp version/date in a frozen header, and never silently overwrite human-reviewed columns ([Xebia](https://xebia.com/blog/data-contracts-and-schema-enforcement-with-dbt/)).

---

## 7. What Modern Mapping-as-Code Teaches Spreadsheet STTMs

In dbt/sqlmesh, the mapping *is* the SQL plus its YAML sidecar; lineage is derived from `ref()`/`source()` calls or SQL parsing, so it can never drift from the pipeline. The standalone STTM survives as the **pre-code contract** — once migration SQL exists, the SQL becomes authoritative unless the STTM is regenerated from it ([Dagster](https://dagster.io/guides/dbt-lineage-in-action-3-use-cases-challenges-and-best-practices)). Informatica formalized the round trip decades earlier: the analyst-facing mapping specification drives mapping generation and exports to Excel as the exchange format ([Informatica](https://docs.informatica.com/data-integration/common-content-for-data-integration/10-5/mapping-specification-guide/introduction-to-mapping-specifications/mapping-specifications-overview.html)); conversely, tools reverse-generate STTM documents from executable metadata ([infa-s2t-gen](https://github.com/samik-saha/infa-s2t-gen)).

Transferable lessons:

- **Tests as columns.** Per-column test declarations living next to the mapping ([dbt](https://docs.getdbt.com/reference/resource-properties/data-tests)); nullability and masking flags as columns that auto-generate tests and policies ([ddl2dbt](https://github.com/ais-open/ddl2dbt)).
- **Contracts as completeness invariants.** No partial coverage: every target column present with a declared type ([Xebia](https://xebia.com/blog/data-contracts-and-schema-enforcement-with-dbt/)).
- **Lineage keys and mapping-type taxonomy.** Stable (target table, target column) keys; a passthrough/rename/transform/derived classification per row ([dbt CLL](https://docs.getdbt.com/docs/explore/column-level-lineage)).
- **Machine-readable hooks.** Enumerated status flags rather than free text, so validation can be scripted; the sheet should be diffable and regenerable ([Data Ladder](https://dataladder.com/source-to-target-mapping-best-practices/), [infa-s2t-gen](https://github.com/samik-saha/infa-s2t-gen)). Some teams go further and keep a machine-readable master (JSON/DSL) that *generates* the Excel deliverable ([STTM Gen](https://github.com/sergiomontey/-.NET-Source-to-Target-Mapping-Documentation-Generator-), [satsuma-lang](https://github.com/EqualExperts/satsuma-lang)).
- **Single-source-of-truth cells.** Avoid parallel logic/description columns that drift; derive one from the other where possible ([Tobiko Data](https://www.tobikodata.com/blog/column-level-lineage-for-dbt)).
- **Know the spreadsheet's genuine edge.** Automated lineage covers only SELECT provenance — join keys, filter predicates, and row-selection logic are blind spots that a per-table population-rule section captures and no tool does ([dbt CLL](https://docs.getdbt.com/docs/explore/column-level-lineage)).

The honest tradeoff: spreadsheets lose on version control, rule-based validation, automated lineage, and scale ([Data Ladder](https://dataladder.com/source-to-target-mapping-best-practices/)). For a one-shot migration this is tolerable — the pipeline runs once — provided the sheet carries a version stamp, changelog, and machine-checkable cells.

---

## 8. Anti-Patterns Catalog

1. **The column-pair list.** Bare source/target name pairs with a free-text comments column — no logic, no nulls, no status. The defining mark of a mediocre template ([Elvity](https://www.elvity.ai/articles/etl-source-to-target-mapping-template)).
2. **Prose-only transformation cells.** "Convert as appropriate" — if two engineers could interpret it differently, it isn't production-grade ([Data Ladder](https://dataladder.com/source-to-target-mapping-best-practices/), [Informatica](https://docs.informatica.com/integration-cloud/data-integration/current-version/mappings/mappings/mapping-templates.html)).
3. **"SQL is self-documenting."** Explicitly called a myth: conditional paths, filters, and edge cases must be documented in non-technical language too ([Data Ladder](https://dataladder.com/source-to-target-mapping-best-practices/)).
4. **Ambiguous blanks.** Blank cells whose meaning (direct move? not mapped? forgotten?) is undefined; unmapped target columns as silent gaps instead of a closed disposition vocabulary ([SSIS](https://learn.microsoft.com/en-us/sql/integration-services/data-flow/error-handling-in-data?view=sql-server-ver16)).
5. **Implicit null/default/magic-value handling.** Behavior discovered at build time instead of stated per field before build ([Data Ladder](https://dataladder.com/source-to-target-mapping-best-practices/)).
6. **Implicit lookup-miss and FK-miss behavior.** No declared on-no-match action or FK disposition — the developer decides ad hoc ([Talend](https://help.qlik.com/talend/en-US/studio-user-guide/7.3/lookup-inner-join-rejection), [ODI](https://docs.oracle.com/middleware/1212/odi/ODIKD/ckm.htm)).
7. **Mapping from assumptions, not profiles.** Skipping profiling and missing domain variants ('EA' vs 'EACH') that then break silently ([Definian](https://www.definian.com/articles/a-primer-on-data-profiling-on-data-migration-projects)).
8. **Ignoring "unused" source fields.** Unaccounted source columns whose history disappears unnoticed until it's needed ([Tale of Data](https://www.taleofdata.com/blog/data-migration-legacy-systems)).
9. **Counts-only validation.** Relying on record counts and volume metrics, which miss value corruption entirely ([Datafold](https://www.datafold.com/blog/data-reconciliation-best-practices/)).
10. **Stale documents.** A mapping older than the last pipeline change is already wrong; no version stamp, no changelog, silent overwrites of reviewed content ([Data Ladder](https://dataladder.com/source-to-target-mapping-best-practices/), [Xebia](https://xebia.com/blog/data-contracts-and-schema-enforcement-with-dbt/)).
11. **Restated shared logic.** Copy-pasting common rules (audit columns, standard decodes) into rows instead of referencing a named shared rule — copies drift ([ODI](https://docs.oracle.com/en/middleware/fusion-middleware/data-integrator/12.2.1.3/odidg/creating-and-using-mappings.html)).
12. **Idealized sample data.** Sample values that omit the problem cases the transformation must actually survive ([Elvity](https://www.elvity.ai/articles/etl-source-to-target-mapping-template)).
13. **Undefined error paths.** No hard/soft rule classification, no per-column error disposition, no reject-record layout or run identifiers — so rejects can't be triaged or recycled ([SSIS](https://learn.microsoft.com/en-us/sql/integration-services/data-flow/error-handling-in-data?view=sql-server-ver16), [ODI](https://docs.oracle.com/middleware/1212/odi/ODIKD/ckm.htm)).
14. **Tolerances negotiated after cutover.** Deferring match-threshold agreement until results are in, guaranteeing the post-migration debate ([dbSeer](https://dbseer.com/blog/data-migration-validation-how-to-prove-accuracy-completeness-and-parity/)).
15. **Single-audience review.** Technical-only or business-only sign-off; both lenses are required, and "done" means every row Accepted or explicitly excluded ([Quinnox](https://www.quinnox.com/blogs/data-migration-validation-best-practices/)).
16. **Collapsing role-distinct columns.** Merging two same-typed source columns (two person FKs, two org FKs) onto one target attribute because they "mean the same thing" — the divergent rows are silently rewritten, and the rate is usually small enough to survive spot-checking. Settle it with a bucket reconciliation before mapping, and check whether the TO-BE model already carries a discriminator flag (see §2).
17. **Sizing off a stale catalog extract.** Taking row counts, null rates or cardinality from optimizer statistics or a dated schema dump as if they were live facts; the estimate can be off by tens of percent and it silently propagates into volume estimates and acceptance thresholds (see §4).
