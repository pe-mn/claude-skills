"""Group content-ordered text runs into ERD table boxes (Oracle Data Modeler style).

Box anatomy in the text layer:
  header run  "SCHEMA.TABLE"
  column rows "P * COL_NAME" + separate "TYPE (len)" run at same y
              markers: P = primary key, F = foreign key, U = unique, * = NOT NULL
  keys rows   "PK_NAME (COLS)" / "FK_NAME (COLS)" / "REF<PARENT><n> (COLS)" constraint entries
Occluded (hidden-under-other-boxes) tables parse fine — their text is present.

Cleans bare-type artifacts (a wrapped row whose type landed on its own line).

Usage: python parse_boxes.py <runs.json> <tables.json>
"""
import json, re, sys
from collections import defaultdict

runs = json.load(open(sys.argv[1], encoding="utf-8"))
HDR = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\.([A-Za-z][A-Za-z0-9_]*)$")
TYPE = re.compile(r"^(NUMBER|VARCHAR2|NVARCHAR2|CHAR|NCHAR|DATE|TIMESTAMP|CLOB|NCLOB|BLOB|LONG|FLOAT|RAW|INTEGER|SDO_GEOMETRY|XMLTYPE|ROWID|BINARY_DOUBLE|BINARY_FLOAT)\b", re.I)
TYPE_KW = {"NUMBER", "VARCHAR2", "NVARCHAR2", "CHAR", "NCHAR", "DATE", "TIMESTAMP",
           "CLOB", "NCLOB", "BLOB", "LONG", "FLOAT", "RAW", "INTEGER"}

tables = []
cur = None
for r in runs:
    txt = r["text"].strip()
    m = HDR.match(txt)
    if m and not TYPE.match(txt):
        if cur: tables.append(cur)
        cur = {"schema": m.group(1), "table": m.group(2), "hx0": r["x0"], "hx1": r["x1"],
               "hy": r["yc"], "rows": []}
        continue
    if cur is None:
        continue
    if r["yc"] > cur["hy"] + 2 or r["x0"] < cur["hx0"] - 120 or r["x0"] > cur["hx1"] + 400:
        tables.append(cur); cur = None
        continue
    cur["rows"].append(r)
if cur: tables.append(cur)

parsed = {}
for t in tables:
    byy = defaultdict(list)
    for r in t["rows"]:
        byy[round(r["yc"] / 4.0)].append(r)
    cols, keys = [], []
    for ykey in sorted(byy, reverse=True):
        parts = sorted(byy[ykey], key=lambda z: z["x0"])
        line = " ".join(p["text"].strip() for p in parts).strip()
        if not line: continue
        if re.match(r"^[A-Z0-9_]+\s*\(.*\)?$", line) and not TYPE.search(line.split("(")[0]):
            keys.append(line); continue
        pk = fk = nn = False
        rest = line
        mm = re.match(r"^(P?F?U?)\s*(\*)?\s+(.*)$", line)
        if mm and (mm.group(1) or mm.group(2)):
            pk = "P" in mm.group(1); fk = "F" in mm.group(1); nn = mm.group(2) == "*"
            rest = mm.group(3)
        tokens = rest.split()
        if not tokens: continue
        name = tokens[0].strip()
        typ = " ".join(tokens[1:]).strip()
        if not re.match(r"^[A-Za-z][A-Za-z0-9_$#]*$", name):
            keys.append(line); continue
        if name.upper() in TYPE_KW:  # wrapped-type artifact
            if cols and not cols[-1]["type"]:
                cols[-1]["type"] = (name + " " + typ).strip()
            continue
        cols.append({"name": name, "type": typ, "pk": pk, "fk": fk, "notnull": nn or pk})
    parsed[t["schema"] + "." + t["table"]] = {"hy": t["hy"], "hx0": t["hx0"], "hx1": t["hx1"],
                                              "cols": cols, "keys": keys}

json.dump(parsed, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
ncols = sum(len(p["cols"]) for p in parsed.values())
empty = [k for k, p in parsed.items() if not p["cols"]]
print(f"boxes: {len(tables)} distinct: {len(parsed)} columns: {ncols} empty-boxes: {len(empty)}")
if empty[:10]: print("  empty (check manually):", empty[:10])
