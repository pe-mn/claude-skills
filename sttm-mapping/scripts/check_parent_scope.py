#!/usr/bin/env python
"""Check that every generalisation parent's extraction scope subsumes its children's.

    python check_parent_scope.py mapping.xlsx [--sheet NAME] [--json out.json]

THE RULE

    scope(parent)  =   COMPLETE: no subtype discriminator AT ALL (row hygiene only)
    scope(child)   =   its own discriminator only

Class-table inheritance means a child row cannot exist without its parent row, so the
parent's row scope is BY DEFINITION the union of whatever its specialisations load. Any
pinned discriminator list on the parent is therefore at best redundant and at worst a
drift bomb: too narrow orphans some children; a token no child uses orphans all of them,
silently — the extract simply returns nothing.

Containment (parent >= union of children) is only the MINIMUM invariant this script can
prove. The house rule is stricter, and it was reached the hard way — a "widen the pin to
the union" fix was applied first and had to be redone, because a wider pin is still a
pin: the moment a new subtype arrives or a BA resolves an open type, the parent list is
stale again. So ANY parent pin is reported, superset or not.

WHY A SCRIPT AND NOT A CHECKLIST ITEM

The predicate is set containment over discriminator values, which is decidable. It was a
checklist item on a real project and passed review anyway: a shared parent entity had been
seeded from another module and pinned a token none of its own children used, so its scope
was DISJOINT from theirs. Nobody spots that by reading; a set comparison spots it
immediately.

EXTRACTION FILTERS ARE PROSE

Real filter cells mix SQL with commentary, often in more than one script:

    REQUEST.REQUEST_TYPE_ID IN (48 General Collection / <non-Latin label>, 58 Case Closure / ...)
      AND REQUEST.IS_DELETED = 0

Anything scanning a character class stops at the first letter and loses 58 — which then
reads as PARENT_TOO_NARROW, a false alarm indistinguishable from a real one. So the
parenthetical is taken whole, and the extractor SELF-TESTS on known shapes before any
workbook is opened. If it cannot parse its own examples it refuses to report.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict

#: Header aliases. Extend rather than renaming a workbook to suit the script.
ALIASES = {
    "entity": ["newmodeltable", "entity", "target_table", "target entity", "table",
               "entity_name"],
    "attribute": ["newmodelcolumn", "attribute", "target_column", "column",
                  "attribute_name", "field"],
    "parent": ["parent table", "parent_table", "generalisation", "generalization",
               "parent entity", "specializes"],
    "filter": ["extraction filter", "extraction_condition", "filter",
               "extraction condition", "filter / extraction condition", "scope"],
    "module": ["module", "target_module", "namespace"],
    "id": ["mapping_id", "mapping id", "id"],
}

#: Discriminators — and ONLY discriminators. A discriminator answers "which source rows
#: ARE this entity". Add patterns per project; an unrecognised one is reported as unparsed,
#: never as "no filter".
#:
#: Two exclusions worth stating, because including them produced pure noise on a real
#: workbook:
#:
#:   * a bare `TYPE_ID` matches as a SUBSTRING of REQUEST_TYPE_ID and DOMAIN_TYPE_ID, so
#:     `DOMAIN_TYPE_ID = 9` registered as `TYPE_ID = 9` and the parent looked too narrow
#:     against a value that was never a request type. Hence the boundary guard below AND
#:     no generic entries here.
#:   * `STATUS_ID` and `DOMAIN_TYPE_ID` are not identity. A status filter says which rows
#:     are terminal; a domain-type says which CODE LIST to decode against. Both
#:     legitimately vary per attribute — "ProcessedDate only at a terminal status" is a
#:     correct per-attribute scope, not a scope violation — so comparing them across a
#:     hierarchy compares things that were never meant to match.
NUMERIC_DISC = [
    "REQUEST_TYPE_ID", "NOTE_TYPE_ID", "DOCUMENT_TYPE_ID", "ASSET_TYPE_ID",
    "APPLICATION_SOURCE",
]
TOKEN_DISC = ["EXTERNAL_ID", "NOTEOWNER", "OWNER_TYPE", "ENTITY_TYPE", "OBJECT_TYPE"]
#: Names that must NOT be matched as a discriminator even if a project adds them, because
#: they are lifecycle or decode selectors. Kept explicit so a future edit has to argue
#: with this note rather than silently reintroduce the noise.
NOT_DISCRIMINATORS = frozenset({"STATUS_ID", "DOMAIN_TYPE_ID", "TYPE_ID", "RECORD_STATUS",
                                "IS_DELETED", "CATEGORY_ID"})

INT_RE = re.compile(r"\d{1,6}")
QUOTED_RE = re.compile(r"'([^']*)'")


def norm(v):
    return "" if v is None else re.sub(r"\s+", " ", str(v).strip())


def _balanced(s):
    """Contents of the leading (...) group, or None. Handles nesting."""
    s = s.lstrip()
    if not s.startswith("("):
        return None
    depth, buf = 0, []
    for ch in s:
        if ch == "(":
            depth += 1
            if depth == 1:
                continue
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return "".join(buf)
        buf.append(ch)
    return "".join(buf)


def discriminators(texts):
    """{discriminator_name: set(values)} plus open asks and unparsed count."""
    out = defaultdict(set)
    meta = {"open_asks": set(), "unparsed": 0}
    for t in texts:
        if not t:
            continue
        hit = False
        for name in NUMERIC_DISC:
            for m in re.finditer(rf"(?<![A-Za-z_]){name}\s*(=|IN)\s*", t, re.I):
                hit = True
                rest = t[m.end():]
                if m.group(1).upper() == "IN":
                    seg = _balanced(rest)
                    if seg is not None:
                        found = INT_RE.findall(seg)
                        if found:
                            out[name].update(found)
                        else:
                            meta["open_asks"].add(f"{name} IN (...) names no value")
                        continue
                m2 = INT_RE.match(rest.lstrip().lstrip("<").lstrip())
                if m2:
                    out[name].add(m2.group(0))
                else:
                    meta["open_asks"].add(f"{name} value unresolved")
        for name in TOKEN_DISC:
            for m in re.finditer(rf"(?<![A-Za-z_]){name}\s*(?:=|IN)\s*\(?\s*((?:'[^']*'[\s|,]*)+)",
                                 t, re.I):
                toks = [x for x in QUOTED_RE.findall(m.group(1)) if x.strip()]
                if toks:
                    out[name].update(toks)
                    hit = True
        if not hit and re.search(r"\b[A-Z_]{3,}\.[A-Z_]{3,}\b", t):
            meta["unparsed"] += 1
    return dict(out), meta


def _selftest():
    cases = [
        ("REQUEST.REQUEST_TYPE_ID = 40 (Open service file) AND X",
         "REQUEST_TYPE_ID", {"40"}),
        ("REQUEST.REQUEST_TYPE_ID IN (48 General Collection / ###, "
         "58 Case Closure / ###) AND X", "REQUEST_TYPE_ID", {"48", "58"}),
        ("DOCUMENT.EXTERNAL_ID = 'SERVICE_FILE' AND X",
         "EXTERNAL_ID", {"SERVICE_FILE"}),
        ("DOCUMENT.EXTERNAL_ID IN ('request', 'receipts')",
         "EXTERNAL_ID", {"request", "receipts"}),
        ("NOTE.NOTE_TYPE_ID = 21002 (User)", "NOTE_TYPE_ID", {"21002"}),
        # boundary guard: DOMAIN_TYPE_ID must NOT register as any discriminator, and a
        # status filter must not register as identity
        ("DOMAIN_DATA.DOMAIN_TYPE_ID = 9 (REQUEST_STATUS) AND REQUEST.STATUS_ID IN "
         "(9005, 9003)", "REQUEST_TYPE_ID", set()),
    ]
    bad = []
    for text, key, want in cases:
        got, _ = discriminators([text])
        if got.get(key, set()) != want:
            bad.append(f"  {key}: wanted {sorted(want)}, got "
                       f"{sorted(got.get(key, set()))}\n    input: {text[:70]}")
    _, meta = discriminators(["REQUEST.REQUEST_TYPE_ID = <BA to supply> AND X"])
    if not meta["open_asks"]:
        bad.append("  an unresolved <...> value did not register as an open ask")
    if bad:
        print("EXTRACTOR SELF-TEST FAILED - refusing to report findings:")
        print("\n".join(bad))
        sys.exit(2)


def resolve_headers(header_row):
    got = {}
    seen = {re.sub(r"[^a-z0-9 /_]", "", norm(h).lower()): i
            for i, h in enumerate(header_row) if norm(h)}
    for canon, cands in ALIASES.items():
        for c in cands:
            if c in seen:
                got[canon] = seen[c]
                break
    return got


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workbook")
    ap.add_argument("--sheet", default=None)
    ap.add_argument("--json", dest="json_out", default=None)
    a = ap.parse_args(argv)

    _selftest()

    try:
        from openpyxl import load_workbook
    except ImportError:
        raise SystemExit("openpyxl is required")

    wb = load_workbook(a.workbook, read_only=True, data_only=True)
    ws = wb[a.sheet] if a.sheet else wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        raise SystemExit("empty sheet")

    hdr_i, H, best = 0, {}, -1
    for i, r in enumerate(rows[:20]):
        got = resolve_headers(r)
        if len(got) > best:
            hdr_i, H, best = i, got, len(got)
    for need in ("entity", "attribute", "parent", "filter"):
        if need not in H:
            raise SystemExit(
                f"could not find a '{need}' column. Looked for: "
                f"{', '.join(ALIASES[need])}\nFound: "
                f"{', '.join(str(x) for x in rows[hdr_i] if x)}")

    def cell(r, k):
        return norm(r[H[k]]) if k in H and H[k] < len(r) else ""

    ent_filters, child_parent = defaultdict(list), defaultdict(set)
    for r in rows[hdr_i + 1:]:
        ent = cell(r, "entity")
        if not ent:
            continue
        mod = cell(r, "module")
        key = f"{mod}.{ent}" if mod else ent
        f = cell(r, "filter")
        if f and not f.startswith("="):
            ent_filters[key].append(f)
        p = cell(r, "parent")
        if p and p != ent and not p.startswith("="):
            child_parent[key].add(p)

    def resolve(q):
        if q in ent_filters or q in child_parent:
            return q
        tail = q.split(".")[-1]
        for k in list(ent_filters) + list(child_parent):
            if k.split(".")[-1].lower() == tail.lower():
                return k
        return None

    findings, ok = [], []
    for pq in sorted({p for ps in child_parent.values() for p in ps}):
        pk = resolve(pq)
        pdisc, pmeta = discriminators(ent_filters.get(pk, []) if pk else [])
        kids = sorted([c for c, ps in child_parent.items() if pq in ps])
        union, kid_detail, asks = defaultdict(set), [], []
        for c in kids:
            cd, cm = discriminators(ent_filters.get(c, []))
            for k, v in cd.items():
                union[k] |= v
            if cm["open_asks"]:
                asks.append({"child": c, "asks": sorted(cm["open_asks"])})
            kid_detail.append({"child": c,
                               "disc": {k: sorted(v) for k, v in cd.items()},
                               "silent": not cd})
        for name in sorted(set(pdisc) | set(union)):
            p_, u_ = pdisc.get(name, set()), union.get(name, set())
            rec = {"parent": pq, "discriminator": name,
                   "parent_values": sorted(p_), "children_union": sorted(u_),
                   "children": kids}
            if not p_ and not u_:
                continue
            if not p_:
                rec["verdict"] = "OK_parent_unpinned"
                ok.append(rec)
            elif not u_:
                rec["verdict"] = "PARENT_PINNED_CHILDREN_SILENT"
                rec["note"] = ("children carry no discriminator of their own; under this "
                               "rule the discriminator belongs on the child and the union "
                               "on the parent")
                findings.append(rec)
            elif u_ <= p_:
                # containment holds, but the parent is still pinned — house rule says a
                # generalisation parent carries NO discriminator, because any list on the
                # parent goes stale the moment a subtype is added or an open type is
                # resolved. Move the values to the children (where they already are, if
                # u_ is non-empty) and strip the parent's.
                rec["verdict"] = "PARENT_PINNED_SUPERSET"
                rec["note"] = ("containment holds today, but a pinned parent list drifts; "
                               "the parent should carry row hygiene only")
                findings.append(rec)
            elif not (u_ & p_):
                rec["verdict"] = "PARENT_DISJOINT"
                rec["missing_from_parent"] = sorted(u_ - p_)
                rec["note"] = ("the parent selects values NO child uses - the extract "
                               "returns nothing for this hierarchy and every child is "
                               "orphaned")
                findings.append(rec)
            else:
                rec["verdict"] = "PARENT_TOO_NARROW"
                rec["missing_from_parent"] = sorted(u_ - p_)
                findings.append(rec)
        if asks:
            findings.append({"parent": pq, "verdict": "CHILD_DISCRIMINATOR_OPEN",
                             "children": kids, "open_asks": asks,
                             "note": ("a child's discriminator is unresolved, so "
                                      "containment cannot be decided for it - treat any "
                                      "OK verdict on this hierarchy as provisional")})

    print(f"hierarchies checked: {len({f['parent'] for f in findings} | {o['parent'] for o in ok})}")
    print(f"passing checks     : {len(ok)}")
    print(f"findings           : {len(findings)}\n")
    order = {"PARENT_DISJOINT": 0, "PARENT_TOO_NARROW": 1,
             "PARENT_PINNED_CHILDREN_SILENT": 2, "PARENT_PINNED_SUPERSET": 3,
             "CHILD_DISCRIMINATOR_OPEN": 4}
    for f in sorted(findings, key=lambda x: order.get(x["verdict"], 9)):
        print(f"[{f['verdict']}] {f['parent']}"
              + (f" / {f['discriminator']}" if f.get("discriminator") else ""))
        if f.get("parent_values") is not None and "discriminator" in f:
            print(f"    parent   : {f['parent_values']}")
            print(f"    children : {f['children_union']}")
        if f.get("missing_from_parent"):
            print(f"    MISSING FROM PARENT: {f['missing_from_parent']}")
        if f.get("open_asks"):
            for x in f["open_asks"]:
                print(f"    open on {x['child']}: {x['asks'][0]}")
        if f.get("note"):
            print(f"    {f['note']}")
        print()
    if a.json_out:
        with open(a.json_out, "w", encoding="utf-8") as fh:
            json.dump({"findings": findings, "passing": ok}, fh, indent=2,
                      ensure_ascii=False)
        print(f"written: {a.json_out}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
