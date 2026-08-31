"""Rule registry for data-model-review.

This module is deliberately *declarative*. It holds no detection logic — only the
contract for each rule: what it claims, how bad it is, which paradigms it applies to,
and where the claim comes from. Detection lives in `checks.py`, keyed by rule id.

The split exists so that provenance is data rather than prose. `selftest.py` walks this
registry and fails if any rule cites a source id absent from `references/sources.md`, or
if a tier-A rule has no implementation. A rule that cannot say where it came from cannot
ship, and that is enforced rather than asked for.

Fields
------
id          Stable identifier. Never reuse one after retiring a rule (same reasoning as
            protobuf field numbers, SRC-PROTO-UPD) — reports and decision logs cite them.
dimension   One of DIMENSIONS. The detailed axis.
hoberman    One of HOBERMAN_CATEGORIES. The reporting axis, for the client-facing
            scorecard.
severity    BLOCKER | MAJOR | MINOR | NOTE. See SEVERITIES for what each commits to.
tier        "A" = mechanically decidable from the parsed model alone, and therefore
            reproducible. "B" = needs judgement about meaning; the reviewer adjudicates
            and must record evidence and confidence.
paradigms   Set of paradigm codes where the rule is valid. A rule absent from a
            paradigm is *not* a silent pass — `score_model.py` reports it as
            NOT_APPLICABLE so the coverage gap stays visible.
source      Source id from references/sources.md.
title       One line, in the reviewer's voice. What is wrong.
rationale   Why it matters. Reviewers paraphrase this; it should survive paraphrase.
failure     A concrete failure scenario. Not "this is bad practice" but "here is the
            query that returns the wrong number".
remedy      The fix, named as a pattern or expressed as DDL.
"""

from dataclasses import dataclass, field
from typing import FrozenSet

# --------------------------------------------------------------------------------------
# Vocabularies
# --------------------------------------------------------------------------------------

#: Paradigm codes. A model is classified into exactly one primary paradigm before any
#: rule runs — see references/paradigms.md. Getting this wrong is the single most
#: expensive mistake available to this skill, because a confidently misapplied canon
#: reads exactly like a competent review.
PARADIGMS = {
    "oltp": "Normalised operational relational schema (3NF/BCNF target)",
    "dim": "Dimensional / star-schema warehouse or mart (Kimball)",
    "vault": "Data Vault 2.0 raw or business vault",
    "mendix": "Mendix low-code domain model",
    "doc": "Document store / denormalised aggregate model",
    "graph": "Property-graph or RDF model",
    "semantic": "Semantic / metrics layer over a physical model",
}

ALL_RELATIONAL = frozenset({"oltp", "dim", "vault"})
ALL_PARADIGMS = frozenset(PARADIGMS)

#: Rules that hold wherever data is modelled, because the defect is in the *shape* of
#: the information rather than in any platform's mechanics. A repeating group is a
#: repeating group whether it is addr1/addr2/addr3 in Oracle or Address1/Address2/
#: Address3 in Mendix; a date in a string is wrong in both. Keeping these paradigm-wide
#: matters more than it looks: scoping them relationally silently exempted the entire
#: Mendix review from structural findings, which made a 66-attribute entity read as
#: clean.
ALL_MODELS = ALL_PARADIGMS

#: Hoberman's ten categories (SRC-HOB-SC). The names and questions are his; the weights
#: in assets/weights.json are ours, because his allocation is published only in the book.
HOBERMAN_CATEGORIES = {
    "Correctness": "Does the model meet the requirements?",
    "Completeness": "Is the model complete, but without gold plating?",
    "Scheme": "Does the model correspond to its schema level?",
    "Structure": "Is the model consistent, with integrity, following the basic rules?",
    "Abstraction": "Is the generalization/specialization balance right?",
    "Standards": "Does the model follow the available rule and naming standards?",
    "Readability": "Is the model presented in a readable layout?",
    "Definitions": "Are the definitions correct, complete and unambiguous?",
    "Consistency": "Does the model use the same structure and terminology throughout?",
    "Data": "Has a data profile been created, and do attributes match reality?",
}

#: Two of Hoberman's categories cannot be assessed from a schema alone. Recording that
#: here rather than scoring them low is the difference between reporting a defect in the
#: model and reporting a gap in the review inputs. Conflating those two is how a
#: scorecard quietly slanders a model for something the reviewer failed to ask for.
REQUIRES_EXTERNAL_INPUT = {
    "Correctness": "a requirements or business-rules document",
    "Readability": "a rendered diagram, not DDL or a spreadsheet",
    "Data": "a data profile — row counts, null rates, value distributions",
}

DIMENSIONS = [
    "Structure", "Keys", "Integrity", "Types", "Nullability", "ReferenceData",
    "Temporality", "Semantics", "Relationships", "Performance", "Governance",
    "Documentation", "Extensibility", "Localisation", "Consistency", "Scheme",
]

#: Extensions beyond Hoberman. Reports must label these as ours so nobody mistakes them
#: for part of the published scorecard.
#:
#: Note there is deliberately no "Platform" dimension. Mendix rules land on the same
#: dimensions as everything else — MDX-001 is a Keys finding, MDX-005 is a Performance
#: finding — because a reader comparing a Mendix model against a relational one should
#: be reading the same axes. What differs is which rules are *applicable*, not what the
#: review is about.
OUR_EXTENSIONS = {"Temporality", "Performance", "Governance", "Localisation",
                  "Extensibility"}

SEVERITIES = {
    "BLOCKER": "Loses data, or makes the system return wrong answers. Fix before load.",
    "MAJOR":   "Forces rework later, or defeats a constraint the design relies on.",
    "MINOR":   "Hygiene. Cheap now, irritating forever if left.",
    "NOTE":    "Preference or context-dependent. Raise it, do not insist on it.",
}

VERDICTS = {
    "VIOLATES_CITED_PRACTICE": "A named source says do not do this.",
    "DEFENSIBLE_TRADEOFF_I_D_DIFFER": "Legitimate choice; I would have chosen otherwise "
                                      "and here is the cost you are accepting.",
    "INSUFFICIENT_EVIDENCE": "The inputs cannot settle this. Say what is missing.",
}


@dataclass(frozen=True)
class Rule:
    id: str
    dimension: str
    hoberman: str
    severity: str
    tier: str
    paradigms: FrozenSet[str]
    source: str
    title: str
    rationale: str
    failure: str
    remedy: str
    tags: FrozenSet[str] = field(default_factory=frozenset)


R = Rule  # local brevity; the registry below is long enough already

# --------------------------------------------------------------------------------------
# STRUCTURE
# --------------------------------------------------------------------------------------

RULES = [
    R("STR-001", "Structure", "Structure", "MAJOR", "A", ALL_MODELS, "SRC-KAR-SAP1",
      "Entity-Attribute-Value table used as schema",
      "An (entity_id, attribute_name, value) triple moves the schema into the data. The "
      "database can then enforce nothing: no type, no requiredness, no referential "
      "integrity on any attribute.",
      "A required attribute is simply absent for some rows and no constraint notices. "
      "Reporting silently under-counts, and the error surfaces months later as a "
      "reconciliation gap nobody can date.",
      "Promote the known attributes to real columns. Where extensibility is genuinely "
      "open-ended, isolate it: a typed side table per attribute family, or a JSON column "
      "with a validating schema, so the core stays enforceable.",
      frozenset({"eav", "karwin-ch5"})),

    R("STR-002", "Structure", "Abstraction", "MAJOR", "B", ALL_MODELS, "SRC-HOB-SC",
      "Over-generalised entity",
      "Hoberman's Abstraction category asks whether generalization and specialization "
      "are in balance. A table called THING or OBJECT, or one carrying a type "
      "discriminator plus a long tail of mutually exclusive nullable columns, has "
      "abstracted past the point where the model communicates anything.",
      "Two genuinely different business concepts share a table, so a constraint correct "
      "for one is impossible to declare because it is wrong for the other. Every rule "
      "moves to application code, where it is enforced inconsistently.",
      "Split into subtypes, or apply a documented supertype/subtype pattern with the "
      "discriminator constrained and the exclusive columns moved to the subtype tables.",
      frozenset({"abstraction"})),

    R("STR-003", "Structure", "Structure", "MAJOR", "A", ALL_MODELS, "SRC-KAR-SAP1",
      "Repeating group in numbered columns",
      "Columns like addr1/addr2/addr3 or phone_1/phone_2 are Karwin's Multicolumn "
      "Attributes: a one-to-many relationship flattened into a fixed number of slots.",
      "Searching for a value means OR-ing across every slot, and the Nth+1 value has "
      "nowhere to go. A query that checks three of four slots is indistinguishable from "
      "a correct one until someone audits it.",
      "Extract a child table with a type or sequence discriminator.",
      frozenset({"karwin-ch7", "1nf"})),

    R("STR-004", "Structure", "Structure", "MAJOR", "A", ALL_MODELS, "SRC-KAR-SAP1",
      "Table-per-period proliferation (Metadata Tribbles)",
      "Tables differing only by a year or month suffix put data values into object "
      "names. Every query and every DDL change now has to enumerate them.",
      "A cross-period query silently omits the newest table because nobody updated the "
      "UNION. Totals are wrong and nothing errors.",
      "One table, partitioned by the period column.",
      frozenset({"karwin-ch8"})),

    R("STR-005", "Structure", "Structure", "MINOR", "A", ALL_MODELS, "SRC-SIMSION",
      "Very wide table",
      "Simsion and Witt treat elegance and communication as quality criteria. Past a "
      "certain width a table has almost certainly absorbed more than one entity, and no "
      "reader can hold it in mind.",
      "Nobody can state the table's grain in a sentence, so nobody notices when rows at "
      "two different grains start coexisting in it.",
      "Identify the functional dependencies and split. Where width is deliberate, say so "
      "in the table description and state the grain.",
      frozenset({"width"})),

    R("STR-006", "Structure", "Structure", "MAJOR", "B", frozenset({"dim"}), "SRC-KIM-DMT",
      "Fact table grain not declared",
      "Grain is step three of Kimball's four-step process and the fact from which "
      "everything else follows. An undeclared grain is not a documentation gap, it is an "
      "unmade decision.",
      "Rows at two grains land in the same fact table — an order-line row beside an "
      "order-header row — and every additive measure double counts.",
      "State the grain in one sentence in the table description, then verify every "
      "measure and every dimension key is true at that grain.",
      frozenset({"grain"})),

    # ----------------------------------------------------------------------------------
    # KEYS
    # ----------------------------------------------------------------------------------

    R("KEY-001", "Keys", "Standards", "MINOR", "A", ALL_RELATIONAL, "SRC-SQLSG",
      "Primary key named bare `id`",
      "The SQL Style Guide says plainly: avoid simply using `id` as the primary "
      "identifier. A qualified name survives being joined, aliased and copied into a "
      "downstream model.",
      "After a three-way join the result set has three columns called `id` and the "
      "consumer picks the wrong one. It resolves, so nothing complains.",
      "Rename to `{table}_id`.",
      frozenset({"naming"})),

    R("KEY-002", "Keys", "Structure", "BLOCKER", "A", ALL_RELATIONAL, "SRC-KAR-SAP1",
      "Table has no primary key",
      "Karwin's Keyless Entry. Without a key the table is a bag, not a relation: rows "
      "cannot be addressed, updated singly, or deduplicated.",
      "A retried load inserts every row twice and there is no constraint to stop it and "
      "no key to deduplicate on afterwards.",
      "Declare the real business key as PK, or add a surrogate and a unique constraint "
      "on the business key.",
      frozenset({"karwin-ch4"})),

    R("KEY-003", "Keys", "Structure", "BLOCKER", "A", ALL_RELATIONAL, "SRC-KAR-SAP1",
      "Surrogate key with no unique constraint on the business key",
      "Karwin's ID Required: a surrogate on everything, uniqueness on nothing. The "
      "surrogate guarantees rows are distinct, which is not the same as guaranteeing "
      "the *business* is distinct. This is the most common way a schema that looks "
      "correct admits duplicates.",
      "The same customer is loaded twice with two different surrogate ids. Both are "
      "valid rows. Every count of customers is now wrong, and merging them later means "
      "rewriting every child FK.",
      "Add a unique constraint on the natural/business key alongside the surrogate. If "
      "no business key exists, that is itself the finding: the entity has no identity.",
      frozenset({"karwin-ch3", "identity"})),

    R("KEY-004", "Keys", "Structure", "NOTE", "A", ALL_RELATIONAL, "SRC-MSFT-WWI",
      "Wide composite primary key",
      "WideWorldImporters documents single-column primary keys specifically for join "
      "simplicity. A wide composite is not wrong, but it propagates into every child "
      "table and every join predicate.",
      "A four-column key becomes sixteen columns of join predicate three levels down, "
      "and one of them gets omitted.",
      "Keep the composite as a unique constraint, and add a surrogate for children to "
      "reference — if the join burden is real. Otherwise leave it and say why.",
      frozenset({"keys"})),

    R("KEY-005", "Keys", "Structure", "MAJOR", "A", ALL_RELATIONAL, "SRC-DATE",
      "Primary key on a mutable descriptive column",
      "A key must be unique, non-null and stable. Names, emails and descriptions fail "
      "stability, and updating one cascades through every referencing row.",
      "A customer corrects the spelling of their name and either the update cascades "
      "through six tables or it is refused, and the correction never happens.",
      "Introduce a stable key — surrogate or an immutable business identifier — and "
      "demote the descriptive column to a unique constraint if uniqueness is real.",
      frozenset({"keys", "stability"})),

    R("KEY-006", "Keys", "Structure", "BLOCKER", "A", ALL_RELATIONAL, "SRC-KAR-SAP1",
      "Key or identifier stored in an approximate numeric type",
      "FLOAT and REAL cannot represent all decimal values exactly. Karwin's Rounding "
      "Errors, applied to identity.",
      "Two ids that differ compare equal, or an equality join misses a row that exists. "
      "Neither produces an error.",
      "Use an exact type: INTEGER, BIGINT, NUMERIC/DECIMAL.",
      frozenset({"karwin-ch9"})),

    R("KEY-007", "Keys", "Structure", "MAJOR", "A", ALL_RELATIONAL, "SRC-PAGILA",
      "Associative table admits duplicate pairs",
      "Pagila puts a composite primary key on every junction table — film_actor(actor_id, "
      "film_id). A surrogate key with no unique constraint on the pair permits the same "
      "relationship to be asserted twice.",
      "An actor is linked to a film twice. Any count or aggregate across the junction "
      "doubles for that pair.",
      "Composite PK on the FK pair, or a unique constraint on it alongside the surrogate.",
      frozenset({"junction"})),

    R("KEY-008", "Keys", "Structure", "BLOCKER", "A", frozenset({"dim"}), "SRC-KIM-DMT",
      "Type 2 dimension keyed on its natural key",
      "Kimball's dimension surrogate keys exist precisely so a dimension can hold "
      "several rows for one natural key over time. Keying on the natural key makes "
      "history impossible to store.",
      "The second version of a customer row violates the primary key, so the load either "
      "fails or overwrites — turning an intended Type 2 dimension into a Type 1 and "
      "destroying history that was supposed to be retained.",
      "Surrogate PK, natural key as a non-unique indexed column, plus effective dates "
      "and a current-row flag.",
      frozenset({"scd", "kimball"})),

    # ----------------------------------------------------------------------------------
    # INTEGRITY
    # ----------------------------------------------------------------------------------

    R("INT-001", "Integrity", "Structure", "MAJOR", "A",
      frozenset({"oltp", "dim", "vault"}), "SRC-KAR-SAP1",
      "Foreign-key-shaped column with no declared constraint",
      "Karwin's Keyless Entry. A column named like a key and holding key values, with "
      "nothing enforcing that the referent exists, is a relationship the database cannot "
      "help you keep.",
      "A parent row is deleted and the children become orphans. A later inner join drops "
      "them, so a report loses rows and nobody can explain the discrepancy.",
      "Declare the FK. If it cannot be declared — cross-database, deliberate staging "
      "tolerance — record that decision and the compensating check.",
      frozenset({"karwin-ch4", "fk"})),

    R("INT-002", "Integrity", "Structure", "BLOCKER", "A", ALL_RELATIONAL, "SRC-KAR-SAP1",
      "Polymorphic association",
      "A (target_type, target_id) pair pointing at whichever table the type names is "
      "Karwin's Polymorphic Associations. No foreign key can be declared, because the "
      "referent's table is a runtime value.",
      "A row references parent id 42 in a table that has no row 42. Nothing detects it. "
      "The join returns nothing and the record is invisible rather than erroneous.",
      "Either an exclusive-arc set of real nullable FKs with a check constraint allowing "
      "exactly one, or a common supertype table that all targets specialise, so a single "
      "real FK works.",
      frozenset({"karwin-ch6", "polymorphic"})),

    R("INT-003", "Integrity", "Structure", "MINOR", "A", ALL_RELATIONAL, "SRC-SQLSG",
      "Foreign key with no ON DELETE / ON UPDATE action declared",
      "Leaving the referential action implicit leaves the deletion semantics of the "
      "relationship undecided. The default is rarely wrong, but it is rarely chosen "
      "either.",
      "A delete that should have cascaded is refused in production, and the operator "
      "works around it by nulling the FK — silently converting a composition into an "
      "orphan.",
      "State the action explicitly, even where it matches the default.",
      frozenset({"fk"})),

    R("INT-004", "Integrity", "Structure", "MAJOR", "A", ALL_RELATIONAL, "SRC-KAR-SAP1",
      "Self-referencing hierarchy with no cycle or depth control",
      "Karwin's Naive Trees. An adjacency list is fine; an adjacency list with no "
      "constraint against cycles and no strategy for deep reads is a recursive query "
      "waiting to hang.",
      "A data-entry error makes A the parent of B and B the parent of A. Every recursive "
      "traversal loops until it is killed.",
      "Add a cycle-preventing constraint or trigger. For read-heavy deep hierarchies "
      "consider a closure table or materialised path alongside the adjacency list.",
      frozenset({"karwin-ch2", "hierarchy"})),

    R("INT-005", "Integrity", "Structure", "BLOCKER", "A", ALL_RELATIONAL, "SRC-DATE",
      "Foreign key type does not match the referenced key type",
      "A type mismatch across a join either fails to create the constraint or forces an "
      "implicit conversion on every join.",
      "VARCHAR '007' does not match INTEGER 7. The join returns nothing, and the missing "
      "rows look like missing data rather than a broken join.",
      "Align the types exactly, referent side wins.",
      frozenset({"fk", "types"})),

    R("INT-006", "Integrity", "Structure", "BLOCKER", "A", ALL_RELATIONAL, "SRC-DATE",
      "Foreign key references a table with no primary or unique key",
      "A reference to a non-unique target is not a foreign key — the referent is "
      "ambiguous.",
      "The join fans out: one child row matches three parent rows, and every aggregate "
      "over the join triples.",
      "Declare a key on the target table.",
      frozenset({"fk", "fanout"})),

    R("INT-007", "Integrity", "Structure", "MAJOR", "A", ALL_RELATIONAL, "SRC-SIMSION",
      "Mutually mandatory foreign keys between two tables",
      "Two tables each holding a NOT NULL FK to the other cannot be populated: neither "
      "row can be inserted first.",
      "The first insert fails whichever order you try. The workaround is to make one FK "
      "nullable and never populate it, leaving a relationship that exists in the diagram "
      "and not in the data.",
      "Make one side optional, defer the constraint, or merge the entities if they share "
      "a lifecycle.",
      frozenset({"circular"})),

    R("INT-008", "Integrity", "Structure", "MAJOR", "B", ALL_RELATIONAL, "SRC-SIMSION",
      "Shared attribute on parent and child with nothing forcing them to agree",
      "Where a child row carries a copy of an attribute its parent also carries — a "
      "currency, a tenant, a company, a period — a plain single-column foreign key "
      "leaves the two free to diverge. Simsion and Witt treat enforcement of business "
      "rules as a quality criterion, and 'the line's currency is the order's currency' "
      "is a business rule the schema can hold and here does not.",
      "A EUR order line is added to a USD order. Every declared constraint is satisfied, "
      "the order total sums two currencies into one number, and the result is a "
      "plausible figure that is wrong. Nothing errors, and no report shows it.",
      "Widen the foreign key to a composite that includes the shared column, so the "
      "child can only reference a parent that agrees with it — FOREIGN KEY (order_id, "
      "currency_id) REFERENCES sales_order (sales_order_id, currency_id), with a "
      "matching unique constraint on the parent. Or remove the copy from the child and "
      "read it through the parent.",
      frozenset({"denormalisation", "composite-fk"})),

    # ----------------------------------------------------------------------------------
    # TYPES
    # ----------------------------------------------------------------------------------

    R("TYP-001", "Types", "Standards", "BLOCKER", "A", ALL_MODELS, "SRC-SQLSG",
      "Date or time value stored in a character type",
      "A textual date cannot be range-queried correctly, sorts lexically, and admits "
      "'31/02/2024' and '' alike. The style guide lists DATE/TIME/TIMESTAMP as the "
      "types for this.",
      "A BETWEEN over the column compares strings, so '2024-1-5' sorts outside "
      "'2024-01-01'..'2024-12-31' and the row vanishes from the year's report.",
      "Convert to a real date or timestamp type; keep the original text only if it is "
      "required as source evidence, and mark it as such.",
      frozenset({"types", "dates"})),

    R("TYP-002", "Types", "Standards", "MAJOR", "A", ALL_MODELS, "SRC-SQLSG",
      "Numeric value stored in a character type",
      "Text numerics sort lexically, cannot be aggregated without casting, and accept "
      "anything.",
      "'10' sorts before '9'. A max() returns the wrong row, and a sum() fails on the "
      "first row containing a stray space.",
      "Cast to an exact numeric type; add a CHECK if a format must be preserved.",
      frozenset({"types"})),

    R("TYP-003", "Types", "Standards", "BLOCKER", "A", ALL_RELATIONAL, "SRC-KAR-SAP1",
      "Monetary amount in an approximate numeric type",
      "Karwin's Rounding Errors. Binary floating point cannot represent 0.1 exactly, so "
      "money in an IEEE-754 type accumulates error with every arithmetic operation. "
      "Which types those are is dialect-dependent, and getting it wrong is costly: in "
      "Oracle, FLOAT and REAL are NUMBER subtypes stored as exact decimal, and the "
      "genuine IEEE types are BINARY_FLOAT and BINARY_DOUBLE. Asserting drift on an "
      "Oracle FLOAT column is a claim that will be rebutted in one sentence — the real "
      "finding there is TYP-004, no declared scale.",
      "A sum of a thousand invoice lines is off by a few cents, the ledger does not "
      "balance, and the difference is not reproducible because it depends on summation "
      "order.",
      "NUMERIC/DECIMAL with explicit precision and scale, or integer minor units.",
      frozenset({"karwin-ch9", "money"})),

    R("TYP-004", "Types", "Standards", "MAJOR", "A", ALL_RELATIONAL, "SRC-SQLSG",
      "Monetary or measured column with no precision and scale",
      "An unqualified NUMBER or DECIMAL leaves the scale to the platform default, which "
      "differs between platforms and between a table and its copy.",
      "The staging copy truncates to two decimals while the source held four. The "
      "reconciliation difference is small, constant, and takes a week to find.",
      "Declare precision and scale explicitly, e.g. DECIMAL(18,4).",
      frozenset({"money", "precision"})),

    R("TYP-005", "Types", "Standards", "MINOR", "A", ALL_RELATIONAL, "SRC-SQLSG",
      "Boolean modelled as a single character flag",
      "A CHAR(1) Y/N flag is a defensible platform accommodation and a genuine loss: the "
      "type no longer excludes 'y', 'T', '1' or ' '.",
      "Three spellings of true accumulate over years of loaders. Every filter has to "
      "know all of them, and one filter does not.",
      "Use BOOLEAN where the platform has it; otherwise keep CHAR(1) and add a CHECK "
      "constraint restricting the domain. This is a NOTE if the CHECK is present.",
      frozenset({"types", "boolean"})),

    R("TYP-006", "Types", "Standards", "BLOCKER", "A", ALL_RELATIONAL, "SRC-SQLSG",
      "Unbounded text used as a key, unique column or foreign key",
      "CLOB/TEXT/VARCHAR(MAX) in a key position cannot be reliably indexed, and "
      "comparison semantics vary with collation.",
      "The unique constraint cannot be created, or is created and then silently fails to "
      "prevent near-duplicates differing in trailing whitespace.",
      "Bound the length, or introduce a hash or surrogate for the key role.",
      frozenset({"types", "keys"})),

    R("TYP-007", "Types", "Standards", "NOTE", "A", ALL_MODELS, "SRC-FRICT-TS",
      "Blanket maximum-width character columns",
      "Every text column at the platform maximum means no domain analysis happened. "
      "Table Schema treats maxLength as a real constraint carrying real information.",
      "A two-character country code column accepts a paragraph, so it eventually holds "
      "one, and the downstream join to the country table starts failing.",
      "Size columns to their domain, and record the domain in the description.",
      frozenset({"types", "width"})),

    R("TYP-008", "Types", "Standards", "MAJOR", "A", ALL_MODELS, "SRC-EID",
      "Formatted identifier stored as a number",
      "National identifiers, phone numbers and account numbers are digit strings, not "
      "quantities. An Emirates ID is 784-YYYY-NNNNNNN-C: the grouping carries meaning "
      "and the last digit is a check digit.",
      "A leading zero is dropped on load, the identifier no longer validates, and the "
      "row cannot be matched against the authoritative register.",
      "Store as a bounded character type with a CHECK on the pattern. If a check-digit "
      "rule is claimed, name the algorithm — the Emirates ID check digit is not a plain "
      "Luhn over all fifteen digits.",
      frozenset({"identifiers", "uae"})),

    R("TYP-009", "Types", "Standards", "MAJOR", "A", ALL_RELATIONAL, "SRC-FOW-TIME",
      "Event or audit timestamp with no time zone",
      "A naive timestamp on an event is ambiguous the moment the system crosses a zone "
      "or a DST boundary, and audit trails are exactly where ambiguity is least "
      "affordable.",
      "Two events an hour apart appear simultaneous across a DST change, so the "
      "reconstructed sequence of a disputed transaction is wrong.",
      "Use a timezone-aware type, or store UTC and record that convention explicitly in "
      "the column description.",
      frozenset({"time", "audit"})),

    # ----------------------------------------------------------------------------------
    # NULLABILITY
    # ----------------------------------------------------------------------------------

    R("NUL-001", "Nullability", "Structure", "MAJOR", "A", ALL_MODELS, "SRC-OMOP-CONV",
      "Sentinel value standing in for unknown",
      "OMOP states it directly: a field with no corresponding source value should be "
      "NULL, not zero. -1, 0, 'N/A', 'UNKNOWN', '1900-01-01' and '9999-12-31' are values "
      "that participate in aggregates and joins as though they were real.",
      "AVG() over a column where unknown is stored as 0 returns a number that is not the "
      "average of anything. It is plausible, so it is used.",
      "Use NULL for unknown. Where a real 'not applicable' member is needed, model it as "
      "a proper reference-data row with a documented meaning.",
      frozenset({"nulls", "sentinel"})),

    R("NUL-002", "Nullability", "Completeness", "MAJOR", "A", ALL_RELATIONAL, "SRC-SIMSION",
      "Almost every column nullable",
      "Enforcement of business rules is one of Simsion and Witt's quality criteria. If "
      "nothing is mandatory, no requirement was recorded in the schema.",
      "A row is inserted with nothing but a surrogate key. It satisfies every constraint "
      "and means nothing, and downstream code must defend against it everywhere.",
      "Mark the genuinely mandatory attributes NOT NULL. The list of what is mandatory is "
      "a requirements question — if it cannot be answered, that is the finding.",
      frozenset({"nulls"})),

    R("NUL-003", "Nullability", "Structure", "MAJOR", "A", ALL_MODELS, "SRC-OMOP-CONV",
      "NOT NULL column defaulted to a value that means unknown",
      "A NOT NULL column with DEFAULT 'UNKNOWN' or DEFAULT 0 launders absence into "
      "presence. The constraint reports completeness that does not exist.",
      "A completeness metric reads 100% because every row has a value. Every value is "
      "the default. The metric is worse than having none.",
      "Allow NULL and let absence be visible, or make the column genuinely mandatory at "
      "the point of capture.",
      frozenset({"nulls", "sentinel"})),

    # ----------------------------------------------------------------------------------
    # REFERENCE DATA
    # ----------------------------------------------------------------------------------

    R("REF-001", "ReferenceData", "Consistency", "MINOR", "A", ALL_RELATIONAL, "SRC-HOB-SC",
      "Inconsistent lookup-table shape",
      "Hoberman's Consistency category asks whether the model uses the same structure "
      "throughout. Several different shapes of lookup table in one model means every "
      "consumer needs a special case.",
      "Generic code that resolves codes to labels works for two thirds of the lookups "
      "and needs a hand-written exception for the rest.",
      "Pick one lookup shape — typically (id, code, label, active) — and apply it.",
      frozenset({"lookup"})),

    R("REF-002", "ReferenceData", "Abstraction", "MAJOR", "A", ALL_MODELS, "SRC-KAR-SAP1",
      "All reference data in one generic lookup table",
      "A single table holding every code list, discriminated by a type column, is EAV "
      "applied to reference data. No foreign key can be declared to a *subset* of it, so "
      "no column can be constrained to the right code list.",
      "An order status column accepts a country code. It resolves, joins, and displays "
      "as a country in a status field.",
      "One table per code list, each referenced by a real FK. Where the volume of tiny "
      "tables is genuinely the problem, constrain per-column with a CHECK or a filtered "
      "FK to a typed view.",
      frozenset({"lookup", "eav"})),

    R("REF-003", "ReferenceData", "Structure", "MAJOR", "A", ALL_RELATIONAL, "SRC-OMOP-CONV",
      "Code and display label conflated",
      "OMOP separates the verbatim source value, the source concept and the standard "
      "concept precisely because the string a user sees and the token a system joins on "
      "have different lifecycles.",
      "Someone fixes a typo in a status label. Every stored reference to it, and every "
      "report filter matching on it, breaks at once.",
      "Separate a stable code from a mutable label. Join on the code, display the label.",
      frozenset({"lookup"})),

    R("REF-004", "ReferenceData", "Structure", "MAJOR", "A", ALL_RELATIONAL, "SRC-OMOP-CONV",
      "Lookup table whose only identity is its label",
      "A lookup with a surrogate id and a label but no stable code has no identity that "
      "survives editing. OMOP's concept ids are persistent by design for this reason.",
      "The label is corrected, and there is now no way to tell whether this is the same "
      "concept as the one referenced in last year's extract.",
      "Add an immutable code column, unique and never edited.",
      frozenset({"lookup", "identity"})),

    R("REF-005", "ReferenceData", "Structure", "MINOR", "A", ALL_RELATIONAL, "SRC-KAR-SAP1",
      "Business-volatile value list hard-coded in DDL",
      "Karwin's 31 Flavors. An enum or CHECK list in the DDL turns adding a value into a "
      "schema migration.",
      "A new status is needed on Friday. It requires a DDL change, a deployment window, "
      "and the row that needed it is entered with the wrong status meanwhile.",
      "Move genuinely volatile lists to a reference table. Keep CHECK constraints for "
      "lists that are stable by nature, like a sex-at-birth code list or a two-value flag.",
      frozenset({"karwin-ch11", "lookup"})),

    # ----------------------------------------------------------------------------------
    # TEMPORALITY
    # ----------------------------------------------------------------------------------

    R("TEM-001", "Temporality", "Completeness", "MINOR", "A", ALL_RELATIONAL, "SRC-PAGILA",
      "No audit columns on a mutable table",
      "Pagila carries last_update on every table; WideWorldImporters documents a "
      "Description on every object. Knowing when a row last changed is the cheapest "
      "forensic capability available.",
      "A value is wrong and there is no way to establish when it became wrong, so there "
      "is no way to scope the correction.",
      "Add created and last-changed timestamps, maintained by default or trigger rather "
      "than by application code.",
      frozenset({"audit"})),

    R("TEM-002", "Temporality", "Structure", "MINOR", "A", ALL_RELATIONAL, "SRC-DAMA",
      "Audit actor stored as free text rather than a reference",
      "created_by holding a login string rather than a reference to the user entity "
      "cannot be joined reliably and does not survive a rename.",
      "A user's login changes. Their historical audit trail is now attributed to nobody, "
      "and there is no constraint that would have caught it.",
      "Reference the user entity. Keep the captured login string alongside only if the "
      "original text is itself evidence.",
      frozenset({"audit"})),

    R("TEM-003", "Temporality", "Consistency", "MAJOR", "A", ALL_RELATIONAL, "SRC-SOFTDEL",
      "Soft delete applied inconsistently across the model",
      "The cited discussion is explicit that a *blanket* soft-delete policy is the "
      "antipattern. A model where some tables have a delete flag and comparable ones do "
      "not has neither a policy nor an accident — it has both.",
      "A join between a soft-deleting parent and a hard-deleting child returns rows for a "
      "logically deleted parent. Whether a record is deleted depends on which table you "
      "asked.",
      "Decide per aggregate, write the decision down, and apply it to every table in that "
      "aggregate.",
      frozenset({"softdelete"})),

    R("TEM-004", "Temporality", "Structure", "BLOCKER", "A", ALL_RELATIONAL, "SRC-SOFTDEL",
      "Soft delete with a unique constraint that ignores it",
      "This is the failure the cited sources name specifically: uniqueness conceptually "
      "should not consider deleted rows, and the database does not know that.",
      "A user deletes their account and cannot sign up again with the same email, "
      "because the soft-deleted row still occupies the unique index. The bug is reported "
      "as a login problem and diagnosed for a week.",
      "Make the unique constraint partial — unique WHERE deleted_at IS NULL — or move "
      "deleted rows out to a separate relation.",
      frozenset({"softdelete"})),

    R("TEM-005", "Temporality", "Structure", "MAJOR", "A", ALL_RELATIONAL, "SRC-SQL2011",
      "Effective-dated rows with no overlap constraint",
      "SQL:2011 provides WITHOUT OVERLAPS for exactly this. A valid_from/valid_to pair "
      "with nothing preventing overlap will overlap.",
      "Two versions of a price are simultaneously valid on the same day. The lookup "
      "returns whichever the optimiser reaches first, so the invoiced amount is "
      "non-deterministic.",
      "An exclusion or WITHOUT OVERLAPS constraint on (business key, period). If the "
      "platform lacks it, a trigger — and say so.",
      frozenset({"temporal", "effectivity"})),

    R("TEM-006", "Temporality", "Consistency", "MINOR", "A", ALL_RELATIONAL, "SRC-FOW-TIME",
      "Open-ended period represented inconsistently",
      "Fowler's Effectivity needs one representation of 'still valid'. NULL in some rows "
      "and 9999-12-31 in others means every predicate must handle both.",
      "A filter written as valid_to >= today misses every row where valid_to is NULL. "
      "The report loses exactly the current rows it was about.",
      "Choose one representation and enforce it. NULL is the more honest; a high sentinel "
      "indexes and range-queries more simply. Either is fine, both is not.",
      frozenset({"temporal"})),

    R("TEM-007", "Temporality", "Structure", "MAJOR", "A", frozenset({"dim"}), "SRC-KIM-DMT",
      "Type 2 dimension without a current-row indicator",
      "Kimball's Type 2 pattern pairs effective dates with a way to find the current row "
      "cheaply.",
      "Every consumer writes its own date-range predicate to find the current row. They "
      "differ at the boundary, so two reports disagree about today.",
      "Add a current-row flag or a durable current view, and document which one consumers "
      "should use.",
      frozenset({"scd"})),

    R("TEM-008", "Temporality", "Structure", "MAJOR", "B", ALL_RELATIONAL, "SRC-FOW-TIME",
      "Retroactive correction needed but only one time axis modelled",
      "Fowler's Bitemporal case: payroll and billing need both when something was true "
      "and when it was recorded. One axis cannot express 'we thought X on Tuesday'.",
      "A backdated correction rewrites history, so a report rerun for last month no "
      "longer reproduces the number that was published and acted on.",
      "Add the record-time axis, or accept single-axis and document that reports are not "
      "reproducible after a correction.",
      frozenset({"bitemporal"})),

    # ----------------------------------------------------------------------------------
    # SEMANTICS / NAMING
    # ----------------------------------------------------------------------------------

    R("NAM-001", "Semantics", "Standards", "MINOR", "A", ALL_RELATIONAL, "SRC-ISO-11179-5",
      "Attribute name has no object-class or representation term",
      "ISO 11179-5 composes a name from object class, property and representation terms. "
      "A bare `name`, `type`, `status`, `date`, `value` or `code` gives the reader none "
      "of them.",
      "Two tables both have `status` meaning different things. A join or a copy carries "
      "the wrong one and nothing in the name warns anyone.",
      "Qualify: customer_status_code, order_placed_date.",
      frozenset({"naming", "iso11179"})),

    R("NAM-002", "Semantics", "Consistency", "MINOR", "A", ALL_RELATIONAL, "SRC-SQLSG",
      "Mixed identifier casing conventions",
      "The style guide prefers snake_case, but the load-bearing point is consistency: "
      "Chinook is internally consistent in PascalCase and is a fine schema. Mixing is "
      "the defect.",
      "Consumers cannot predict an identifier without looking it up, and on a "
      "case-sensitive platform half the hand-written queries need quoting.",
      "Pick one convention, state it, apply it. Do not mix.",
      frozenset({"naming"})),

    R("NAM-003", "Semantics", "Consistency", "MINOR", "A", ALL_RELATIONAL, "SRC-SQLSG",
      "Mixed singular and plural table naming",
      "Same reasoning as casing: either convention is defensible, inconsistency is not.",
      "Every join has to be looked up rather than recalled.",
      "Pick one and apply it.",
      frozenset({"naming"})),

    R("NAM-004", "Semantics", "Standards", "MINOR", "A", ALL_RELATIONAL, "SRC-SQLSG",
      "Type prefix or Hungarian notation on an object name",
      "The style guide names this directly: avoid descriptive prefixes such as sp_ or "
      "tbl. The prefix encodes what the catalog already knows.",
      "A table is promoted to a view and either the name lies or every reference has to "
      "change.",
      "Drop the prefix.",
      frozenset({"naming"})),

    R("NAM-005", "Semantics", "Standards", "MINOR", "A", ALL_RELATIONAL, "SRC-SQLSG",
      "Undocumented abbreviation in an identifier",
      "The guide allows abbreviations only where commonly understood. An abbreviation "
      "with no glossary entry is a private joke.",
      "Nobody can say whether CUST_STAT_CD is customer status or custody state, so a new "
      "developer guesses, and guesses wrong in one place out of ten.",
      "Expand it, or add it to a glossary that ships with the model.",
      frozenset({"naming"})),

    R("NAM-006", "Semantics", "Standards", "MINOR", "A", ALL_RELATIONAL, "SRC-SQLSG",
      "Table shares a name with one of its own columns",
      "Called out explicitly in the style guide.",
      "Unqualified references become ambiguous, and the error message points at the "
      "wrong line.",
      "Rename one of them.",
      frozenset({"naming"})),

    R("NAM-007", "Semantics", "Standards", "MAJOR", "A", ALL_RELATIONAL, "SRC-SQLSG",
      "Reserved word used as an identifier",
      "Reserved words require quoting forever, and the set differs by platform, so a "
      "model that works on one fails to port.",
      "A migration to another engine fails on a table called ORDER, and the fix touches "
      "every query that referenced it.",
      "Rename.",
      frozenset({"naming", "portability"})),

    R("NAM-008", "Semantics", "Consistency", "MAJOR", "A", ALL_MODELS, "SRC-HOB-SC",
      "One concept named several ways (synonym)",
      "Hoberman's Consistency category. cust_id, customer_id and custno in one model are "
      "three names for one thing.",
      "A join is written between two of the three and misses the third table entirely, "
      "so a segment of customers is absent from the analysis.",
      "Standardise on one name per concept and record it in a glossary.",
      frozenset({"naming", "consistency"})),

    R("NAM-009", "Semantics", "Consistency", "MAJOR", "A", ALL_MODELS, "SRC-HOB-SC",
      "One name meaning several things (homonym)",
      "The inverse of NAM-008 and more dangerous, because the names match so the mistake "
      "looks correct.",
      "Two `amount` columns, one gross and one net, are unioned. The total is neither.",
      "Rename to disambiguate, and say in each description which is which.",
      frozenset({"naming", "consistency"})),

    R("NAM-010", "Semantics", "Completeness", "MAJOR", "A", ALL_MODELS, "SRC-KIM-DMT",
      "Monetary or measured value with no unit or currency",
      "Kimball has named techniques for multiple currency facts and multiple units of "
      "measure. A bare `amount` or `weight` column asserts a unit it does not record.",
      "Amounts in two currencies are summed. The total is a number with no meaning, and "
      "it looks exactly like a valid one.",
      "Add a currency or unit column, or carry the unit in the column name — the dbt "
      "convention of subtotal_cents — and state the convention in the description.",
      frozenset({"units", "money"})),

    R("NAM-011", "Semantics", "Standards", "NOTE", "A", ALL_RELATIONAL, "SRC-SQLSG",
      "Identifier exceeds 30 bytes or uses characters outside [A-Za-z0-9_]",
      "The guide caps identifiers at 30 bytes for portability and restricts the character "
      "set. Longer names are legal on modern platforms; they are still a migration risk.",
      "A port to a platform with a shorter limit truncates two names to the same string.",
      "Shorten, and avoid spaces, accents and punctuation in identifiers.",
      frozenset({"naming", "portability"})),

    R("NAM-012", "Semantics", "Standards", "NOTE", "A", ALL_RELATIONAL, "SRC-DBT-STG",
      "Date and timestamp columns not distinguished by name",
      "The dbt convention distinguishes a date from a point in time by name because "
      "consumers otherwise have to check the type to know whether truncation happened.",
      "A join on order_date to a date dimension misses every row because the column is "
      "actually a timestamp with a time component.",
      "Suffix dates with _date and instants with _at, and hold to it.",
      frozenset({"naming", "time"})),

    # ----------------------------------------------------------------------------------
    # RELATIONSHIPS
    # ----------------------------------------------------------------------------------

    R("REL-001", "Relationships", "Structure", "BLOCKER", "A", ALL_MODELS, "SRC-KAR-SAP1",
      "Multi-valued attribute stored as a delimited list",
      "Karwin's Jaywalking. A comma-separated list of ids in a column is a "
      "many-to-many relationship with no constraint, no index and no join.",
      "A LIKE '%,7,%' search also matches 17 and 70. The membership test is wrong in "
      "both directions and looks like it works.",
      "A junction table with real foreign keys.",
      frozenset({"karwin-ch1", "1nf"})),

    R("REL-002", "Relationships", "Structure", "MAJOR", "B", ALL_RELATIONAL, "SRC-SIMSION",
      "Many-to-many resolved without its own attributes",
      "Simsion and Witt treat enforcement of business rules as a quality criterion. A "
      "junction table that is only two keys is often hiding attributes of the "
      "relationship itself — a role, a period, a quantity.",
      "The relationship's start date has nowhere to live, so it is stored on the parent "
      "and becomes wrong as soon as there are two relationships.",
      "Model the association as an entity in its own right where the relationship has "
      "properties.",
      frozenset({"junction"})),

    R("REL-003", "Relationships", "Structure", "NOTE", "B", frozenset({"dim"}), "SRC-KIM-DMT",
      "Centipede fact table",
      "Kimball names this: a fact table with a very large number of dimension keys, "
      "usually from modelling hierarchy levels as separate dimensions.",
      "Query performance collapses and the model becomes unreadable, so analysts build "
      "their own extracts and the conformed dimensions stop being conformed.",
      "Collapse hierarchy levels into their natural dimensions; consider junk dimensions "
      "for low-cardinality flags.",
      frozenset({"kimball"})),

    R("REL-004", "Relationships", "Structure", "MAJOR", "B", ALL_RELATIONAL, "SRC-KIM-DMT",
      "Fan-out risk: sibling one-to-many children aggregated together",
      "Joining two one-to-many children of the same parent multiplies their rows before "
      "aggregation. Kimball's remedy is multipass SQL rather than a single join.",
      "A parent with three children in table A and four in table B produces twelve rows. "
      "Summing either child's measure over that join gives a number several times too "
      "large — and it is a plausible number.",
      "Aggregate each child separately and join the aggregates, or use a bridge table "
      "with an allocation factor.",
      frozenset({"fanout"})),

    # ----------------------------------------------------------------------------------
    # PERFORMANCE
    # ----------------------------------------------------------------------------------

    R("PER-001", "Performance", "Structure", "MAJOR", "A", frozenset({"oltp", "vault"}),
      "SRC-MSFT-WWI",
      "Foreign key column with no index",
      "WideWorldImporters indexes every foreign key unless another index already leads "
      "with the same column. This is a documented, deliberate policy, not folklore.",
      "Deleting one parent row scans the whole child table to check the constraint. On a "
      "large child table the delete times out and the operator disables the constraint "
      "to get it done.",
      "Index the FK column, or record which existing index already leads with it.",
      frozenset({"index"})),

    R("PER-002", "Performance", "Structure", "MINOR", "A", ALL_RELATIONAL, "SRC-KAR-SAP1",
      "Index Shotgun",
      "Karwin's name for indexing by hope: many indexes, or several sharing a leading "
      "column, added without a query to justify them.",
      "Writes slow measurably while the redundant indexes are never chosen by the "
      "planner. The cost is continuous and invisible.",
      "Keep indexes that a named access path needs. Drop those whose leading column is "
      "already covered by a wider index.",
      frozenset({"karwin-ch12", "index"})),

    R("PER-003", "Performance", "Structure", "MAJOR", "A", ALL_RELATIONAL, "SRC-SIMSION",
      "Uniqueness asserted only in documentation",
      "A uniqueness rule described in a comment and not declared as a constraint is a "
      "rule that is not enforced.",
      "Duplicates appear, and because the documentation says they cannot, nobody checks "
      "for them until a downstream count is challenged.",
      "Declare the unique constraint. If it cannot be declared because the data already "
      "violates it, that is the more important finding.",
      frozenset({"constraints"})),

    # ----------------------------------------------------------------------------------
    # GOVERNANCE
    # ----------------------------------------------------------------------------------

    R("GOV-001", "Governance", "Data", "MAJOR", "A", ALL_PARADIGMS, "SRC-DAMA",
      "Personal data not identified as such",
      "DMBOK expects classification to be part of the model, not a separate spreadsheet. "
      "Names, national identifiers, dates of birth, addresses, contact details, salary "
      "and biometrics are personal data whether or not anyone labelled them.",
      "A copy is taken for a test environment. Nothing marked it as personal, so nothing "
      "masked it, and production personal data now sits in a system with weaker access "
      "control.",
      "Classify at column level in the model itself, and let masking, retention and "
      "access rules read the classification.",
      frozenset({"pii"})),

    R("GOV-002", "Governance", "Structure", "BLOCKER", "A",
      ALL_PARADIGMS - frozenset({"mendix"}), "SRC-KAR-SAP1",
      "Credential stored in a reversible form",
      "Karwin's Readable Passwords. A column named password, secret, pin or token in a "
      "plain character type is recoverable by anyone who can read the table or a backup "
      "of it.",
      "A backup file, a support query, or a database dump exposes every user's password "
      "in plain text at once.",
      "Store a salted hash of a password and never the password. For tokens and secrets, "
      "use a secret store rather than a table column.",
      frozenset({"karwin-ch19", "security"})),

    R("GOV-003", "Governance", "Data", "NOTE", "B", ALL_PARADIGMS, "SRC-DAMA",
      "No retention or ownership metadata",
      "DMBOK treats stewardship and retention as model-level concerns. Without an owner "
      "there is nobody to ask what a column means; without retention there is no basis "
      "for deleting anything.",
      "Personal data is retained indefinitely because no rule said otherwise, which is "
      "itself a compliance exposure.",
      "Record an owner and a retention rule per entity, in the model.",
      frozenset({"governance"})),

    # ----------------------------------------------------------------------------------
    # DOCUMENTATION
    # ----------------------------------------------------------------------------------

    R("DOC-001", "Documentation", "Definitions", "MAJOR", "A", ALL_PARADIGMS, "SRC-MSFT-WWI",
      "Entity has no definition",
      "WideWorldImporters puts a Description on every schema, table, column, index and "
      "check constraint. Hoberman scores Definitions as one of ten categories. An "
      "undefined entity cannot be reviewed, mapped or migrated safely.",
      "Two developers implement contradictory assumptions about what a table holds, and "
      "both are consistent with the schema.",
      "One or two sentences per entity: what it is, at what grain, and what it excludes.",
      frozenset({"docs"})),

    R("DOC-002", "Documentation", "Definitions", "MINOR", "A", ALL_PARADIGMS, "SRC-MSFT-WWI",
      "Low column-definition coverage",
      "Reported as a coverage percentage rather than per column, because a hundred "
      "identical findings is noise, not a review.",
      "The meaning of a column exists only in the head of whoever wrote the loader.",
      "Define columns whose meaning is not fully carried by their name — which, if the "
      "naming is good, is a minority of them.",
      frozenset({"docs"})),

    R("DOC-003", "Documentation", "Definitions", "MINOR", "A", ALL_PARADIGMS, "SRC-HOB-SC",
      "Definition merely restates the name",
      "Hoberman asks whether definitions are correct, complete and unambiguous. "
      "'customer_id: the customer id' satisfies a completeness metric and informs "
      "nobody.",
      "A definition-coverage report reads 100% while the model remains undocumented, so "
      "the gap is never scheduled for work.",
      "Say what it means, its domain, and how it is populated.",
      frozenset({"docs"})),

    R("DOC-004", "Documentation", "Definitions", "NOTE", "A", ALL_PARADIGMS, "SRC-OMOP-FIELD",
      "Derived column with no population rule recorded",
      "OMOP's field spec carries an etlConventions column for every field. A derived "
      "value without its derivation is not reproducible.",
      "Two loaders compute the same derived column differently and both are defensible. "
      "The values disagree and there is no specification to arbitrate.",
      "Record the derivation next to the column.",
      frozenset({"docs", "lineage"})),

    # ----------------------------------------------------------------------------------
    # EXTENSIBILITY
    # ----------------------------------------------------------------------------------

    R("EVO-001", "Extensibility", "Abstraction", "MAJOR", "A", ALL_MODELS, "SRC-KAR-SAP1",
      "Spare or numbered generic columns",
      "spare1, udf3, attribute12 are Multicolumn Attributes plus an admission that the "
      "model is expected to be wrong. Their meaning is set by convention outside the "
      "database.",
      "Two teams use spare2 for different things in different regions. A consolidation "
      "query treats them as one column.",
      "Model the actual attributes. Where genuine open extension is required, use a "
      "typed extension table or a validated JSON column so at least the shape is known.",
      frozenset({"karwin-ch7"})),

    R("EVO-002", "Extensibility", "Abstraction", "MAJOR", "B", ALL_RELATIONAL, "SRC-HOB-SC",
      "Subtypes modelled as nullable columns on a supertype",
      "Single-table inheritance: a type discriminator plus columns that only apply to "
      "some types. Hoberman's Abstraction category is exactly this balance.",
      "A column mandatory for one subtype cannot be declared NOT NULL because it is "
      "meaningless for another, so the rule moves to application code and is enforced in "
      "one of the three places it is needed.",
      "Supertype/subtype tables, with the discriminator constrained and each subtype "
      "carrying its own mandatory columns.",
      frozenset({"inheritance"})),

    R("EVO-003", "Extensibility", "Structure", "MINOR", "A", ALL_MODELS, "SRC-PROTO-UPD",
      "Enumeration with no default or unknown member",
      "Protobuf requires the first enum value to be 0 and treats it as the default, so "
      "that a consumer reading data written by a newer schema has somewhere to put a "
      "value it does not recognise.",
      "A new status value reaches an older consumer, which has no member for it and "
      "either rejects the row or coerces it to the first valid value.",
      "Include an explicit unknown or unspecified member, and make it the default.",
      frozenset({"evolution", "enum"})),

    # ----------------------------------------------------------------------------------
    # LOCALISATION
    # ----------------------------------------------------------------------------------

    R("LOC-001", "Localisation", "Structure", "MAJOR", "A", ALL_PARADIGMS, "SRC-I18N-DB",
      "More than two languages in parallel columns",
      "The cited survey is explicit that parallel columns are acceptable only when the "
      "language set is small and fixed, because each new language is a schema change. "
      "Past two languages that condition is usually already broken.",
      "Adding a third language means altering every table that carries a label, plus "
      "every view and every loader over them.",
      "Move to a translation table keyed by (entity, attribute, language).",
      frozenset({"i18n"})),

    R("LOC-002", "Localisation", "Consistency", "MAJOR", "A", ALL_PARADIGMS, "SRC-I18N-DB",
      "Asymmetric bilingual coverage",
      "Where a model carries paired language columns, a pair with one side missing means "
      "some screens can render in one language and not the other. Consistency is the "
      "whole value of the pattern.",
      "An Arabic-language user reaches a screen with an English-only label, or a blank "
      "one, and there is no constraint that would have caught the gap at build time.",
      "Complete the pairs, and constrain both sides to be present together where the "
      "label is required at all.",
      frozenset({"i18n", "arabic"})),

    R("LOC-003", "Localisation", "Structure", "MAJOR", "A", ALL_PARADIGMS, "SRC-HIJRI",
      "Hijri date with no canonical Gregorian counterpart",
      "The practice is to keep Gregorian canonical in a real date type and derive Hijri "
      "for display, persisting the derived form only where it must be filtered or "
      "indexed. A Hijri-only text or numeric date cannot be range-queried or compared "
      "across systems.",
      "A report filtering a date range misses records because the stored Hijri text does "
      "not order the way the range expects.",
      "Store the Gregorian date as the system of record; derive Hijri, and mark the "
      "derived columns as derived.",
      frozenset({"i18n", "hijri"})),

    R("LOC-004", "Localisation", "Structure", "MAJOR", "A", ALL_PARADIGMS, "SRC-HIJRI",
      "Hijri and Gregorian both independently writable",
      "Two writable representations of one instant will diverge, and there is no way to "
      "tell which is right. Compounded by the fact that generic Hijri algorithms differ "
      "from the Umm al-Qura table used for official dates.",
      "The Gregorian date is corrected and the Hijri date is not. Two documents printed "
      "from the same record carry different dates, and both are citable.",
      "One is canonical, the other is derived — enforced by a generated column, a "
      "trigger, or a documented and tested derivation.",
      frozenset({"i18n", "hijri"})),

    R("LOC-005", "Localisation", "Standards", "NOTE", "B", ALL_PARADIGMS, "SRC-I18N-DB",
      "No collation or normalisation policy for non-Latin text",
      "Arabic text admits several encodings of the same word — alef variants, tatweel, "
      "diacritics — so equality and sorting depend on a policy nobody has stated.",
      "Two spellings of one name do not match, so a person exists twice and neither "
      "record is complete.",
      "State the collation and a normalisation rule at capture, and apply it to matching "
      "keys.",
      frozenset({"i18n", "arabic"})),

    # ----------------------------------------------------------------------------------
    # SCHEME (model-level discipline)
    # ----------------------------------------------------------------------------------

    R("SCH-001", "Scheme", "Scheme", "MINOR", "B", ALL_PARADIGMS, "SRC-HOB-SC",
      "Model level not declared, or mixed levels in one model",
      "Hoberman's Scheme category asks whether the model corresponds to its schema. A "
      "logical model carrying tablespaces, or a physical model with no types, is being "
      "read at the wrong level by whoever reviews it.",
      "A reviewer raises physical findings against a conceptual model, or misses real "
      "physical defects because the model looked conceptual.",
      "Declare the level. Keep physical concerns out of logical models.",
      frozenset({"scheme"})),

    # ----------------------------------------------------------------------------------
    # CONSISTENCY (cross-model)
    # ----------------------------------------------------------------------------------

    R("CON-001", "Consistency", "Consistency", "MAJOR", "A", ALL_RELATIONAL, "SRC-HOB-SC",
      "Same column name carries different types across tables",
      "Hoberman's Consistency category. If customer_id is INTEGER in one table and "
      "VARCHAR in another, one of them is wrong.",
      "The join needs a cast, the cast is implicit, the index is not used, and on some "
      "rows the conversion fails at runtime rather than at build time.",
      "Unify the type. Where two things genuinely differ, they need different names — "
      "see NAM-009.",
      frozenset({"consistency", "types"})),

    R("CON-002", "Consistency", "Consistency", "MINOR", "A", ALL_RELATIONAL, "SRC-HOB-SC",
      "Audit column naming inconsistent across the model",
      "created_on, created_date, create_dt and CREATED_TS in one model defeat every "
      "generic tool written over it.",
      "A generic freshness monitor covers the tables it happens to match and silently "
      "skips the rest.",
      "One name per audit concept, everywhere.",
      frozenset({"consistency", "audit"})),

    # ----------------------------------------------------------------------------------
    # MENDIX PLATFORM
    #
    # Mendix is a different paradigm, not a dialect. Several relational rules above are
    # deliberately absent from the `mendix` paradigm set because they are meaningless or
    # inverted there — associations are declared by construction so there is no
    # undeclared FK; every persistable entity has an implicit ID so there is no missing
    # PK; PascalCase is correct rather than a violation. score_model.py reports those as
    # NOT_APPLICABLE rather than passing them silently, so the substitution stays
    # visible. See references/mendix.md.
    # ----------------------------------------------------------------------------------

    R("MDX-001", "Keys", "Structure", "BLOCKER", "A", frozenset({"mendix"}), "SRC-MDX-VALID",
      "Business key with no Unique validation rule",
      "Mendix gives every persistable entity an implicit ID, so the relational check for "
      "a missing primary key never fires. Identity still has to be declared, and the "
      "only database-enforced mechanism for it is a Unique validation rule.",
      "The same customer is created twice. Both objects are valid, each with its own "
      "implicit ID, and no constraint objected. Every count is wrong and merging them "
      "means repointing associations by hand.",
      "Add a Unique validation rule on the business key. Note that Unique cannot be "
      "applied to an inherited attribute in a specialization — if the key lives on the "
      "generalization, the constraint belongs there.",
      frozenset({"mendix", "identity"})),

    R("MDX-002", "Integrity", "Structure", "MAJOR", "A", frozenset({"mendix"}), "SRC-MDX-ASSOC",
      "Delete behaviour left at the default where the child cannot stand alone",
      "The Mendix default is 'Keep associated object(s)'. For a composition — an order "
      "line, an address that belongs to one person — keeping the child is exactly the "
      "orphan-tolerant design the relational rubric treats as a defect, arrived at by "
      "not choosing rather than by choosing.",
      "A person is deleted and their addresses remain, associated with nothing. They are "
      "invisible to every page and still counted by every aggregate over the address "
      "entity.",
      "Set 'Delete associated object(s) as well' for compositions, or 'Delete only if "
      "not associated' where the parent must not be removable while children exist. "
      "Leaving it at Keep is fine for a reference association — say so explicitly.",
      frozenset({"mendix", "orphan"})),

    R("MDX-003", "Relationships", "Structure", "MAJOR", "A", frozenset({"mendix"}), "SRC-MDX-PERF",
      "Multiple associations between the same pair of entities",
      "Mendix advises against this explicitly, especially where the associations carry "
      "different access levels.",
      "Two associations between Person and Address mean every retrieve has to know which "
      "one it wants, and the security rules on one do not apply to the other — so data "
      "reachable through the constrained association is reachable unconstrained through "
      "the other.",
      "Use one association plus an enumeration on one entity, or an intermediary entity "
      "carrying an enumeration of the association type.",
      frozenset({"mendix"})),

    R("MDX-004", "Extensibility", "Abstraction", "MAJOR", "A", frozenset({"mendix"}), "SRC-MDX-MXP",
      "Inheritance deeper than two levels (MXP009)",
      "MxAssist rule MXP009 sets the limit at two levels. Beyond that, queries and "
      "access-rule evaluation compound, and Mendix locks the generalization entity on "
      "write — so a write low in the hierarchy can block retrieves across all of it.",
      "A commit on one specialization blocks reads of every sibling type for the "
      "duration of the transaction, and the contention appears as an unrelated timeout "
      "elsewhere in the app.",
      "Flatten to at most two levels using an enumeration, a one-to-one association, or "
      "a non-persistable inheritance layer. Settle this before production data exists: "
      "removing a generalization loses its relationships permanently.",
      frozenset({"mendix", "mxp009", "inheritance"})),

    R("MDX-005", "Performance", "Structure", "MAJOR", "A", frozenset({"mendix"}), "SRC-MDX-MXP",
      "Attribute used for search or sort has no index (MXP003 / MXP007)",
      "Mendix indexes the entity ID, stored owner and changedBy, and association storage "
      "automatically — but nothing else. MXP003 and MXP007 flag sort-bar and XPath "
      "attributes without indexes, and the community guidance sets the threshold around "
      "100 records for anything searched by other than a reference.",
      "A grid sorted on an unindexed attribute over a large entity degrades until the "
      "page times out, and it degrades gradually so nobody attributes it to the model.",
      "Add an index covering the search and sort clause together. At most three "
      "attributes, most selective first, matching the order the query uses. Note that a "
      "Contains comparison gets no benefit from an index at all.",
      frozenset({"mendix", "mxp003", "mxp007", "index"})),

    R("MDX-006", "Performance", "Structure", "MINOR", "A", frozenset({"mendix"}), "SRC-MDX-PERF",
      "Duplicate index leading with the same attribute",
      "Named directly in the community performance guidance: avoid duplicate indexes "
      "starting with identical attributes.",
      "Writes pay for two indexes and the planner uses one. The cost is permanent and "
      "shows up as a general slowness nobody can localise.",
      "Keep the wider index, drop the narrower one whose leading attribute it covers.",
      frozenset({"mendix", "index"})),

    R("MDX-007", "Performance", "Structure", "MAJOR", "A", frozenset({"mendix"}), "SRC-MDX-MXP",
      "Calculated attribute where a stored attribute is needed (MXP001 / MXP002)",
      "MXP001 and MXP002. A calculated attribute runs its microflow on every retrieve, "
      "once per row in a list — and an unused one still runs.",
      "A grid of fifty rows executes fifty microflows, each with its own database "
      "actions, on every page load. The page is slow and the cause is invisible in the "
      "domain model diagram.",
      "Convert to a stored attribute and set the value in a microflow before commit. "
      "Delete calculated attributes nothing reads.",
      frozenset({"mendix", "mxp001", "mxp002"})),

    R("MDX-008", "Types", "Standards", "BLOCKER", "A", frozenset({"mendix"}), "SRC-MDX-ATTR",
      "Monetary amount not stored as Decimal",
      "The Mendix attribute documentation says it outright: use Decimal to represent "
      "amounts of money. There is no Currency type, and Float-like storage carries the "
      "same rounding exposure as anywhere else.",
      "Summed invoice lines drift by cents and the ledger does not balance, "
      "irreproducibly.",
      "Decimal, within its 20 integral and 8 fractional digit limits. If the amount can "
      "exceed that, the finding is that the model needs minor units.",
      frozenset({"mendix", "money"})),

    R("MDX-009", "Governance", "Structure", "BLOCKER", "A", frozenset({"mendix"}), "SRC-MDX-ATTR",
      "Credential attribute not stored as Hashed string",
      "Mendix provides a Hashed string type that hashes using the algorithm in app "
      "settings, specifically for passwords. A String password attribute is recoverable.",
      "A database export or a support query exposes every password in plain text.",
      "Change the attribute type to Hashed string. Note that hashed strings are not "
      "filterable, which is the correct constraint for a credential.",
      frozenset({"mendix", "security"})),

    R("MDX-010", "Temporality", "Completeness", "MINOR", "A", frozenset({"mendix"}), "SRC-MDX-SYSMEM",
      "System members not enabled on a mutable persistable entity",
      "createdDate, changedDate, owner and changedBy are opt-in per entity and default "
      "to false. The platform will maintain them for free; if they are off, nothing is "
      "recording who changed what.",
      "A value is wrong and there is no record of when it changed or who changed it, so "
      "the correction cannot be scoped and the cause cannot be found.",
      "Enable Store 'createdDate', 'changedDate', 'owner' and 'changedBy' on entities "
      "that change. Remember that createdDate and changedDate are not automatically "
      "indexed, so index them if they are filtered.",
      frozenset({"mendix", "audit"})),

    R("MDX-011", "Temporality", "Structure", "MINOR", "A", frozenset({"mendix"}), "SRC-MDX-SYSMEM",
      "Audit user modelled as a String instead of the owner / changedBy association",
      "Mendix's owner and changedBy are associations to the system User entity. A "
      "String username attribute duplicates that badly: it cannot be joined and does not "
      "survive a rename.",
      "A user's login changes and their entire audit history is attributed to a string "
      "that matches nobody.",
      "Use the system members. Keep a captured username only where the original text is "
      "itself the evidence.",
      frozenset({"mendix", "audit"})),

    R("MDX-012", "Semantics", "Standards", "MAJOR", "A", frozenset({"mendix"}), "SRC-MDX-NAMING",
      "Entity or attribute name breaks Mendix naming conventions",
      "Mendix requires PascalCase and singular entity names with no underscores, "
      "abbreviations or special characters — and the reason is not aesthetic. A module "
      "named Customer containing an entity named customer is a Java compilation error "
      "that stops the app from running. Note this inverts the snake_case rule that "
      "applies to relational models.",
      "The app fails to compile after a module rename, with an error that points at "
      "generated Java rather than at the domain model.",
      "PascalCase, singular, no underscores — except the deliberate leading underscore "
      "that marks a technical, non-business attribute.",
      frozenset({"mendix", "naming"})),

    R("MDX-013", "Structure", "Structure", "MAJOR", "A", frozenset({"mendix"}), "SRC-MDX-PERF",
      "Temporary or UI-state association on a persistable entity",
      "Mendix guidance: do not put temporary associations on persistable entities, use "
      "non-persistable entities for UI logic.",
      "Session-scoped selection state is written to the database, so it survives the "
      "session, accumulates without bound, and appears in reports as though it were "
      "business data.",
      "Move the association to a non-persistable entity.",
      frozenset({"mendix"})),

    R("MDX-014", "Performance", "Structure", "MINOR", "A", frozenset({"mendix"}), "SRC-MDX-PERF",
      "Reference set used where a reference would do",
      "Many-to-many reference sets make Mendix retrieve IDs per row on every list "
      "retrieve, so the cost scales with the grid.",
      "A list page issues an extra query per row. It is fast with test data and slow in "
      "production, which is the worst way to find out.",
      "Prefer one-to-many where the cardinality allows it; where many-to-many is real, "
      "consider an intermediary entity so the relationship can be retrieved and filtered "
      "directly.",
      frozenset({"mendix"})),

    R("MDX-015", "Governance", "Structure", "MAJOR", "B", frozenset({"mendix"}), "SRC-MDX-MXP",
      "Entity access rules absent, duplicated, or negated (MXP010 / MXP013)",
      "Access rules are where Mendix enforces authorisation. MXP010 flags duplicated "
      "rules, which compound into complex queries; MXP013 flags negated XPath such as "
      "not() or = false(), which performs badly on large sets. An entity with no rules "
      "at all is the more serious case.",
      "A persistable entity with no access rules is unreachable by every role — or, if "
      "a broad rule exists elsewhere in the hierarchy, reachable by all of them. Either "
      "way the security model is not what the diagram suggests.",
      "One consolidated rule per role; validate state transitions in microflows rather "
      "than as access-rule variations; rewrite negations as positive predicates.",
      frozenset({"mendix", "mxp010", "mxp013", "security"})),

    R("MDX-016", "Structure", "Scheme", "MINOR", "B", frozenset({"mendix"}), "SRC-MDX-DM",
      "Persistability chosen by default rather than deliberately",
      "Mendix offers Persistable, Non-persistable, External and View entities. Treating "
      "everything as persistable is a decision made by not making it.",
      "Transient calculation results are written to the database, growing a table nobody "
      "reads and nobody prunes.",
      "State why each entity is persistable. Use non-persistable for in-memory work and "
      "View entities to abstract data from add-on modules.",
      frozenset({"mendix"})),

    R("MDX-020", "Structure", "Structure", "MAJOR", "A", frozenset({"mendix"}),
      "SRC-MDX-STORAGE",
      "Attribute declared on both a specialisation and its generalisation",
      "Mendix uses class-table inheritance: an instance is stored partly in the "
      "generalisation's table and partly in the specialisation's, joined on a shared id. "
      "So an inherited attribute has exactly ONE physical column, on the generalisation. "
      "Redeclaring it on the child describes a column that does not exist — which means "
      "whoever declared it believes each table is independently complete, and that belief "
      "will produce a load that writes the same value twice or a mapping that specifies "
      "it twice with different rules.",
      "Two rows in the mapping claim the same physical column, each with its own source. "
      "The load runs both; whichever writes last wins, non-deterministically. Nothing "
      "errors, and the value is plausible either way — so the divergence is found, if at "
      "all, by someone reconciling a report months later.",
      "Declare the attribute once, on the entity that owns it. Where a subtype genuinely "
      "needs a different source for the same column, that is not a second declaration — "
      "it is one column with a discriminated expression, and it belongs on the "
      "generalisation as a CASE over the subtype.",
      frozenset({"mendix", "inheritance", "class-table"})),

    R("MDX-018", "Extensibility", "Abstraction", "BLOCKER", "B", frozenset({"mendix"}),
      "SRC-MDX-TYPECHANGE",
      "Generalization used to model a role or lifecycle stage that changes over time",
      "A Mendix object's entity type is fixed for its lifetime. There is no way to "
      "convert a specialization into a sibling specialization, or back into its "
      "generalization: you must create a new object of the target type, copy every "
      "attribute, and re-point every association by hand. So modelling something that "
      "changes — a role, a status, an eligibility stage — as a specialization builds a "
      "transition the business performs routinely into a structure that forbids it.",
      "An applicant is approved and becomes a beneficiary. The type cannot change, so "
      "the code creates a second object and copies the data across. Every association "
      "pointing at the original is now pointing at a stale object, and the two drift "
      "apart — with no constraint anywhere that notices.",
      "Model the varying part as an enumeration on one entity, or as a one-to-one "
      "association to a role entity that can be created and removed. Reserve "
      "generalization for what an object *is* permanently, never for what it is "
      "currently doing. Settle this before production data exists: removing a "
      "generalization afterwards loses its relationships permanently.",
      frozenset({"mendix", "inheritance", "party-role"})),

    R("MDX-019", "Governance", "Structure", "MAJOR", "A", frozenset({"mendix"}),
      "SRC-MDX-ACCESS",
      "Specialization entity declares no access rules of its own",
      "Access rules are explicitly NOT inherited from a generalization — Mendix states "
      "that security for every entity is specified explicitly. A reviewer who assumes "
      "inheritance (as most do, since every other object-oriented system works that "
      "way) will read an unprotected specialization as protected by its parent. Rules "
      "are also additive rather than restrictive, so a specialization can never narrow "
      "what its own rules grant.",
      "A specialization holding the more sensitive attributes ships with no access rules "
      "at all. Nothing on the generalization covers it, so the entity is either "
      "unreachable for every role or exposed through another path — and the domain "
      "model diagram looks identical either way.",
      "Declare access rules explicitly on every persistable entity, specializations "
      "included. Note the one exception: System.User's built-in platform rules do apply "
      "to its specializations and cannot be overridden.",
      frozenset({"mendix", "security"})),

    R("MDX-017", "Nullability", "Structure", "MAJOR", "A", frozenset({"mendix"}), "SRC-MDX-VALID",
      "Mandatory attribute with no Required validation rule",
      "Mendix has no NOT NULL to inspect; requiredness is a validation rule. The rubric's "
      "relational nullability checks are therefore substituted by this one.",
      "An object is committed with the attribute empty. Nothing objected, and downstream "
      "logic that assumed a value fails somewhere unrelated.",
      "Add a Required validation rule. Note the platform limitation: validation rules run "
      "on commit, so anything writing through Java or directly to the database bypasses "
      "them — if such a path exists, a database constraint is also needed.",
      frozenset({"mendix", "nulls"})),
]

# --------------------------------------------------------------------------------------
# Indexes over the registry
# --------------------------------------------------------------------------------------

BY_ID = {r.id: r for r in RULES}


def for_paradigm(paradigm: str):
    """Rules valid in `paradigm`, in registry order."""
    return [r for r in RULES if paradigm in r.paradigms]


def not_applicable(paradigm: str):
    """Rules deliberately excluded from `paradigm`.

    Reported rather than dropped: a reader needs to know that 'no missing-FK findings'
    means associations are declared by construction, not that the model passed a check.
    """
    return [r for r in RULES if paradigm not in r.paradigms]


def by_dimension(paradigm: str = None):
    out = {d: [] for d in DIMENSIONS}
    for r in RULES:
        if paradigm is None or paradigm in r.paradigms:
            out[r.dimension].append(r)
    return out
