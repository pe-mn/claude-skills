"""Tier-A detection implementations for data-model-review.

Every function here is a pure function of the parsed model. No I/O, no clock, no
randomness, no network — that is what makes the mechanical half of the score
reproducible, and `selftest.py` asserts it by scoring the same fixture twice and
diffing.

A check yields zero or more dicts:

    {"object": "SALES.ORDERS.CUSTOMER_ID", "evidence": "why this fired"}

`score_model.py` attaches the rule metadata, so a check never repeats the rule's own
title or severity. The evidence string is the check's whole contribution to the report
beyond "it fired" — it should name the specific thing found, because a finding a reader
cannot locate is a finding they will ignore.

Where a check cannot decide, it yields nothing. Tier-A checks do not guess: an
undecidable case belongs to a tier-B rule where a reviewer records evidence and
confidence, or to NOT_ASSESSABLE. Silence here means "no mechanical evidence", never
"looks fine".
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

# --------------------------------------------------------------------------------------
# Type vocabulary
# --------------------------------------------------------------------------------------

TEXT_TYPES = {"char", "varchar", "varchar2", "nchar", "nvarchar", "nvarchar2", "text",
              "clob", "nclob", "string", "character", "varying", "citext", "tinytext",
              "mediumtext", "longtext"}
UNBOUNDED_TEXT = {"text", "clob", "nclob", "longtext", "mediumtext"}
APPROX_NUMERIC = {"float", "real", "double", "double precision", "binary_float",
                  "binary_double", "number(*,*)"}
EXACT_NUMERIC = {"int", "integer", "smallint", "bigint", "tinyint", "numeric", "decimal",
                 "number", "dec", "long"}
DATE_TYPES = {"date", "datetime", "datetime2", "timestamp", "timestamptz",
              "timestamp with time zone", "timestamp without time zone",
              "smalldatetime", "time", "datetimeoffset", "date and time"}
TZ_AWARE = {"timestamptz", "timestamp with time zone", "datetimeoffset"}
BOOL_TYPES = {"bool", "boolean", "bit"}
BINARY_TYPES = {"blob", "bytea", "binary", "varbinary", "image", "raw"}

#: Reserved words that bite in practice. Not the full ANSI list — the full list produces
#: noise (STATUS, VALUE and NAME are technically reserved somewhere) and noise trains
#: readers to skip the section. These are the ones that actually break a port.
RESERVED = {"order", "group", "user", "table", "select", "from", "where", "index",
            "key", "primary", "check", "default", "case", "when", "then", "else",
            "column", "constraint", "level", "session", "date", "number", "comment",
            "grant", "revoke", "public", "role", "rows", "current", "authorization",
            "using", "natural", "left", "right", "full", "outer", "inner", "join",
            "union", "all", "any", "some", "exists", "between", "like", "is", "null",
            "not", "and", "or", "as", "by", "having", "distinct", "into", "values",
            "set", "on", "off", "start", "end", "size", "type", "value", "language",
            "position", "path", "range", "result", "return", "row", "state", "domain"}

#: Defaults that stand in for "unknown". Note what is NOT here: a bare `0`.
#: `credit_limit NUMERIC NOT NULL DEFAULT 0` is a real business value meaning no credit,
#: and flagging it produces a confident, wrong finding on well-built schemas. Zero as a
#: sentinel is only asserted where OMOP asserts it — in a reference/key column, via
#: SENTINELS_KEY below.
SENTINELS = {"-1", "'n/a'", "'na'", "'unknown'", "'unk'", "'none'", "'null'",
             "'-'", "'?'", "''", "'x'", "'tbd'", "'1900-01-01'", "'9999-12-31'",
             "'0001-01-01'", "'1970-01-01'", "'31-dec-9999'", "9999", "99999999"}
#: Additionally treated as sentinels when the column is a key or reference. This is the
#: OMOP rule directly: a non-required concept field should be NULL, not zero.
SENTINELS_KEY = SENTINELS | {"0", "-1", "'0'"}
SENTINEL_UNKNOWN_WORDS = {"unknown", "n/a", "na", "none", "not applicable", "tbd", "?"}

PII_TOKENS = {
    "name", "firstname", "lastname", "surname", "fullname", "middlename", "fname",
    "lname", "email", "mail", "phone", "mobile", "telephone", "tel", "fax",
    "address", "addr", "street", "postcode", "zipcode", "zip", "dob", "birthdate",
    "dateofbirth", "birth", "nationalid", "nationalno", "ssn", "socialsec", "passport",
    "emiratesid", "eid", "iqama", "iban", "accountno", "cardno", "creditcard",
    "salary", "wage", "income", "gender", "sex", "nationality", "religion",
    "maritalstatus", "photo", "signature", "fingerprint", "biometric", "latitude",
    "longitude", "geolocation", "ip", "ipaddress", "deviceid",
}
CREDENTIAL_TOKENS = {"password", "passwd", "pwd", "secret", "pin", "token",
                     "apikey", "api_key", "privatekey", "clientsecret", "credential"}
MONEY_TOKENS = {"amount", "amt", "price", "cost", "fee", "salary", "wage", "balance",
                "total", "subtotal", "payment", "charge", "revenue", "value", "budget",
                "discount", "tax", "vat", "premium", "fine", "penalty", "installment",
                "instalment", "donation", "contribution", "rent", "income", "expense",
                # credit_limit was missed until the flawed fixture proved it: a
                # NUMBER with no scale holding a credit limit is the same defect as
                # one holding an amount, and the token list was the only reason it
                # went unreported.
                "credit", "debit", "limit", "outstanding", "arrears", "principal",
                "interest", "refund", "deposit", "invoiced", "billed", "turnover"}
CURRENCY_TOKENS = {"currency", "curr", "ccy", "currencycode", "iso_currency"}
UNIT_TOKENS = {"unit", "uom", "unitofmeasure", "measure"}
MEASURE_TOKENS = {"weight", "height", "length", "width", "area", "volume", "distance",
                  "duration", "temperature", "speed", "quantity", "qty", "size"}
DELETE_FLAG_TOKENS = {"isdeleted", "deleted", "deletedat", "deleteddate", "deletedon",
                      "isdelete", "delflag", "deleteflag", "isactive", "activeflag",
                      "isvoid", "voided", "archived", "isarchived"}
SOFT_DELETE_STRICT = {"isdeleted", "deleted", "deletedat", "deleteddate", "deletedon",
                      "isdelete", "delflag", "deleteflag", "isvoid", "voided",
                      "archived", "isarchived"}
CREATED_TOKENS = {"createdat", "createdon", "createddate", "createdtime", "createdts",
                  "createdt", "createtime", "createdate", "inserted", "insertedat",
                  "rowcreated", "datecreated", "creationdate", "creation_date"}
CHANGED_TOKENS = {"updatedat", "updatedon", "updateddate", "modifiedat", "modifiedon",
                  "modifieddate", "changedat", "changedon", "changeddate", "lastupdate",
                  "lastupdated", "lastmodified", "updatetime", "updatedt", "rowupdated",
                  "datemodified"}
ACTOR_TOKENS = {"createdby", "updatedby", "modifiedby", "changedby", "owner", "author",
                "enteredby", "approvedby", "processedby", "actionby", "userid",
                "username", "login", "loginid", "userlogin"}
VALID_FROM_TOKENS = {"validfrom", "valid_from", "effectivefrom", "effectivedate",
                     "startdate", "datefrom", "fromdate", "begindate", "activefrom",
                     "rowstartdate", "dbtvalidfrom", "effstartdate"}
VALID_TO_TOKENS = {"validto", "valid_to", "effectiveto", "enddate", "dateto", "todate",
                   "expirydate", "expiredate", "activeto", "rowenddate",
                   "dbtvalidto", "effenddate"}
CURRENT_FLAG_TOKENS = {"iscurrent", "current", "currentflag", "iscurrentrow",
                       "activerow", "islatest", "latestflag", "currentind",
                       "dbtvalidtoisnull"}
LANG_SUFFIXES = ["ar", "en", "fr", "de", "es", "ur", "hi", "zh", "ru", "tr", "fa",
                 "arabic", "english", "french", "german", "spanish"]
HIJRI_TOKENS = {"hijri", "hijra", "hijry", "higri", "islamicdate", "ummalqura",
                "hijridate", "arabicdate"}
GREGORIAN_TOKENS = {"gregorian", "greg", "miladi", "gregoriandate"}
NATIONAL_ID_TOKENS = {"emiratesid", "eid", "eidno", "nationalid", "nationalno",
                      "idnumber", "idno", "iqama", "civilid", "passportno",
                      "socialsecnumber", "ssn"}
PHONE_TOKENS = {"phone", "mobile", "telephone", "tel", "fax", "whatsapp", "contactno"}
GENERIC_NAMES = {"name", "type", "status", "code", "value", "date", "flag", "desc",
                 "description", "number", "no", "amount", "text", "data", "info",
                 "category", "class", "kind", "state", "level", "comment", "note",
                 "remark", "detail", "result", "reference", "ref", "key", "id"}
GENERIC_ENTITY_NAMES = {"thing", "object", "entity", "item", "data", "record",
                        "master", "generic", "common", "misc", "miscellaneous",
                        "general", "table", "info", "detail", "element", "resource"}
TYPE_PREFIXES = ("tbl", "tbl_", "t_", "tb_", "sp_", "vw_", "v_", "fn_", "usp_",
                 "dim_x", "tab_")


# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------

def _norm(s):
    """Fold an identifier for token comparison: lowercase, strip separators."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _words(s):
    """Split an identifier into lowercase word tokens across snake/camel/Pascal."""
    s = s or ""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return [w for w in re.split(r"[^A-Za-z0-9]+", s.lower()) if w]


def _base_type(col):
    t = (col.get("type") or "").strip().lower()
    t = re.sub(r"\(.*\)", "", t).strip()
    return t


#: Dialects where FLOAT and REAL are NOT IEEE-754. Oracle's documentation is explicit:
#: "The FLOAT data type is a subtype of NUMBER... A FLOAT value is represented internally
#: as NUMBER." Oracle's actual binary floating-point types are BINARY_FLOAT and
#: BINARY_DOUBLE. Treating Oracle FLOAT as approximate produced a BLOCKER whose failure
#: scenario — a sum drifting by cents — is simply false there, and an Oracle DBA would
#: rebut it in one sentence and then distrust the rest of the review. The real finding on
#: an Oracle FLOAT money column is TYP-004: no declared scale.
_EXACT_FLOAT_DIALECTS = {"oracle"}
_ORACLE_IEEE = {"binary_float", "binary_double"}


def _family(col, dialect=None):
    """Coarse type family: text/exact/approx/date/bool/binary/unknown.

    Prefers a family stamped onto the column by `stamp_families()`, which is where
    dialect-awareness is applied. Falling back to a dialect-free reading keeps the
    helper usable in isolation and in tests.
    """
    stamped = col.get("_family")
    if stamped:
        return stamped
    t = _base_type(col)
    if t in TZ_AWARE or t in DATE_TYPES:
        return "date"
    if t in BOOL_TYPES:
        return "bool"
    if dialect in _EXACT_FLOAT_DIALECTS and t in {"float", "real"}:
        return "exact"
    if dialect in _EXACT_FLOAT_DIALECTS and t in _ORACLE_IEEE:
        return "approx"
    if t in APPROX_NUMERIC:
        return "approx"
    if t in EXACT_NUMERIC:
        return "exact"
    if t in TEXT_TYPES:
        return "text"
    if t in BINARY_TYPES:
        return "binary"
    return "unknown"


def stamp_families(model):
    """Annotate every column with its dialect-aware type family, in place.

    Called once before any check runs. Doing it here rather than inside each check keeps
    the checks pure functions of the model and keeps the dialect rule in exactly one
    place — there are a dozen call sites for `_family`, and a dialect test in each of
    them is a dozen chances to get it wrong.
    """
    dialect = ((model.get("meta") or {}).get("dialect") or "").strip().lower()
    for t in model.get("tables", []):
        for c in t.get("columns") or []:
            c["_family"] = _family(c, dialect)
    return model


def _fq(table, col=None):
    parts = [p for p in (table.get("schema"), table.get("name")) if p]
    if col:
        parts.append(col if isinstance(col, str) else col.get("name"))
    return ".".join(parts)


def _tables(model, persistable_only=False):
    for t in model.get("tables", []):
        if t.get("kind") == "view":
            continue
        if persistable_only and t.get("persistable") is False:
            continue
        yield t


def _cols(table):
    return table.get("columns", []) or []


def _has_token(colname, tokens):
    n = _norm(colname)
    return n in tokens or any(tok in n for tok in tokens if len(tok) > 4)


def _pk(table):
    return [c.lower() for c in (table.get("primary_key") or [])]


def _uniques(table):
    """All uniqueness assertions: unique constraints, unique indexes, and the PK."""
    out = []
    if table.get("primary_key"):
        out.append([c.lower() for c in table["primary_key"]])
    for u in table.get("unique_constraints") or []:
        out.append([c.lower() for c in u])
    for ix in table.get("indexes") or []:
        if ix.get("unique"):
            out.append([c.lower() for c in ix.get("columns", [])])
    return out


def _has_exclusion(table):
    """True if the table declares an overlap-exclusion constraint.

    PostgreSQL's EXCLUDE ... WITH && and SQL:2011's WITHOUT OVERLAPS are the same
    assertion. It is also a uniqueness assertion — over a period rather than a point —
    so KEY-003 must count it, or every correctly-built temporal table is reported as
    admitting duplicates.
    """
    for ck in table.get("checks") or []:
        blob = f"{ck.get('name') or ''} {ck.get('expression') or ''}".lower()
        if "exclude" in blob or "overlap" in blob or "&&" in blob:
            return True
    for ix in table.get("indexes") or []:
        if (ix.get("kind") or "").lower() == "exclusion":
            return True
        if "overlap" in (ix.get("name") or "").lower():
            return True
    return False


def _has_period(table):
    names = {_norm(c["name"]) for c in _cols(table)}
    return bool(names & VALID_FROM_TOKENS) and bool(names & VALID_TO_TOKENS)


def _is_key_shaped(colname):
    """A column in an identifier role: never a monetary amount or a measure, whatever it
    is named. `payment_method_id` contains 'payment' and is not money; `deed_number`
    ends in 'number' and is not a quantity.

    `number`, `reference` and `identifier` are here because an independent review pass
    withdrew TYP-002 twice over exactly that suffix — `CUSTOMER_NUMBER` and `DEED_NUMBER`
    are identifiers correctly held as text, and calling them "a quantity in a character
    type" is the kind of confident false positive that costs a review its credibility.

    `num` is deliberately absent while `no` and `number` are present. The SQL Style
    Guide's uniform suffixes define `_num` as a numeric value and `_id` as the unique
    identifier, so `ROW_COUNT_NUM` is a quantity while `INVOICE_NO` and `DEED_NUMBER` are
    identifiers. Treating `_num` as an identifier silently disabled TYP-002.
    """
    n = _norm(colname)
    return n.endswith(("id", "key", "sk", "code", "ref", "reference", "no",
                       "number", "seq", "identifier", "guid", "uuid", "barcode",
                       "isbn", "iban"))

def _indexed_leading(table):
    """Columns that lead some index (or the PK), i.e. usefully indexed on their own."""
    lead = set()
    if table.get("primary_key"):
        lead.add(table["primary_key"][0].lower())
    for ix in table.get("indexes") or []:
        cols = ix.get("columns") or []
        if cols:
            lead.add(cols[0].lower())
    return lead


def _pk_lookup(model):
    """table-name(lower) -> set of its key column names(lower), from PK and uniques."""
    out = {}
    for t in model.get("tables", []):
        keys = set()
        for u in _uniques(t):
            keys.update(u)
        out[(t.get("name") or "").lower()] = keys
    return out


def _mendix_validations(table):
    """{attribute_lower: set(rule_types_lower)} for a Mendix entity."""
    out = defaultdict(set)
    for v in table.get("validation_rules") or []:
        out[(v.get("attribute") or "").lower()].add((v.get("type") or "").lower())
    return out


def _is_junction(table):
    """A table that exists to resolve a many-to-many: mostly FK columns, little else."""
    fks = table.get("foreign_keys") or []
    if len(fks) < 2:
        return False
    fk_cols = {c.lower() for fk in fks for c in fk.get("columns", [])}
    payload = [c for c in _cols(table)
               if c["name"].lower() not in fk_cols
               and c["name"].lower() not in _pk(table)
               and not _has_token(c["name"], CREATED_TOKENS | CHANGED_TOKENS | ACTOR_TOKENS)]
    return len(payload) <= 1


# ======================================================================================
# STRUCTURE
# ======================================================================================

def STR_001(model):
    """EAV triple: an entity reference, an attribute-name column, and a value column."""
    for t in _tables(model):
        names = {_norm(c["name"]) for c in _cols(t)}
        attr_like = names & {"attributename", "attribute", "attrname", "fieldname",
                             "propertyname", "property", "key", "keyname", "paramname",
                             "attributecode", "fieldcode"}
        val_like = names & {"value", "attributevalue", "attrvalue", "fieldvalue",
                            "propertyvalue", "paramvalue", "datavalue", "textvalue"}
        ent_like = [c for c in _cols(t) if _norm(c["name"]).endswith("id")]
        if attr_like and val_like and ent_like and len(_cols(t)) <= 12:
            yield {"object": _fq(t),
                   "evidence": f"columns {sorted(attr_like)} + {sorted(val_like)} beside "
                               f"an entity reference: the attribute name is data, so no "
                               f"type or requiredness can be declared for any attribute"}


def STR_002(model):
    for t in _tables(model):
        if _norm(t["name"]) in GENERIC_ENTITY_NAMES:
            yield {"object": _fq(t),
                   "evidence": f"entity named '{t['name']}' names no business concept"}


def STR_003(model):
    pat = re.compile(r"^(.*?)[ _]?(\d{1,3})$")
    for t in _tables(model):
        groups = defaultdict(list)
        for c in _cols(t):
            m = pat.match(c["name"])
            stem = m.group(1) if m else None
            if not stem:
                continue
            # A one- or two-character stem still counts once there are enough of them.
            # The original `len(stem) > 2` gate meant an entity carrying F01..F61 — the
            # largest repeating group imaginable — produced no finding at all, which a
            # reviewer had to raise by hand.
            if len(stem) > 2 or len(groups[_norm(stem)]) >= 0:
                groups[_norm(stem)].append(c["name"])
        for stem, cols in groups.items():
            if len(stem) <= 2 and len(cols) < 5:
                continue
            if len(cols) >= 3:
                yield {"object": _fq(t),
                       "evidence": f"{len(cols)} numbered columns share the stem "
                                   f"'{stem}': {', '.join(sorted(cols)[:5])}"
                                   f"{' ...' if len(cols) > 5 else ''}"}


def STR_004(model):
    pat = re.compile(r"^(.*?)[ _]?((19|20)\d{2}|\d{4}_?\d{2}|q[1-4])$", re.I)
    stems = defaultdict(list)
    for t in _tables(model):
        m = pat.match(t["name"])
        if m and m.group(1) and len(m.group(1)) > 2:
            stems[_norm(m.group(1))].append(t["name"])
    for stem, names in stems.items():
        if len(names) >= 2:
            yield {"object": stem,
                   "evidence": f"{len(names)} tables differ only by period suffix: "
                               f"{', '.join(sorted(names)[:6])}"
                               f"{' ...' if len(names) > 6 else ''}"}


def STR_005(model):
    for t in _tables(model):
        n = len(_cols(t))
        if n > 60:
            yield {"object": _fq(t), "evidence": f"{n} columns"}


def _is_fact(table):
    n = _norm(table["name"])
    if table.get("role") == "fact":
        return True
    return n.startswith("fact") or n.endswith("fact") or n.startswith("f_")


def STR_006(model):
    """Prescreen for an undeclared grain.

    Tier B: whether the stated grain is *right* needs judgement. But whether one is
    stated at all is mechanical, and it is the question that most often turns out to
    have no answer.
    """
    for t in _tables(model):
        if not _is_fact(t):
            continue
        if (t.get("grain") or "").strip():
            continue
        desc = (t.get("description") or "").strip()
        if desc and re.search(r"\bgrain\b|\bone row per\b|\bat the level of\b", desc, re.I):
            continue
        yield {"object": _fq(t),
               "evidence": "fact table with no grain statement in `grain` or the "
                           "description; confirm with the modeller what one row means "
                           "before trusting any measure on it"}


# ======================================================================================
# KEYS
# ======================================================================================

def KEY_001(model):
    for t in _tables(model):
        pk = _pk(t)
        if len(pk) == 1 and pk[0] in {"id", "pk", "key"}:
            yield {"object": _fq(t, pk[0]),
                   "evidence": f"primary key is named '{pk[0]}'"}


def KEY_002(model):
    for t in _tables(model):
        if not t.get("primary_key") and not (t.get("unique_constraints") or []):
            yield {"object": _fq(t),
                   "evidence": "no primary key and no unique constraint: rows cannot be "
                               "addressed individually"}


def KEY_003(model):
    for t in _tables(model):
        pk = _pk(t)
        if len(pk) != 1:
            continue
        pkc = pk[0]
        # Only a surrogate if the PK is a single numeric/identity column.
        col = next((c for c in _cols(t) if c["name"].lower() == pkc), None)
        if not col:
            continue
        if _family(col) not in {"exact", "unknown"}:
            continue
        looks_surrogate = (col.get("is_identity")
                           or _norm(pkc) in {"id", "pk", "key"}
                           or _norm(pkc) == _norm(t["name"]) + "id"
                           or _norm(pkc).endswith("sk")
                           or _norm(pkc).endswith("surrogatekey"))
        if not looks_surrogate:
            continue
        other_uniques = [u for u in _uniques(t) if u != pk]
        if other_uniques:
            continue
        # A junction table's identity is its FK pair; KEY-007 handles that case.
        if _is_junction(t):
            continue
        # An effective-dated table's business key includes the period, and an exclusion
        # constraint is the assertion that enforces it. KEY-008 and TEM-005 own those
        # cases with advice specific to them.
        if _has_exclusion(t) or _has_period(t):
            continue
        if len(_cols(t)) < 2:
            continue
        yield {"object": _fq(t, pkc),
               "evidence": "surrogate key is the only uniqueness assertion on the "
                           "table, so nothing prevents the same business entity being "
                           "stored twice under two different ids"}


def KEY_004(model):
    for t in _tables(model):
        pk = t.get("primary_key") or []
        if len(pk) >= 4 and not _is_junction(t):
            yield {"object": _fq(t),
                   "evidence": f"{len(pk)}-column primary key ({', '.join(pk)}) "
                               f"propagates into every child table and join predicate"}


def KEY_005(model):
    descriptive = {"name", "title", "label", "email", "description", "desc", "address",
                   "comment", "text", "fullname", "companyname"}
    for t in _tables(model):
        for pkc in _pk(t):
            col = next((c for c in _cols(t) if c["name"].lower() == pkc), None)
            if not col:
                continue
            if _family(col) == "text" and (_norm(pkc) in descriptive
                                           or any(d in _norm(pkc) for d in descriptive)):
                yield {"object": _fq(t, pkc),
                       "evidence": f"'{col['name']}' ({col.get('type')}) is a mutable "
                                   f"descriptive value serving as the key"}


def KEY_006(model):
    for t in _tables(model):
        keycols = set(_pk(t))
        for u in _uniques(t):
            keycols.update(u)
        for fk in t.get("foreign_keys") or []:
            keycols.update(c.lower() for c in fk.get("columns", []))
        for c in _cols(t):
            if c["name"].lower() in keycols and _family(c) == "approx":
                yield {"object": _fq(t, c),
                       "evidence": f"key column typed {c.get('type')}: approximate "
                                   f"numerics do not compare exactly"}


def KEY_007(model):
    for t in _tables(model):
        if not _is_junction(t):
            continue
        fk_cols = sorted({c.lower() for fk in (t.get("foreign_keys") or [])
                          for c in fk.get("columns", [])})
        if not fk_cols:
            continue
        for u in _uniques(t):
            if sorted(set(u)) == fk_cols:
                break
        else:
            yield {"object": _fq(t),
                   "evidence": f"associative table with no uniqueness on its key pair "
                               f"({', '.join(fk_cols)}): the same relationship can be "
                               f"asserted twice"}


def KEY_008(model):
    for t in _tables(model):
        cols = {_norm(c["name"]) for c in _cols(t)}
        has_period = bool(cols & VALID_FROM_TOKENS) and bool(cols & VALID_TO_TOKENS)
        if not has_period:
            continue
        pk = _pk(t)
        if len(pk) != 1:
            continue
        col = next((c for c in _cols(t) if c["name"].lower() == pk[0]), None)
        if not col:
            continue
        looks_surrogate = (col.get("is_identity") or _norm(pk[0]).endswith("sk")
                           or _norm(pk[0]) in {"id"}
                           or _norm(pk[0]) == _norm(t["name"]) + "sk")
        if not looks_surrogate:
            yield {"object": _fq(t, pk[0]),
                   "evidence": "table carries an effective-date period but its primary "
                               "key is a single natural key, so a second version of the "
                               "same entity cannot be stored"}


# ======================================================================================
# INTEGRITY
# ======================================================================================

def INT_001(model):
    keys = _pk_lookup(model)
    declared = {}
    for t in model.get("tables", []):
        declared[(t.get("name") or "").lower()] = {
            c.lower() for fk in (t.get("foreign_keys") or [])
            for c in fk.get("columns", [])}
    # Candidate referents: a column named <something>_id whose stem names a real table.
    table_names = {(t.get("name") or "").lower() for t in model.get("tables", [])}
    for t in _tables(model):
        tname = (t.get("name") or "").lower()
        pk = set(_pk(t))
        for c in _cols(t):
            n = _norm(c["name"])
            if not n.endswith("id") or n in {"id"}:
                continue
            if c["name"].lower() in declared.get(tname, set()):
                continue
            if c["name"].lower() in pk:
                continue
            stem = n[:-2]
            cands = [x for x in table_names
                     if _norm(x) == stem or _norm(x) == stem + "s"
                     or _norm(x).endswith("_" + stem) or _norm(x) == stem.rstrip("s")]
            cands = [x for x in cands if x != tname]
            if cands and keys.get(cands[0]):
                yield {"object": _fq(t, c),
                       "evidence": f"names a reference to '{cands[0]}' (which has a key) "
                                   f"but no foreign key constraint is declared"}


def INT_002(model):
    for t in _tables(model):
        names = {_norm(c["name"]): c["name"] for c in _cols(t)}
        pk = {c.lower() for c in (t.get("primary_key") or [])}
        tname = _norm(t["name"])
        for n, orig in names.items():
            if not n.endswith("id") or n == "id":
                continue
            # PRODUCT.PRODUCT_ID beside PRODUCT.PRODUCT_TYPE is a primary key beside a
            # category attribute, not a polymorphic pair. Withdrawn as a false positive
            # by an independent review pass, and correctly so: a table's own key can
            # never be a polymorphic reference to somewhere else.
            if orig.lower() in pk:
                continue
            stem = n[:-2]
            if stem == tname or stem == tname.rstrip("s"):
                continue
            for suffix in ("type", "typeid", "typecode", "table", "tablename",
                           "entity", "entityname", "class", "classname", "kind",
                           "objecttype", "reftype", "sourcetype", "ownertype"):
                partner = stem + suffix
                if partner in names:
                    yield {"object": _fq(t, orig),
                           "evidence": f"'{orig}' is paired with '{names[partner]}': the "
                                       f"referenced table is a runtime value, so no "
                                       f"foreign key can be declared"}
                    break


def INT_003(model):
    for t in _tables(model):
        for fk in t.get("foreign_keys") or []:
            if not fk.get("on_delete"):
                yield {"object": f"{_fq(t)} -> {fk.get('ref_table')}",
                       "evidence": f"foreign key on ({', '.join(fk.get('columns', []))}) "
                                   f"declares no ON DELETE action"}


def INT_004(model):
    for t in _tables(model):
        tname = (t.get("name") or "").lower()
        for fk in t.get("foreign_keys") or []:
            if (fk.get("ref_table") or "").lower() != tname:
                continue
            checks = " ".join((c.get("expression") or "") for c in (t.get("checks") or []))
            cols = [c.lower() for c in fk.get("columns", [])]
            if not any(c in checks.lower() for c in cols):
                yield {"object": f"{_fq(t)}.{', '.join(fk.get('columns', []))}",
                       "evidence": "self-referencing hierarchy with no check constraint "
                                   "or documented guard against cycles"}


def INT_005(model):
    types = {}
    for t in model.get("tables", []):
        for c in _cols(t):
            types[((t.get("name") or "").lower(), c["name"].lower())] = c
    for t in _tables(model):
        for fk in t.get("foreign_keys") or []:
            rt = (fk.get("ref_table") or "").lower()
            for lc, rc in zip(fk.get("columns", []), fk.get("ref_columns", []) or []):
                a = types.get(((t.get("name") or "").lower(), lc.lower()))
                b = types.get((rt, (rc or "").lower()))
                if not a or not b:
                    continue
                if _family(a) != _family(b) and "unknown" not in (_family(a), _family(b)):
                    yield {"object": _fq(t, lc),
                           "evidence": f"{a.get('type')} references {rt}.{rc} which is "
                                       f"{b.get('type')}"}


def INT_006(model):
    keys = _pk_lookup(model)
    known = set(keys)
    for t in _tables(model):
        for fk in t.get("foreign_keys") or []:
            rt = (fk.get("ref_table") or "").lower()
            if rt in known and not keys.get(rt):
                yield {"object": f"{_fq(t)} -> {fk.get('ref_table')}",
                       "evidence": f"referenced table '{fk.get('ref_table')}' has no "
                                   f"primary key or unique constraint, so the referent "
                                   f"is ambiguous and the join can fan out"}


def INT_008(model):
    """Prescreen: a child copies a parent attribute with no composite FK enforcing it.

    Tier B, because whether the copy must agree is a business question — a shipping
    address deliberately snapshotted at order time must NOT track the customer's current
    one, and reporting that as a defect would be wrong. The check surfaces the pair; a
    reviewer decides which kind it is.

    Both an independent reviewer and this skill's own reviewer found this on the same
    schema before any rule existed for it, which is what earned it a place here.
    """
    cols_by_table = {(t.get("name") or "").lower():
                     {c["name"].lower() for c in _cols(t)}
                     for t in model.get("tables", [])}
    # Grouped by the shared column, not emitted per relationship. On a schema that
    # carries currency_id widely this fired seven times on ten tables, of which two were
    # real — and seven separate candidates asking the same question is a list a reviewer
    # skims rather than works. One question with the pairs listed underneath is the same
    # information at a tenth of the reading cost.
    pairs = defaultdict(list)
    for t in _tables(model):
        own = {c["name"].lower() for c in _cols(t)}
        pk = set(_pk(t))
        for fk in t.get("foreign_keys") or []:
            rt = (fk.get("ref_table") or "").lower()
            parent_cols = cols_by_table.get(rt)
            if not parent_cols:
                continue
            fk_cols = {c.lower() for c in fk.get("columns", [])}
            audit = {_norm(x) for x in CREATED_TOKENS | CHANGED_TOKENS | ACTOR_TOKENS}
            for c in sorted((own & parent_cols) - fk_cols - pk):
                if not _is_key_shaped(c) or _norm(c) in audit:
                    continue
                pairs[c].append(f"{_fq(t)} -> {fk.get('ref_table')} "
                                f"(FK on {', '.join(fk.get('columns', []))})")
    for col, rels in sorted(pairs.items()):
        yield {"object": f"shared column '{col}'",
               "evidence": f"carried on both sides of {len(rels)} parent/child "
                           f"relationship(s) with no composite foreign key forcing "
                           f"agreement: " + "; ".join(rels[:6])
                           + (" ..." if len(rels) > 6 else "")
                           + ". Decide per relationship: a deliberate snapshot should be "
                             "documented as one, a value that must track the parent needs "
                             "the key widened"}


def INT_007(model):
    mandatory = defaultdict(set)
    for t in _tables(model):
        tname = (t.get("name") or "").lower()
        nn = {c["name"].lower() for c in _cols(t) if c.get("nullable") is False}
        for fk in t.get("foreign_keys") or []:
            if all(c.lower() in nn for c in fk.get("columns", [])):
                mandatory[tname].add((fk.get("ref_table") or "").lower())
    seen = set()
    for a, targets in mandatory.items():
        for b in targets:
            if a in mandatory.get(b, set()) and (b, a) not in seen:
                seen.add((a, b))
                yield {"object": f"{a} <-> {b}",
                       "evidence": "each table holds a NOT NULL foreign key to the "
                                   "other, so neither row can be inserted first"}


# ======================================================================================
# TYPES
# ======================================================================================

def TYP_001(model):
    date_named = {"date", "dt", "time", "timestamp", "on", "at", "day", "when"}
    for t in _tables(model):
        for c in _cols(t):
            if _family(c) != "text":
                continue
            w = _words(c["name"])
            if w and (w[-1] in date_named or _has_token(c["name"], VALID_FROM_TOKENS |
                                                        VALID_TO_TOKENS | CREATED_TOKENS |
                                                        CHANGED_TOKENS)):
                if _has_token(c["name"], HIJRI_TOKENS):
                    continue  # LOC-003 owns this case, with better advice
                yield {"object": _fq(t, c),
                       "evidence": f"named as a date but typed {c.get('type')}: sorts "
                                   f"lexically and admits invalid dates"}


def TYP_002(model):
    num_named = {"amount", "amt", "qty", "quantity", "count", "total", "number",
                 "num", "price", "cost", "rate", "percent", "percentage", "score",
                 "balance", "age", "year", "seq", "sequence"}
    for t in _tables(model):
        for c in _cols(t):
            if _family(c) != "text":
                continue
            # An identifier is not a quantity. `_NUMBER`, `_REF`, `_CODE` and friends are
            # correctly held as text, often precisely because they carry leading zeros,
            # prefixes or check characters that a numeric type would destroy.
            if _is_key_shaped(c["name"]):
                continue
            if _has_token(c["name"], NATIONAL_ID_TOKENS | PHONE_TOKENS):
                continue  # correctly text; TYP-008 covers the inverse
            w = _words(c["name"])
            if w and w[-1] in num_named:
                yield {"object": _fq(t, c),
                       "evidence": f"named as a quantity but typed {c.get('type')}"}


def TYP_003(model):
    for t in _tables(model):
        for c in _cols(t):
            if _family(c) == "approx" and _has_token(c["name"], MONEY_TOKENS):
                yield {"object": _fq(t, c),
                       "evidence": f"monetary column typed {c.get('type')}: binary "
                                   f"floating point cannot represent decimal amounts "
                                   f"exactly, and the error accumulates"}


def TYP_004(model):
    for t in _tables(model):
        for c in _cols(t):
            if _family(c) != "exact":
                continue
            if not (_has_token(c["name"], MONEY_TOKENS)
                    or _has_token(c["name"], MEASURE_TOKENS)):
                continue
            if _base_type(c) in {"int", "integer", "smallint", "bigint", "tinyint"}:
                continue  # integer minor units is a legitimate choice
            if c.get("scale") is None and c.get("precision") is None:
                yield {"object": _fq(t, c),
                       "evidence": f"{c.get('type')} with no precision or scale: the "
                                   f"effective scale becomes a platform default"}


def TYP_005(model):
    for t in _tables(model):
        checks = " ".join((c.get("expression") or "") for c in (t.get("checks") or [])).lower()
        for c in _cols(t):
            if _family(c) != "text":
                continue
            if (c.get("length") or 99) > 1:
                continue
            w = _words(c["name"])
            if not (w and (w[0] in {"is", "has", "can"} or w[-1] in {"flag", "ind",
                                                                    "indicator", "yn"})):
                continue
            if c["name"].lower() in checks:
                continue
            yield {"object": _fq(t, c),
                   "evidence": f"single-character flag typed {c.get('type')} with no "
                               f"CHECK constraint: the domain is unrestricted"}


def TYP_006(model):
    for t in _tables(model):
        keycols = set(_pk(t))
        for u in _uniques(t):
            keycols.update(u)
        for fk in t.get("foreign_keys") or []:
            keycols.update(c.lower() for c in fk.get("columns", []))
        for c in _cols(t):
            if c["name"].lower() in keycols and _base_type(c) in UNBOUNDED_TEXT:
                yield {"object": _fq(t, c),
                       "evidence": f"unbounded {c.get('type')} in a key position"}


def TYP_007(model):
    for t in _tables(model):
        wide = [c for c in _cols(t)
                if _family(c) == "text" and (c.get("length") or 0) >= 4000]
        texty = [c for c in _cols(t) if _family(c) == "text"]
        if texty and len(wide) >= 3 and len(wide) >= 0.6 * len(texty):
            yield {"object": _fq(t),
                   "evidence": f"{len(wide)} of {len(texty)} text columns are at or "
                               f"above 4000 characters: no domain analysis is recorded "
                               f"in the widths"}


def TYP_008(model):
    for t in _tables(model):
        for c in _cols(t):
            if _family(c) not in {"exact", "approx"}:
                continue
            if _has_token(c["name"], NATIONAL_ID_TOKENS):
                yield {"object": _fq(t, c),
                       "evidence": f"formatted identifier typed {c.get('type')}: "
                                   f"grouping and any leading zeros are lost, and a "
                                   f"check digit cannot be validated on a number"}
            elif _has_token(c["name"], PHONE_TOKENS):
                yield {"object": _fq(t, c),
                       "evidence": f"phone number typed {c.get('type')}: loses leading "
                                   f"zeros and international prefixes"}


def TYP_009(model):
    for t in _tables(model):
        for c in _cols(t):
            if _family(c) != "date":
                continue
            if _base_type(c) in TZ_AWARE:
                continue
            if _has_token(c["name"], CREATED_TOKENS | CHANGED_TOKENS):
                if _base_type(c) == "date":
                    continue  # a plain date has no time to be ambiguous about
                yield {"object": _fq(t, c),
                       "evidence": f"audit instant typed {c.get('type')} with no time "
                                   f"zone"}


# ======================================================================================
# NULLABILITY
# ======================================================================================

def _is_sentinel(col, default):
    vocab = SENTINELS_KEY if _is_key_shaped(col["name"]) else SENTINELS
    return default in vocab or any(w == default.strip("'")
                                   for w in SENTINEL_UNKNOWN_WORDS)


def NUL_001(model):
    for t in _tables(model):
        for c in _cols(t):
            d = (str(c.get("default")) if c.get("default") is not None else "").strip().lower()
            if not d:
                continue
            if _is_sentinel(c, d):
                yield {"object": _fq(t, c),
                       "evidence": f"DEFAULT {c.get('default')} stands in for absence "
                                   f"but participates in joins and aggregates as a real "
                                   f"value"}


def NUL_002(model):
    for t in _tables(model):
        cols = _cols(t)
        if len(cols) < 5:
            continue
        known = [c for c in cols if c.get("nullable") is not None]
        if len(known) < 5:
            continue
        pk = set(_pk(t))
        opt = [c for c in known if c.get("nullable") and c["name"].lower() not in pk]
        ratio = len(opt) / max(1, len(known) - len(pk))
        if ratio >= 0.95:
            yield {"object": _fq(t),
                   "evidence": f"{len(opt)} of {len(known)} columns are nullable: no "
                               f"requirement is recorded in the schema"}


def NUL_003(model):
    for t in _tables(model):
        for c in _cols(t):
            if c.get("nullable") is not False:
                continue
            d = (str(c.get("default")) if c.get("default") is not None else "").strip().lower()
            if not d:
                continue
            if _is_sentinel(c, d):
                yield {"object": _fq(t, c),
                       "evidence": f"NOT NULL with DEFAULT {c.get('default')}: the "
                                   f"constraint reports completeness the data does not "
                                   f"have"}


# ======================================================================================
# REFERENCE DATA
# ======================================================================================

def _lookup_tables(model):
    for t in _tables(model):
        cols = _cols(t)
        if not (2 <= len(cols) <= 6):
            continue
        n = _norm(t["name"])
        looks = (n.startswith("lk") or n.startswith("lu") or n.startswith("ref")
                 or n.endswith("type") or n.endswith("types") or n.endswith("status")
                 or n.endswith("code") or n.endswith("codes") or n.endswith("category")
                 or n.endswith("lookup") or n.endswith("domain")
                 or (any(_norm(c["name"]) in {"code", "name", "label", "description",
                                              "value"} for c in cols)
                     and len(cols) <= 4))
        if looks:
            yield t


def REF_001(model):
    shapes = defaultdict(list)
    for t in _lookup_tables(model):
        sig = tuple(sorted(_norm(c["name"]) for c in _cols(t)))
        shapes[sig].append(t["name"])
    if len(shapes) >= 3:
        detail = "; ".join(f"({', '.join(sig)}) x{len(v)}"
                           for sig, v in sorted(shapes.items(), key=lambda kv: -len(kv[1]))[:4])
        yield {"object": "reference data",
               "evidence": f"{len(shapes)} distinct lookup-table shapes across "
                           f"{sum(len(v) for v in shapes.values())} lookup tables: {detail}"}


def REF_002(model):
    for t in _tables(model):
        names = {_norm(c["name"]) for c in _cols(t)}
        type_disc = names & {"domaintype", "domaintypeid", "typeid", "type", "typecode",
                             "category", "categoryid", "lookuptype", "listname",
                             "codetype", "group", "groupid", "domainid", "setid"}
        value_like = names & {"value", "datavalue", "code", "name", "label",
                              "description", "text", "displayvalue"}
        n = _norm(t["name"])
        generic_name = any(k in n for k in ("domaindata", "lookup", "reference", "codes",
                                            "codelist", "genericlookup", "allcodes",
                                            "systemcode", "commoncode", "masterdata",
                                            "listofvalues", "lov"))
        if type_disc and value_like and (generic_name or len(_cols(t)) <= 8):
            yield {"object": _fq(t),
                   "evidence": f"discriminator {sorted(type_disc)} plus value columns "
                               f"{sorted(value_like)}: every code list shares one table, "
                               f"so no column can be constrained to the right list"}


def REF_003(model):
    for t in _lookup_tables(model):
        names = {_norm(c["name"]) for c in _cols(t)}
        has_code = bool(names & {"code", "codevalue", "shortcode", "abbreviation", "abbr"})
        has_label = bool(names & {"name", "label", "description", "displayname", "title",
                                  "namear", "nameen"})
        if has_label and not has_code:
            yield {"object": _fq(t),
                   "evidence": "carries a label but no stable code column, so the label "
                               "is doing double duty as identity and as display text"}


def REF_004(model):
    for t in _lookup_tables(model):
        names = {_norm(c["name"]) for c in _cols(t)}
        if names & {"code", "codevalue", "shortcode", "abbreviation", "abbr"}:
            continue
        labels = names & {"name", "label", "description", "displayname", "title"}
        if not labels:
            continue
        stable = False
        for u in _uniques(t):
            if any(_norm(c) in {"code", "codevalue", "shortcode"} for c in u):
                stable = True
        if not stable:
            yield {"object": _fq(t),
                   "evidence": "identity rests on a surrogate id plus an editable "
                               "label; nothing survives a label correction"}


def REF_005(model):
    for t in _tables(model):
        for ck in t.get("checks") or []:
            expr = (ck.get("expression") or "")
            vals = re.findall(r"'([^']{1,40})'", expr)
            if len(vals) >= 5 and re.search(r"\bin\b", expr, re.I):
                yield {"object": f"{_fq(t)} / {ck.get('name') or 'check'}",
                       "evidence": f"{len(vals)} literal values hard-coded in a CHECK "
                                   f"({', '.join(vals[:5])} ...): adding one is a "
                                   f"schema migration"}
    for e in model.get("enums") or []:
        if len(e.get("values") or []) >= 8:
            yield {"object": f"enum {e.get('name')}",
                   "evidence": f"{len(e['values'])} values defined in the type: adding "
                               f"one is a DDL change"}


# ======================================================================================
# TEMPORALITY
# ======================================================================================

def TEM_001(model):
    for t in _tables(model):
        if _is_junction(t) or len(_cols(t)) < 3:
            continue
        names = {_norm(c["name"]) for c in _cols(t)}
        if names & CREATED_TOKENS or names & CHANGED_TOKENS:
            continue
        if any(_has_token(c["name"], CREATED_TOKENS | CHANGED_TOKENS) for c in _cols(t)):
            continue
        yield {"object": _fq(t),
               "evidence": "no created or last-changed timestamp"}


def TEM_002(model):
    for t in _tables(model):
        fk_cols = {c.lower() for fk in (t.get("foreign_keys") or [])
                   for c in fk.get("columns", [])}
        for c in _cols(t):
            if not _has_token(c["name"], {"createdby", "updatedby", "modifiedby",
                                          "changedby", "enteredby", "approvedby"}):
                continue
            if c["name"].lower() in fk_cols:
                continue
            if _family(c) == "text":
                yield {"object": _fq(t, c),
                       "evidence": f"audit actor stored as {c.get('type')} with no "
                                   f"foreign key to a user entity"}


def TEM_003(model):
    """Soft delete applied inconsistently.

    A soft-delete column whose description explains the decision is exempt. The rule is
    about a policy that was never made, not about a documented localised choice — and
    reporting a justified decision as an accident is how a review loses the argument it
    should win. It also puts the incentive in the right place: write down why, and the
    finding goes away.
    """
    softs, hards, documented = [], [], []
    for t in _tables(model):
        if _is_junction(t):
            continue
        delcols = [c for c in _cols(t) if _norm(c["name"]) in SOFT_DELETE_STRICT]
        if delcols:
            if any((c.get("description") or "").strip() for c in delcols):
                documented.append(t["name"])
            else:
                softs.append(t["name"])
        else:
            hards.append(t["name"])
    total = len(softs) + len(hards) + len(documented)
    # No lower ratio bound beyond "at least one of each". A single soft-delete flag in a
    # model that otherwise hard-deletes is the commonest real form of this defect —
    # someone added it to one table — and a 15% floor was silently exempting exactly
    # that case. The ratio goes in the evidence so a reviewer can dismiss a deliberate
    # localised choice.
    if softs and len(hards) >= 2 and total >= 4:
        note = (f" ({len(documented)} further table(s) soft-delete with the decision "
                f"documented, and are excluded)" if documented else "")
        yield {"object": "model",
               "evidence": f"{len(softs)} of {total} tables carry an undocumented delete "
                           f"flag and {len(hards)} do not (soft: "
                           f"{', '.join(sorted(softs)[:4])}; hard: "
                           f"{', '.join(sorted(hards)[:4])}): deletion semantics depend "
                           f"on which table you ask{note}"}


def TEM_004(model):
    """Soft delete versus uniqueness.

    There are three states here, not two, and conflating the last two is how a real
    defect passes review:

      1. Unique constraint ignores the delete flag entirely — a soft-deleted row keeps
         occupying its key and the value can never be reused.
      2. Unique index is *partial* (`WHERE deleted_at IS NULL`) — the remedy.
      3. Unique index is *composite*, merely including the delete column — the classic
         wrong fix, and worse than (1). Because NULLs compare distinct in a unique index,
         `unique (customer_ref, deleted_at)` permits **unlimited** duplicate
         `customer_ref` among live rows while constraining only the deleted ones. It
         looks deliberate, it reads as handled, and it enforces nothing where it matters.

    An earlier version of this check treated (3) as satisfying the rule, and a reviewer
    working without it caught a live instance the check had passed.
    """
    for t in _tables(model):
        delcols = [c["name"] for c in _cols(t) if _norm(c["name"]) in SOFT_DELETE_STRICT]
        if not delcols:
            continue
        dl = {d.lower() for d in delcols}
        pk = _pk(t)

        # Partial unique indexes filtering on the delete column: the remedy.
        partial_ok = set()
        for ix in t.get("indexes") or []:
            if not ix.get("unique"):
                continue
            pred = (ix.get("where") or "").lower()
            if pred and any(d in pred for d in dl):
                partial_ok.add(tuple(sorted(c.lower() for c in ix.get("columns", []))))

        for ix in t.get("indexes") or []:
            if not ix.get("unique"):
                continue
            cols = [c.lower() for c in ix.get("columns", [])]
            if not (set(cols) & dl):
                continue
            if (ix.get("where") or ""):
                continue  # partial: this is the remedy, not the defect
            payload = [c for c in cols if c not in dl]
            if not payload:
                continue
            yield {"object": f"{_fq(t)} / {ix.get('name') or 'unique index'}"
                             f"({', '.join(ix.get('columns', []))})",
                   "evidence": f"the delete flag '{delcols[0]}' is a *column* of this "
                               f"unique index rather than a filter on it. NULLs compare "
                               f"distinct, so this permits unlimited duplicate "
                               f"({', '.join(payload)}) among live rows and constrains "
                               f"only deleted ones — the opposite of the intent. It "
                               f"needs to be a partial index: "
                               f"UNIQUE ({', '.join(payload)}) WHERE "
                               f"{delcols[0]} IS NULL"}

        for u in _uniques(t):
            if u == pk or set(u) & dl:
                continue
            if tuple(sorted(u)) in partial_ok:
                continue
            yield {"object": f"{_fq(t)} / unique({', '.join(u)})",
                   "evidence": f"unique constraint ignores the delete flag "
                               f"'{delcols[0]}', so a soft-deleted row keeps "
                               f"occupying its key and the value can never be "
                               f"reused"}


def TEM_005(model):
    for t in _tables(model):
        names = {_norm(c["name"]): c["name"] for c in _cols(t)}
        f = next((v for k, v in names.items() if k in VALID_FROM_TOKENS), None)
        to = next((v for k, v in names.items() if k in VALID_TO_TOKENS), None)
        if not (f and to):
            continue
        if _has_exclusion(t):
            continue
        # A unique constraint that includes the period start is a weaker but real
        # guard: it prevents two rows starting on the same day, though not partial
        # overlap. Treat it as satisfying the rule and let the reviewer judge whether
        # partial overlap matters, rather than reporting a table that clearly thought
        # about the problem.
        if any(_norm(f) in {_norm(c) for c in u} for u in _uniques(t)):
            continue
        yield {"object": f"{_fq(t)} ({f}, {to})",
               "evidence": "effective-dated period with no exclusion or WITHOUT "
                           "OVERLAPS constraint: two versions can be valid at once"}


def TEM_006(model):
    open_null, open_sentinel = [], []
    for t in _tables(model):
        for c in _cols(t):
            if _norm(c["name"]) not in VALID_TO_TOKENS:
                continue
            d = (str(c.get("default")) if c.get("default") is not None else "").lower()
            if "9999" in d or "31-dec-9999" in d:
                open_sentinel.append(_fq(t, c))
            elif c.get("nullable"):
                open_null.append(_fq(t, c))
    if open_null and open_sentinel:
        yield {"object": "model",
               "evidence": f"open-ended periods use NULL in {len(open_null)} place(s) "
                           f"({open_null[0]}) and a high sentinel in "
                           f"{len(open_sentinel)} ({open_sentinel[0]}): every predicate "
                           f"must handle both"}


def TEM_007(model):
    for t in _tables(model):
        names = {_norm(c["name"]) for c in _cols(t)}
        if not (names & VALID_FROM_TOKENS and names & VALID_TO_TOKENS):
            continue
        if names & CURRENT_FLAG_TOKENS:
            continue
        if not _norm(t["name"]).startswith("dim") and t.get("role") != "dimension":
            continue
        yield {"object": _fq(t),
               "evidence": "Type 2 dimension with effective dates but no current-row "
                           "indicator, so every consumer writes its own boundary "
                           "predicate"}


# ======================================================================================
# SEMANTICS / NAMING
# ======================================================================================

def NAM_001(model):
    for t in _tables(model):
        for c in _cols(t):
            if _norm(c["name"]) in GENERIC_NAMES and len(_words(c["name"])) == 1:
                yield {"object": _fq(t, c),
                       "evidence": f"'{c['name']}' carries no object-class or "
                                   f"representation term"}


def _casing(name):
    if not name:
        return "other"
    if "_" in name:
        return "upper_snake" if name.isupper() else "snake"
    if name.isupper():
        return "upper"
    if name[0].isupper() and any(ch.islower() for ch in name):
        return "pascal"
    if name[0].islower() and any(ch.isupper() for ch in name):
        return "camel"
    if name.islower():
        return "lower"
    return "other"


#: Casing labels that are the same convention seen through a one-word name. `customer`
#: is indistinguishable from snake_case, and `CUSTOMER` from UPPER_SNAKE, so collapsing
#: them stops NAM-002 reporting a mixed convention in a perfectly consistent schema.
_CASE_EQUIV = {"lower": "snake", "upper": "upper_snake"}


def NAM_002(model):
    styles = Counter(_CASE_EQUIV.get(s, s)
                     for s in (_casing(t["name"]) for t in _tables(model)))
    styles = {k: v for k, v in styles.items() if k != "other"}
    if len(styles) >= 2 and sum(styles.values()) >= 5:
        ranked = sorted(styles.items(), key=lambda kv: (-kv[1], kv[0]))
        # No ratio threshold: a single deviant table is exactly the case worth naming,
        # and it is the case a percentage floor hides. Name the offenders so the finding
        # is actionable in one glance.
        minority_styles = {k for k, _ in ranked[1:]}
        offenders = sorted(t["name"] for t in _tables(model)
                           if _CASE_EQUIV.get(_casing(t["name"]),
                                              _casing(t["name"])) in minority_styles)
        yield {"object": "model",
               "evidence": "table naming mixes "
                           + ", ".join(f"{k} ({v})" for k, v in ranked)
                           + f"; the minority is {', '.join(offenders[:6])}"
                           + (" ..." if len(offenders) > 6 else "")}


def NAM_003(model):
    plural, singular = [], []
    for t in _tables(model):
        w = _words(t["name"])
        if not w:
            continue
        last = w[-1]
        if last.endswith("s") and not last.endswith("ss") and len(last) > 3:
            plural.append(t["name"])
        else:
            singular.append(t["name"])
    total = len(plural) + len(singular)
    # No ratio threshold, for the same reason as NAM-002: the single table that broke
    # the convention is the actionable finding, and a percentage floor is precisely what
    # hides it.
    if total >= 5 and plural and singular:
        odd = plural if len(plural) <= len(singular) else singular
        kind = "plural" if odd is plural else "singular"
        yield {"object": "model",
               "evidence": f"{len(plural)} plural and {len(singular)} singular table "
                           f"names; the {kind} minority is "
                           f"{', '.join(sorted(odd)[:6])}"
                           f"{' ...' if len(odd) > 6 else ''}"}


def NAM_004(model):
    for t in _tables(model):
        n = t["name"].lower()
        for p in TYPE_PREFIXES:
            if n.startswith(p) and len(n) > len(p) + 2:
                yield {"object": _fq(t),
                       "evidence": f"name begins with the type prefix '{p}'"}
                break


#: Short words that are words, not abbreviations. Deliberately generous: this check
#: exists to push undocumented jargon into a glossary, and the remedy for a false
#: positive is to add the term to `model.glossary` — which is the outcome we wanted
#: anyway. Being slightly noisy in a MINOR rule whose fix is "write it down" is a better
#: failure than missing the abbreviations that actually confuse people.
_SHORT_WORDS = {
    "id", "no", "code", "name", "type", "date", "time", "day", "year", "week",
    "hour", "min", "max", "sum", "avg", "text", "note", "city", "town", "area",
    "zone", "unit", "size", "rank", "step", "line", "item", "page", "part", "path",
    "rate", "role", "rule", "sort", "user", "case", "cost", "fee", "form", "goal",
    "kind", "lang", "level", "link", "list", "logo", "mode", "next", "prev", "open",
    "paid", "plan", "port", "post", "read", "seq", "sex", "slug", "span", "star",
    "task", "team", "term", "tier", "top", "url", "uri", "used", "view", "void",
    "wage", "flag", "from", "into", "over", "sent", "seen", "done", "new", "old",
    "end", "row", "key", "map", "set", "tag", "ref", "job", "log", "net", "sub",
    "add", "age", "amt", "qty", "num", "desc", "tax", "vat", "iban", "email",
    "phone", "photo", "price", "title", "value", "count", "order", "owner", "state",
    "total", "true", "false", "start", "stop", "since", "until", "notes", "label",
    "grade", "score", "group", "class", "index", "batch", "cycle", "entry", "event",
    "month", "quart", "stage", "token", "topic", "delta", "first", "last", "main",
    "iso", "utc", "gmt", "pdf", "csv", "xml", "json", "html", "http", "api", "sql",
    "ar", "en", "fr", "de", "es", "ur", "hi", "zh", "ru", "tr", "fa",
    # English function words. snake_case splitting produces these constantly —
    # created_at yields "at", changed_by yields "by", is_active yields "is" — and
    # flagging them buries the two or three real abbreviations in noise.
    "at", "by", "is", "in", "on", "of", "to", "for", "and", "or", "not", "has", "can",
    "was", "per", "via", "the", "a", "an", "as", "if", "it", "no", "so", "up", "out",
    "off", "all", "any", "one", "two", "num",
}


#: Upper bound on what counts as a suspected abbreviation. Four, not five: the
#: abbreviations that actually confuse people are short (cust, addr, amt, qty, dept,
#: txn, acct, invc), while five-letter tokens are overwhelmingly real words (sales,
#: valid, order, price). Raising this to five doubled the false-positive rate on the
#: sound fixture without catching anything new on the flawed one.
_ABBREV_MAX = 4


def NAM_005(model):
    glossary = {_norm(k) for k in (model.get("glossary") or {})}
    counts = Counter()
    where = defaultdict(set)
    for t in _tables(model):
        for w in _words(t["name"]):
            if 2 <= len(w) <= _ABBREV_MAX and w not in _SHORT_WORDS \
                    and _norm(w) not in glossary:
                counts[w] += 1
                where[w].add(t["name"])
        for c in _cols(t):
            for w in _words(c["name"]):
                if w.isdigit() or not (2 <= len(w) <= _ABBREV_MAX):
                    continue
                if w in _SHORT_WORDS or _norm(w) in glossary:
                    continue
                counts[w] += 1
                where[w].add(t["name"])
    for w, n in sorted(counts.items()):
        if n >= 3 and len(where[w]) >= 2:
            yield {"object": f"token '{w}'",
                   "evidence": f"'{w}' appears in {n} identifiers across "
                               f"{len(where[w])} tables with no glossary entry; supply "
                               f"model.glossary to silence terms that are legitimate"}


def NAM_006(model):
    for t in _tables(model):
        tn = _norm(t["name"])
        for c in _cols(t):
            if _norm(c["name"]) == tn:
                yield {"object": _fq(t, c),
                       "evidence": f"column '{c['name']}' has the same name as its table"}


def NAM_007(model):
    for t in _tables(model):
        if _norm(t["name"]) in RESERVED:
            yield {"object": _fq(t),
                   "evidence": f"'{t['name']}' is a reserved word"}
        for c in _cols(t):
            if _norm(c["name"]) in RESERVED:
                yield {"object": _fq(t, c),
                       "evidence": f"'{c['name']}' is a reserved word"}


def _concept_key(colname):
    """Strip an identifier down to its likely concept, for synonym detection."""
    w = _words(colname)
    w = [x for x in w if x not in {"id", "no", "num", "number", "code", "key", "fk",
                                   "pk", "sk", "ref"}]
    return "".join(w)


def NAM_008(model):
    """Synonyms: one concept, several names.

    The trap here is that ISO 11179 *expects* `currency_id` and `currency_code` to share
    an object-class term — they are the same concept with different representation terms,
    which is correct, not a synonym. So stripping the representation term and flagging
    every collision reports good naming as a defect.

    What is actually wrong is a *truncated* object-class term: `cust_id` beside
    `customer_id`. The discriminator used here is that a genuine object class appears
    somewhere as a table name or a full word, whereas a truncation does not. `product` is
    a table, so `product_id` beside `product_price_history_id` is fine; `cust` is not a
    table, so `cust_no` beside `customer_number` is flagged.
    """
    table_stems = {_norm(t["name"]) for t in _tables(model)}
    for stem in list(table_stems):
        table_stems.add(stem.rstrip("s"))

    stems = defaultdict(set)
    for t in _tables(model):
        for c in _cols(t):
            n = _norm(c["name"])
            if not (n.endswith(("id", "no", "code", "num", "ref", "key"))):
                continue
            k = _concept_key(c["name"])
            if 3 <= len(k):
                stems[k].add(f"{t['name']}.{c['name']}")

    ordered = sorted(stems, key=len)
    for i, short in enumerate(ordered):
        if short in table_stems or short in _SHORT_WORDS or len(short) > 6:
            continue
        for long in ordered[i + 1:]:
            if long == short or not long.startswith(short):
                continue
            if long not in table_stems and long.rstrip("s") not in table_stems:
                continue
            yield {"object": f"concept '{long}'",
                   "evidence": f"also named '{short}' — {', '.join(sorted(stems[short]))} "
                               f"beside {', '.join(sorted(stems[long])[:3])}; "
                               f"'{short}' is a truncation, since no table carries that "
                               f"name"}
            break


def NAM_009(model):
    holders = defaultdict(set)
    for t in _tables(model):
        for c in _cols(t):
            holders[_norm(c["name"])].add((t["name"], _family(c), _base_type(c)))
    for name, uses in holders.items():
        fams = {f for _, f, _ in uses}
        if len(uses) >= 2 and len(fams) >= 2 and "unknown" not in fams:
            detail = "; ".join(f"{tn}.{name} {bt}" for tn, _, bt in sorted(uses)[:4])
            yield {"object": f"column name '{name}'",
                   "evidence": f"same name, different types: {detail}"}


def NAM_010(model):
    for t in _tables(model):
        names = {_norm(c["name"]) for c in _cols(t)}
        has_ccy = bool(names & CURRENCY_TOKENS) or any(
            any(tok in n for tok in CURRENCY_TOKENS) for n in names)
        has_unit = bool(names & UNIT_TOKENS) or any(
            any(tok in n for tok in UNIT_TOKENS) for n in names)
        for c in _cols(t):
            if _family(c) not in {"exact", "approx"}:
                continue
            # A column in a key role is never an amount, however it is named:
            # `payment_method_id` contains 'payment' and is not money.
            if _is_key_shaped(c["name"]):
                continue
            n = _norm(c["name"])
            if _has_token(c["name"], MONEY_TOKENS) and not has_ccy:
                if any(u in n for u in ("cents", "fils", "minor", "usd", "aed", "eur",
                                        "gbp", "sar", "pct", "percent", "rate")):
                    continue
                yield {"object": _fq(t, c),
                       "evidence": "monetary column with no currency column on the "
                                   "table and no currency in the name"}
            elif _has_token(c["name"], MEASURE_TOKENS) and not has_unit:
                if any(u in n for u in ("kg", "gram", "cm", "mm", "metre", "meter",
                                        "km", "days", "hours", "minutes", "seconds",
                                        "pct", "percent", "count")):
                    continue
                yield {"object": _fq(t, c),
                       "evidence": "measured column with no unit column on the table "
                                   "and no unit in the name"}


def NAM_011(model):
    for t in _tables(model):
        for obj, name in [(_fq(t), t["name"])] + [(_fq(t, c), c["name"]) for c in _cols(t)]:
            if len(name.encode("utf-8")) > 30:
                yield {"object": obj,
                       "evidence": f"identifier is {len(name.encode('utf-8'))} bytes"}
            elif not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name or ""):
                yield {"object": obj,
                       "evidence": f"identifier '{name}' uses characters outside "
                                   f"[A-Za-z0-9_] or does not start with a letter"}


def NAM_012(model):
    for t in _tables(model):
        for c in _cols(t):
            w = _words(c["name"])
            if not w:
                continue
            bt = _base_type(c)
            if w[-1] == "date" and bt in {"timestamp", "timestamptz", "datetime",
                                          "datetime2", "datetimeoffset",
                                          "timestamp with time zone"}:
                yield {"object": _fq(t, c),
                       "evidence": f"named '_date' but typed {c.get('type')}: joins to "
                                   f"a date dimension will miss on the time component"}


# ======================================================================================
# RELATIONSHIPS
# ======================================================================================

def REL_003(model):
    """Prescreen for Kimball's centipede fact table.

    Tier B: whether 21 dimension keys is wrong depends on whether they are genuine
    independent dimensions or hierarchy levels that should have been folded in. Counting
    them is mechanical; deciding is not.
    """
    for t in _tables(model):
        if not _is_fact(t):
            continue
        keys = [c["name"] for c in _cols(t)
                if _norm(c["name"]).endswith(("key", "sk"))
                and c["name"].lower() not in {k.lower() for k in (t.get("primary_key") or [])}]
        if len(keys) > 20:
            yield {"object": _fq(t),
                   "evidence": f"{len(keys)} dimension keys. Check whether these are "
                               f"independent dimensions or hierarchy levels that belong "
                               f"inside their parent dimension: "
                               f"{', '.join(sorted(keys)[:8])} ..."}


def REL_001(model):
    plural_hint = re.compile(r"(list|ids|codes|tags|values|names|numbers|s)$", re.I)
    for t in _tables(model):
        fk_cols = {c.lower() for fk in (t.get("foreign_keys") or [])
                   for c in fk.get("columns", [])}
        for c in _cols(t):
            if _family(c) != "text":
                continue
            if c["name"].lower() in fk_cols:
                continue
            n = _norm(c["name"])
            if not plural_hint.search(c["name"]):
                continue
            if not (n.endswith("ids") or n.endswith("list") or n.endswith("codes")
                    or n.endswith("tags")):
                continue
            yield {"object": _fq(t, c),
                   "evidence": f"'{c['name']}' ({c.get('type')}) names a collection in a "
                               f"single text column with no foreign key"}


# ======================================================================================
# PERFORMANCE
# ======================================================================================

def PER_001(model):
    for t in _tables(model):
        lead = _indexed_leading(t)
        for fk in t.get("foreign_keys") or []:
            cols = fk.get("columns") or []
            if not cols:
                continue
            if cols[0].lower() in lead:
                continue
            yield {"object": _fq(t, cols[0]),
                   "evidence": f"foreign key to {fk.get('ref_table')} with no index "
                               f"leading on '{cols[0]}': deleting a parent row scans "
                               f"this table"}


def PER_002(model):
    for t in _tables(model):
        ixs = [ix for ix in (t.get("indexes") or []) if ix.get("columns")]
        if len(ixs) > 8:
            yield {"object": _fq(t),
                   "evidence": f"{len(ixs)} indexes on one table"}
        leads = defaultdict(list)
        for ix in ixs:
            leads[ix["columns"][0].lower()].append(ix.get("name") or "?")
        for col, names in leads.items():
            if len(names) >= 2:
                yield {"object": _fq(t, col),
                       "evidence": f"{len(names)} indexes lead with '{col}': "
                                   f"{', '.join(names)}"}


def PER_003(model):
    for t in _tables(model):
        for c in _cols(t):
            desc = (c.get("description") or "").lower()
            if not desc:
                continue
            if not re.search(r"\bunique\b|\bno duplicates\b|\bone per\b", desc):
                continue
            # A description that names the enforcing mechanism is documenting it, not
            # asserting an unenforced rule. `deleted_at: "...the partial unique index
            # below keeps customer_ref reusable"` mentions uniqueness *about another
            # column*, and reading that as an undeclared constraint on deleted_at is a
            # confident false positive of exactly the kind that gets a review dismissed.
            if re.search(r"\b(index|constraint|uq_|ix_|pk_)\b", desc):
                continue
            declared = {x for u in _uniques(t) for x in u}
            if c["name"].lower() not in declared:
                yield {"object": _fq(t, c),
                       "evidence": f"description asserts uniqueness (\""
                                   f"{(c.get('description') or '')[:70]}...\") but no "
                                   f"unique constraint or index declares it"}


# ======================================================================================
# GOVERNANCE
# ======================================================================================

#: Personal-data tokens that are personal whoever the subject is. A date of birth or a
#: passport number belongs to a natural person by definition.
PII_UNAMBIGUOUS = {
    "dob", "birthdate", "dateofbirth", "birth", "nationalid", "nationalno", "ssn",
    "socialsec", "passport", "emiratesid", "eid", "iqama", "gender", "sex",
    "nationality", "religion", "maritalstatus", "photo", "signature", "fingerprint",
    "biometric", "salary", "wage", "income", "deviceid",
}
#: Tokens that are personal data *if the entity is a natural person* and ordinary
#: business data otherwise. A `customer` table documented as "an organisation the
#: business sells to" has a `legal_name` that is a company name — reporting it as
#: unclassified personal data is a confident false positive, and one a reviewer working
#: from the table's own description caught.
PII_IF_PERSON = PII_TOKENS - PII_UNAMBIGUOUS
#: Words in a table description that settle it as an organisation rather than a person.
_ORG_WORDS = ("organisation", "organization", "company", "business", "supplier",
              "vendor", "corporate", "entity the business", "legal entity",
              "institution", "agency", "firm", "contracting entity")
_PERSON_WORDS = ("person", "individual", "people", "employee", "staff", "citizen",
                 "resident", "applicant", "beneficiary", "patient", "student",
                 "customer who", "natural person", "contact")


def _subject_is_organisation(table):
    """True when the table's own description settles it as a non-person subject."""
    desc = (table.get("description") or "").lower()
    if not desc:
        return False
    if any(w in desc for w in _PERSON_WORDS):
        return False
    return any(w in desc for w in _ORG_WORDS)


def GOV_001(model):
    for t in _tables(model):
        org = _subject_is_organisation(t)
        for c in _cols(t):
            if c.get("classification"):
                continue
            n = _norm(c["name"])
            unambiguous = _has_token(c["name"], PII_UNAMBIGUOUS) or n in PII_UNAMBIGUOUS
            ambiguous = _has_token(c["name"], PII_IF_PERSON) or n in PII_IF_PERSON
            if unambiguous:
                yield {"object": _fq(t, c),
                       "evidence": f"'{c['name']}' holds personal data with no "
                                   f"classification recorded"}
            elif ambiguous and not org:
                yield {"object": _fq(t, c),
                       "evidence": f"'{c['name']}' holds personal data with no "
                                   f"classification recorded, if this entity represents "
                                   f"a natural person. Confirm the subject: on an "
                                   f"organisation this is ordinary business data, and "
                                   f"the table description does not settle it"}


def GOV_002(model):
    for t in _tables(model):
        for c in _cols(t):
            if not (_has_token(c["name"], CREDENTIAL_TOKENS)
                    or _norm(c["name"]) in CREDENTIAL_TOKENS):
                continue
            fam = _family(c)
            typ = _base_type(c)
            if typ in {"hashed string", "hashedstring"}:
                continue
            if fam in {"text", "binary", "unknown"}:
                if re.search(r"hash|digest|bcrypt|argon|salt", _norm(c["name"])):
                    continue
                yield {"object": _fq(t, c),
                       "evidence": f"credential column typed {c.get('type')}: readable "
                                   f"by anyone with table or backup access"}


# ======================================================================================
# DOCUMENTATION
# ======================================================================================

def DOC_001(model):
    for t in _tables(model):
        if not (t.get("description") or "").strip():
            yield {"object": _fq(t), "evidence": "no description"}


def _is_self_evident(table, col):
    """Columns whose meaning is fully carried by their name plus their constraint.

    Hoberman's Completeness category warns against gold plating in the same breath as
    incompleteness, and demanding a sentence for `created_at` is gold plating. Counting
    those against documentation coverage would push a model toward writing 'the date the
    row was created' eighty times, which is how documentation becomes something people
    stop reading.
    """
    n = _norm(col["name"])
    if n in CREATED_TOKENS | CHANGED_TOKENS | ACTOR_TOKENS | CURRENT_FLAG_TOKENS:
        return True
    if col.get("is_pk") and n == _norm(table["name"]) + "id":
        return True
    fk_cols = {c.lower() for fk in (table.get("foreign_keys") or [])
               for c in fk.get("columns", [])}
    if col["name"].lower() in fk_cols and n.endswith("id"):
        return True  # a named FK to a documented table explains itself
    return False


def DOC_002(model):
    total = documented = 0
    for t in _tables(model):
        for c in _cols(t):
            if _is_self_evident(t, c):
                continue
            total += 1
            if (c.get("description") or "").strip():
                documented += 1
    if total and documented / total < 0.5:
        yield {"object": "model",
               "evidence": f"{documented} of {total} columns documented "
                           f"({documented / total:.0%}), excluding audit columns, "
                           f"self-named keys and foreign keys, which explain themselves"}


def DOC_003(model):
    for t in _tables(model):
        for c in _cols(t):
            d = (c.get("description") or "").strip()
            if not d:
                continue
            if _norm(d) in {_norm(c["name"]), "the" + _norm(c["name"])} or \
               _norm(d).replace("the", "") == _norm(c["name"]):
                yield {"object": _fq(t, c),
                       "evidence": f"description '{d}' restates the column name"}


def DOC_004(model):
    for t in _tables(model):
        for c in _cols(t):
            if not (c.get("calculated") or c.get("generated")):
                continue
            if (c.get("description") or "").strip() or c.get("expression"):
                continue
            yield {"object": _fq(t, c),
                   "evidence": "derived column with no derivation recorded"}


# ======================================================================================
# EXTENSIBILITY
# ======================================================================================

def EVO_001(model):
    named = re.compile(r"^(spare|reserved|filler|udf|user_?def|user_?field|extra|attr|"
                       r"attribute|field|custom|flex|misc|col|column|text|num|value)"
                       r"_?\d{1,3}$", re.I)
    # A fixed vocabulary of placeholder words misses the commonest real form, which is a
    # meaningless short prefix plus a number — F01..F61, C1..C40, X001..X120. Those carry
    # no less meaning than `spare1`; they just were not on the list. Treat a stem of at
    # most three characters, repeated five or more times, as a placeholder family.
    anon = re.compile(r"^([A-Za-z]{1,3})_?\d{1,3}$")
    for t in _tables(model):
        hits = [c["name"] for c in _cols(t) if named.match(c["name"])]
        fams = defaultdict(list)
        for c in _cols(t):
            m = anon.match(c["name"])
            if m and not named.match(c["name"]):
                fams[m.group(1).lower()].append(c["name"])
        for stem, cols in sorted(fams.items()):
            if len(cols) >= 5:
                hits.extend(cols)
        if hits:
            hits = sorted(set(hits))
            yield {"object": _fq(t),
                   "evidence": f"{len(hits)} columns carry no meaning in their names: "
                               f"{', '.join(hits[:6])}"
                               f"{' ...' if len(hits) > 6 else ''}. Whatever they hold is "
                               f"defined outside the database, in an application that a "
                               f"migration is usually replacing"}


def EVO_003(model):
    unknownish = {"unknown", "unspecified", "notset", "none", "na", "notapplicable",
                  "other", "undefined", "default", "empty", "blank"}
    for e in model.get("enums") or []:
        vals = {_norm(v) for v in (e.get("values") or [])}
        if vals and not (vals & unknownish):
            yield {"object": f"enum {e.get('name')}",
                   "evidence": f"no unknown or unspecified member among "
                               f"{len(vals)} values"}


# ======================================================================================
# LOCALISATION
# ======================================================================================

def _lang_pairs(table):
    """{stem: {lang: column_name}} for columns ending in a language suffix."""
    out = defaultdict(dict)
    for c in _cols(table):
        w = _words(c["name"])
        if len(w) < 2:
            continue
        if w[-1] in LANG_SUFFIXES:
            out["".join(w[:-1])][w[-1]] = c["name"]
    return out


def LOC_001(model):
    for t in _tables(model):
        for stem, langs in _lang_pairs(t).items():
            if len(langs) > 2:
                yield {"object": _fq(t),
                       "evidence": f"'{stem}' exists in {len(langs)} languages as "
                                   f"parallel columns ({', '.join(sorted(langs))}): a "
                                   f"new language is a schema change"}


def LOC_002(model):
    langs_seen = Counter()
    for t in _tables(model):
        for langs in _lang_pairs(t).values():
            # .keys(), not the dict: Counter.update(dict) treats the values as counts,
            # and these values are column-name strings, so it raised a TypeError and the
            # rule went unexamined on every bilingual model.
            langs_seen.update(langs.keys())
    if len(langs_seen) < 2:
        return
    primary = {l for l, _ in langs_seen.most_common(2)}
    for t in _tables(model):
        for stem, langs in _lang_pairs(t).items():
            missing = primary - set(langs)
            if missing and len(langs) >= 1:
                yield {"object": f"{_fq(t)}.{stem}_*",
                       "evidence": f"has {sorted(langs)} but not "
                                   f"{sorted(missing)}, while the model uses "
                                   f"{sorted(primary)} elsewhere"}


def LOC_003(model):
    for t in _tables(model):
        names = {_norm(c["name"]): c for c in _cols(t)}
        hijri = [c for n, c in names.items() if any(h in n for h in HIJRI_TOKENS)]
        if not hijri:
            continue
        greg = [c for n, c in names.items()
                if _family(c) == "date" and not any(h in n for h in HIJRI_TOKENS)]
        for hc in hijri:
            if _family(hc) != "date" and not greg:
                yield {"object": _fq(t, hc),
                       "evidence": f"Hijri date typed {hc.get('type')} with no "
                                   f"Gregorian date column on the table to serve as the "
                                   f"canonical value"}


def LOC_004(model):
    for t in _tables(model):
        names = {_norm(c["name"]): c for c in _cols(t)}
        hijri = [c for n, c in names.items() if any(h in n for h in HIJRI_TOKENS)]
        greg = [c for n, c in names.items() if any(g in n for g in GREGORIAN_TOKENS)]
        if hijri and greg:
            derived = [c for c in hijri + greg
                       if c.get("generated") or c.get("calculated")
                       or (c.get("description") or "").lower().find("derived") >= 0]
            if not derived:
                yield {"object": _fq(t),
                       "evidence": f"both '{hijri[0]['name']}' and '{greg[0]['name']}' "
                                   f"are independently writable, with no generated "
                                   f"column, trigger or documented derivation tying "
                                   f"them together"}


# ======================================================================================
# CONSISTENCY
# ======================================================================================

def CON_001(model):
    # NAM-009 reports the naming failure; this reports the type divergence for keys,
    # where the consequence is a broken join rather than a confused reader.
    holders = defaultdict(set)
    for t in _tables(model):
        for c in _cols(t):
            n = _norm(c["name"])
            if n.endswith("id") and n != "id":
                holders[n].add((t["name"], _base_type(c), _family(c)))
    for name, uses in holders.items():
        fams = {f for _, _, f in uses}
        if len(uses) >= 2 and len(fams) >= 2 and "unknown" not in fams:
            detail = "; ".join(f"{tn} {bt}" for tn, bt, _ in sorted(uses)[:4])
            yield {"object": f"key column '{name}'",
                   "evidence": f"declared with different types: {detail}"}


def CON_002(model):
    found = defaultdict(set)
    for t in _tables(model):
        for c in _cols(t):
            n = _norm(c["name"])
            if n in CREATED_TOKENS:
                found["created"].add(c["name"])
            elif n in CHANGED_TOKENS:
                found["changed"].add(c["name"])
    for concept, names in found.items():
        if len({_norm(n) for n in names}) >= 2:
            yield {"object": f"audit '{concept}'",
                   "evidence": f"spelled {len(names)} ways: {', '.join(sorted(names))}"}


# ======================================================================================
# MENDIX
# ======================================================================================

def MDX_001(model):
    for t in _tables(model, persistable_only=True):
        v = _mendix_validations(t)
        if any("unique" in rules_ for rules_ in v.values()):
            continue
        if len(_cols(t)) < 2:
            continue
        cands = [c["name"] for c in _cols(t)
                 if re.search(r"code|number|no$|reference|email|identifier|key",
                              _norm(c["name"]))]
        hint = f" — candidates: {', '.join(cands[:3])}" if cands else \
               " — and no attribute looks like a business key, which is itself the finding"
        yield {"object": _fq(t),
               "evidence": f"no Unique validation rule on any attribute{hint}"}


def MDX_002(model):
    for a in model.get("associations") or []:
        db = (a.get("delete_behavior_parent") or a.get("delete_behavior") or "").lower()
        if db and "keep" not in db:
            continue
        mult = (a.get("multiplicity") or "").lower()
        if "many" not in mult:
            continue
        yield {"object": a.get("name") or f"{a.get('parent')}->{a.get('child')}",
               "evidence": f"delete behaviour is 'Keep associated object(s)' (the "
                           f"default) on a {a.get('multiplicity')} association: "
                           f"deleting a {a.get('parent')} leaves its "
                           f"{a.get('child')} objects associated with nothing"}


def MDX_003(model):
    pairs = Counter()
    names = defaultdict(list)
    for a in model.get("associations") or []:
        key = tuple(sorted([(a.get("parent") or ""), (a.get("child") or "")]))
        pairs[key] += 1
        names[key].append(a.get("name") or "?")
    for key, n in pairs.items():
        if n >= 2:
            yield {"object": " <-> ".join(key),
                   "evidence": f"{n} associations between the same pair: "
                               f"{', '.join(names[key])}"}


def MDX_004(model):
    parent = {}
    for t in model.get("tables", []):
        if t.get("generalization"):
            parent[t["name"]] = t["generalization"]

    def depth(name, seen=()):
        if name in seen or name not in parent:
            return 0
        return 1 + depth(parent[name], seen + (name,))

    for name in parent:
        d = depth(name)
        if d > 2:
            chain, cur = [name], name
            while cur in parent and len(chain) < 8:
                cur = parent[cur]
                chain.append(cur)
            yield {"object": name,
                   "evidence": f"inheritance depth {d} (MXP009 limit is 2): "
                               f"{' -> '.join(chain)}"}


def MDX_005(model):
    for t in _tables(model, persistable_only=True):
        lead = {c.lower() for ix in (t.get("indexes") or []) if ix.get("columns")
                for c in [ix["columns"][0]]}
        for c in _cols(t):
            uses = c.get("used_in") or []
            if not ({"sort", "xpath", "search"} & set(uses)):
                continue
            if c["name"].lower() in lead:
                continue
            yield {"object": _fq(t, c),
                   "evidence": f"used in {', '.join(sorted(set(uses)))} but no index "
                               f"leads with it (MXP003 / MXP007)"}


def MDX_006(model):
    for t in _tables(model):
        leads = defaultdict(list)
        for ix in t.get("indexes") or []:
            if ix.get("columns"):
                leads[ix["columns"][0].lower()].append(ix.get("name") or "?")
        for col, names in leads.items():
            if len(names) >= 2:
                yield {"object": _fq(t, col),
                       "evidence": f"{len(names)} indexes lead with '{col}'"}


def MDX_007(model):
    for t in _tables(model):
        for c in _cols(t):
            if not c.get("calculated"):
                continue
            uses = c.get("used_in") or []
            if not uses:
                yield {"object": _fq(t, c),
                       "evidence": "calculated attribute that nothing reads, still "
                                   "executed on every retrieve (MXP002)"}
            elif {"grid", "list", "datacontainer", "sort", "xpath"} & set(uses):
                yield {"object": _fq(t, c),
                       "evidence": f"calculated attribute used in "
                                   f"{', '.join(sorted(set(uses)))}: the microflow runs "
                                   f"once per row on every retrieve (MXP001)"}


def MDX_008(model):
    for t in _tables(model):
        for c in _cols(t):
            if not _has_token(c["name"], MONEY_TOKENS):
                continue
            bt = _base_type(c)
            if bt in {"decimal"}:
                continue
            if bt in {"integer", "long"} and re.search(r"cents|fils|minor", _norm(c["name"])):
                continue
            yield {"object": _fq(t, c),
                   "evidence": f"monetary attribute typed {c.get('type')}; Mendix "
                               f"documents Decimal as the type for money"}


def MDX_009(model):
    for t in _tables(model):
        for c in _cols(t):
            if not (_has_token(c["name"], CREDENTIAL_TOKENS)
                    or _norm(c["name"]) in CREDENTIAL_TOKENS):
                continue
            if _base_type(c) in {"hashed string", "hashedstring"}:
                continue
            yield {"object": _fq(t, c),
                   "evidence": f"credential attribute typed {c.get('type')} rather than "
                               f"Hashed string"}


def MDX_010(model):
    for t in _tables(model, persistable_only=True):
        sm = t.get("system_members") or {}
        off = [k for k in ("createdDate", "changedDate", "owner", "changedBy")
               if not sm.get(k)]
        if len(off) == 4:
            yield {"object": _fq(t),
                   "evidence": "no system members enabled: nothing records when the "
                               "object changed or who changed it"}
        elif off:
            yield {"object": _fq(t),
                   "evidence": f"system members not enabled: {', '.join(off)}"}


def MDX_011(model):
    for t in _tables(model):
        sm = t.get("system_members") or {}
        for c in _cols(t):
            if not _has_token(c["name"], {"createdby", "changedby", "modifiedby",
                                          "updatedby", "username", "userlogin",
                                          "loginid"}):
                continue
            if _base_type(c) in {"string", "varchar", "text"}:
                yield {"object": _fq(t, c),
                       "evidence": f"audit actor as a String attribute while "
                                   f"Store 'owner'={bool(sm.get('owner'))} and "
                                   f"Store 'changedBy'={bool(sm.get('changedBy'))}; the "
                                   f"platform members are associations to System.User"}


def MDX_012(model):
    for t in _tables(model):
        n = t["name"] or ""
        problems = []
        if "_" in n:
            problems.append("contains an underscore")
        if _casing(n) not in {"pascal", "upper"} and n:
            problems.append(f"is {_casing(n)}, not PascalCase")
        w = _words(n)
        if w and w[-1].endswith("s") and not w[-1].endswith("ss") and len(w[-1]) > 3:
            problems.append("is plural")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", n or ""):
            problems.append("uses characters outside [A-Za-z0-9]")
        if problems:
            yield {"object": _fq(t),
                   "evidence": f"entity name '{n}' " + "; ".join(problems)}
        for c in _cols(t):
            cn = c["name"] or ""
            if cn.startswith("_"):
                continue  # the sanctioned marker for a technical attribute
            if "_" in cn or _casing(cn) not in {"pascal", "upper"}:
                yield {"object": _fq(t, c),
                       "evidence": f"attribute name '{cn}' is not PascalCase without "
                                   f"underscores"}


def MDX_013(model):
    for t in _tables(model):
        if t.get("persistable") is False:
            continue
        for c in _cols(t):
            n = _norm(c["name"])
            if any(k in n for k in ("selected", "isselected", "temp", "tmp", "uistate",
                                    "searchfield", "filtervalue", "currentpage",
                                    "sortcolumn")):
                yield {"object": _fq(t, c),
                       "evidence": f"'{c['name']}' looks like UI state on a persistable "
                                   f"entity: it will be written to the database and "
                                   f"outlive the session"}


def MDX_014(model):
    for a in model.get("associations") or []:
        if "many-to-many" in (a.get("multiplicity") or "").lower():
            yield {"object": a.get("name") or f"{a.get('parent')}<->{a.get('child')}",
                   "evidence": "reference set (many-to-many): Mendix retrieves the IDs "
                               "per row on every list retrieve"}


#: Entity-name fragments suggesting a role or lifecycle stage rather than a permanent
#: kind of thing. Deliberately conservative — this is a tier-B prescreen, and the point
#: is to put the question in front of a reviewer, not to conclude.
_ROLE_WORDS = {"applicant", "beneficiary", "recipient", "claimant", "customer",
               "supplier", "vendor", "employee", "manager", "approver", "reviewer",
               "requester", "owner", "member", "candidate", "student", "patient",
               "donor", "tenant", "guest", "subscriber", "senior", "junior", "active",
               "inactive", "pending", "approved", "rejected", "archived", "former",
               "prospective", "trial", "premium", "verified"}


def MDX_020(model):
    """An attribute declared on a specialisation that its generalisation also declares.

    Under class-table inheritance that column exists once, on the generalisation. A second
    declaration on the child is not extra storage — it is a second claim on one column.
    """
    by_name = {t["name"]: t for t in _tables(model)}
    for t in _tables(model):
        parent = t.get("generalization")
        if not parent or parent not in by_name:
            continue
        # Walk the whole chain: an attribute may be declared two levels up.
        ancestors, cur, seen = {}, parent, set()
        while cur in by_name and cur not in seen:
            seen.add(cur)
            for c in _cols(by_name[cur]):
                ancestors.setdefault(_norm(c["name"]), cur)
            cur = by_name[cur].get("generalization")
        dupes = [(c["name"], ancestors[_norm(c["name"])])
                 for c in _cols(t) if _norm(c["name"]) in ancestors]
        if not dupes:
            continue
        detail = ", ".join(f"{n} (declared on {a})" for n, a in sorted(dupes)[:5])
        yield {"object": _fq(t),
               "evidence": f"{len(dupes)} attribute(s) redeclared from an ancestor: "
                           f"{detail}{' ...' if len(dupes) > 5 else ''}. Each of these is "
                           f"one physical column on the ancestor's table, not two"}


def MDX_018(model):
    """Prescreen: generalization used for something that looks like a role or a stage.

    Tier B — whether a subtype is a permanent kind of thing or a passing role is a
    judgement about the business, not the schema. But the question is worth forcing,
    because the cost of getting it wrong in Mendix is unusually high: an object's type
    cannot change, so the model forbids a transition the business performs routinely,
    and it cannot be undone once production data exists.
    """
    for t in _tables(model):
        parent = t.get("generalization")
        if not parent:
            continue
        words = set(_words(t["name"]))
        hits = words & _ROLE_WORDS
        if not hits:
            continue
        yield {"object": _fq(t),
               "evidence": f"'{t['name']}' specialises '{parent}' and reads as a role or "
                           f"lifecycle stage ({', '.join(sorted(hits))}) rather than a "
                           f"permanent kind of thing. Confirm with the business whether "
                           f"an object of this type can ever stop being one — if it can, "
                           f"the type cannot follow it"}


def MDX_019(model):
    for t in _tables(model, persistable_only=True):
        if not t.get("generalization"):
            continue
        rules_ = t.get("access_rules")
        if rules_ is None:
            continue  # the extract did not carry access rules; unexamined, not failed
        if rules_:
            continue
        yield {"object": _fq(t),
               "evidence": f"specialises '{t['generalization']}' and declares no access "
                           f"rules; Mendix does not inherit them from a generalization"}


def MDX_017(model):
    for t in _tables(model, persistable_only=True):
        v = _mendix_validations(t)
        for c in _cols(t):
            if c.get("nullable") is not False:
                continue
            if "required" in v.get(c["name"].lower(), set()):
                continue
            yield {"object": _fq(t, c),
                   "evidence": "marked mandatory in the model but no Required "
                               "validation rule exists, and Mendix has no NOT NULL"}


# --------------------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------------------

CHECKS = {name.replace("_", "-", 1): fn for name, fn in list(globals().items())
          if re.fullmatch(r"[A-Z]{3}_\d{3}", name)}
