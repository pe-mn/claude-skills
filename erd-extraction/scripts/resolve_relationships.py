"""Resolve ERD relationships: FK keys-section entries + connector lines + floating labels.

Usage: python resolve_relationships.py <tables.json> <paths.json> <runs.json> <relationships.json> <tables_clean.json>

Fixes over v2:
- cleans bare-type parse artifacts from tables.json (DATE/VARCHAR2 rows) -> tables_clean.json
- child's own name is stripped from the FK-constraint name before parent scoring
- token/abbreviation word matching replaces raw substring scoring
- line-only pairs kept only with resolved direction; rest go to a review list
"""
import json, re, sys, math
from collections import defaultdict, Counter

tables = json.load(open(sys.argv[1], encoding="utf-8"))
paths = json.load(open(sys.argv[2], encoding="utf-8"))
runs = json.load(open(sys.argv[3], encoding="utf-8"))

TYPE_KW = {"NUMBER", "VARCHAR2", "NVARCHAR2", "CHAR", "NCHAR", "DATE", "TIMESTAMP",
           "CLOB", "NCLOB", "BLOB", "LONG", "FLOAT", "RAW", "INTEGER"}

# ---------- clean columns ----------
for nm, t in tables.items():
    clean = []
    for c in t["cols"]:
        if c["name"].upper() in TYPE_KW:
            if clean and not clean[-1]["type"]:
                clean[-1]["type"] = (c["name"] + " " + c["type"]).strip()
            continue
        clean.append(c)
    t["cols"] = clean
json.dump(tables, open(sys.argv[5], "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------- box rects ----------
rects = paths["rects"]
boxes = {}
for name, t in tables.items():
    hx = t["hx0"] + 5; hy = t["hy"]
    best = None
    for r in rects:
        if r["x0"] - 2 <= hx <= r["x1"] + 2 and r["y0"] - 2 <= hy <= r["y1"] + 2:
            if r["y1"] - r["y0"] < 6: continue
            area = (r["x1"] - r["x0"]) * (r["y1"] - r["y0"])
            if best is None or area < best[0]: best = (area, r)
    if best: boxes[name] = best[1]

# ---------- connector chains ----------
segs = []
for p in paths["lines"]:
    pts = [(q[0], q[1]) for q in p["pts"]]
    xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
    if math.hypot(max(xs) - min(xs), max(ys) - min(ys)) < 12:
        continue
    segs.append(pts)

def key(pt): return (round(pt[0] / 2), round(pt[1] / 2))
uf = list(range(len(segs)))
def find(i):
    while uf[i] != i:
        uf[i] = uf[uf[i]]; i = uf[i]
    return i
def union(i, j):
    ri, rj = find(i), find(j)
    if ri != rj: uf[ri] = rj
end_index = defaultdict(list)
for i, s in enumerate(segs):
    end_index[key(s[0])].append(i); end_index[key(s[-1])].append(i)
for pt, lst in end_index.items():
    for a in lst[1:]: union(lst[0], a)
chains = defaultdict(list)
for i in range(len(segs)): chains[find(i)].append(i)

def chain_endpoints(idx_list):
    cnt = defaultdict(int); ptmap = {}
    for i in idx_list:
        for pt in (segs[i][0], segs[i][-1]):
            cnt[key(pt)] += 1; ptmap[key(pt)] = pt
    return [ptmap[k] for k, v in cnt.items() if v == 1]

def border_dist(px, py, r):
    dx = max(r["x0"] - px, 0, px - r["x1"]); dy = max(r["y0"] - py, 0, py - r["y1"])
    out = math.hypot(dx, dy)
    if out > 0: return out
    return min(px - r["x0"], r["x1"] - px, py - r["y0"], r["y1"] - py)

names = list(boxes)
def endpoint_box(px, py, tol=8.0):
    best = None
    for nm in names:
        d = border_dist(px, py, boxes[nm])
        if d <= tol and (best is None or d < best[0]): best = (d, nm)
    return best[1] if best else None

conn_pairs = defaultdict(int)
chain_geo = {}
for cid, idx_list in chains.items():
    ends = chain_endpoints(idx_list)
    hit = sorted({h for h in (endpoint_box(e[0], e[1]) for e in ends) if h})
    if len(hit) == 2:
        conn_pairs[frozenset(hit)] += 1
        chain_geo[cid] = (hit[0], hit[1])
    elif len(hit) == 1 and len([e for e in ends if endpoint_box(e[0], e[1], 6.0) == hit[0]]) >= 2:
        conn_pairs[frozenset((hit[0],))] += 1
        chain_geo[cid] = (hit[0], hit[0])
    # >2 boxes: junction artifact of crossing lines -> DROP (was all-pairs spray in v2)
print("chains:", len(chains), "resolved pairs:", len(chain_geo), "distinct pairs:", len(conn_pairs))

# ---------- floating labels ----------
def inside_any_box(x, y):
    for nm in names:
        r = boxes[nm]
        if r["x0"] - 1 <= x <= r["x1"] + 1 and r["y0"] - 1 <= y <= r["y1"] + 1: return True
    return False
LBL = re.compile(r"^[A-Z][A-Z0-9_]{3,}$")
labels = [(r["text"].strip(), (r["x0"] + r["x1"]) / 2, (r["y0"] + r["y1"]) / 2)
          for r in runs if LBL.match(r["text"].strip())
          and not inside_any_box((r["x0"] + r["x1"]) / 2, (r["y0"] + r["y1"]) / 2)]

def pt_seg_dist(px, py, a, b):
    ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0: return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

label_pair = {}
for t, cx, cy in labels:
    best = None
    for cid in chain_geo:
        d = min(pt_seg_dist(cx, cy, segs[i][0], segs[i][-1]) for i in chains[cid])
        if best is None or d < best[0]:
            best = (d, frozenset(chain_geo[cid]))
    if best and best[0] <= 15:
        prev = label_pair.get(t)
        if prev is None or best[0] < prev[1]:
            label_pair[t] = (best[1], best[0])

# ---------- FK resolution ----------
short = {nm: nm.split(".")[1] for nm in tables}
pk_cols = {nm: [c["name"] for c in t["cols"] if c["pk"]] for nm, t in tables.items()}
col_names = {nm: {c["name"] for c in t["cols"]} for nm, t in tables.items()}
ENTRY = re.compile(r"^([A-Z0-9_]+)\s*\(([^)]*)\)?\s*$")

NOISE = {"FK", "REF", "ID", "PK", "THE", ""}
def tokens_of(s):
    return [t for t in re.split(r"[_0-9]+", s) if t not in NOISE]

def word_score(fkname, child_short, parent_short):
    """score parent word presence in fkname, ignoring the child's own words"""
    ftoks = tokens_of(fkname)
    ctoks = tokens_of(child_short)
    ptoks = tokens_of(parent_short)
    if not ptoks: return 0
    # remove ONE occurrence of the child's token sequence (child name embedded in constraint)
    for i in range(len(ftoks) - len(ctoks) + 1):
        if ftoks[i:i + len(ctoks)] == ctoks:
            ftoks = ftoks[:i] + ftoks[i + len(ctoks):]
            break
    # exact contiguous parent sequence
    for i in range(len(ftoks) - len(ptoks) + 1):
        if ftoks[i:i + len(ptoks)] == ptoks:
            return 6
    # per-word prefix-abbreviation coverage
    cov = 0.0
    for w in ptoks:
        hit = 0.0
        for ft in ftoks:
            if w == ft: hit = 1.0; break
            if len(ft) >= 3 and w.startswith(ft): hit = max(hit, len(ft) / len(w))
        cov += hit
    cov /= len(ptoks)
    if cov >= 0.99: return 5
    if cov >= 0.75: return 3
    if cov >= 0.5: return 1
    return 0

def resolve(child, fkname, fkcols, connected):
    lbl = label_pair.get(fkname)
    lbl_parent = None
    if lbl and child in lbl[0]:
        other = [x for x in lbl[0] if x != child]
        lbl_parent = other[0] if other else child
    m = re.match(r"^REF([A-Z0-9_]+?)(\d+)?$", fkname)
    scored = []
    for parent in names:
        ps = short[parent]; score = 0
        if lbl_parent == parent: score += 8
        if m and m.group(1) and (m.group(1) == ps or m.group(1).rstrip("_") == ps): score += 8
        score += word_score(fkname, short[child], ps)
        for col in fkcols:
            if col in pk_cols.get(parent, []): score += 5
            elif pk_cols.get(parent) and col.endswith("_ID") and col[:-3] == ps: score += 4
        if parent in connected and parent != child: score += 3
        if "USER" in ps and fkcols and all(c in ("CREATED_BY", "UPDATED_BY") for c in fkcols): score += 5
        if score > 0: scored.append((score, parent))
    scored.sort(key=lambda z: (-z[0], z[1]))
    if not scored: return None, 0, 0, []
    margin = scored[0][0] - (scored[1][0] if len(scored) > 1 else 0)
    return scored[0][1], scored[0][0], margin, scored[:4]

conn_by_table = defaultdict(set)
for pair in conn_pairs:
    tp = tuple(pair)
    if len(tp) == 2:
        conn_by_table[tp[0]].add(tp[1]); conn_by_table[tp[1]].add(tp[0])
    else:
        conn_by_table[tp[0]].add(tp[0])

rels, fk_pairs = [], set()
for child, t in tables.items():
    seen = set()
    for k in t["keys"]:
        mm = ENTRY.match(k.strip())
        if not mm: continue
        cname, ccols = mm.group(1), [c.strip() for c in mm.group(2).split(",") if c.strip()]
        if cname.startswith("PK") or cname in seen: continue
        if not (cname.startswith(("FK", "REF")) or "_FK" in cname): continue
        seen.add(cname)
        parent, score, margin, top = resolve(child, cname, ccols, conn_by_table.get(child, set()))
        conf = "high" if (score >= 10 and margin >= 4) else ("medium" if score >= 7 else "low")
        rels.append({"child": child, "fk_constraint": cname, "fk_columns": ccols, "parent": parent,
                     "confidence": conf, "score": score, "margin": margin,
                     "line_evidence": bool(parent) and (parent in conn_by_table.get(child, set())),
                     "label_evidence": cname in label_pair,
                     "alternatives": [f"{short[p]}({s})" for s, p in top[1:]]})
        if parent: fk_pairs.add(frozenset((child, parent)))

synth, review = [], []
for pair, cnt in conn_pairs.items():
    tp = tuple(pair)
    if pair in fk_pairs or len(tp) != 2: continue
    a, b = tp
    cand = {(c_, p_, col) for c_, p_ in ((a, b), (b, a)) for col in pk_cols.get(p_, [])
            if col in col_names[c_] and col not in pk_cols.get(c_, [])}
    dirs = {(c_, p_) for c_, p_, _ in cand}
    if len(dirs) == 1:
        c_, p_ = next(iter(dirs))
        cols = sorted({col for cc, pp, col in cand if (cc, pp) == (c_, p_)})
        synth.append({"child": c_, "fk_constraint": "(line only)", "fk_columns": cols, "parent": p_,
                      "confidence": "medium", "score": 6, "margin": 0, "line_evidence": True,
                      "label_evidence": False, "alternatives": []})
    else:
        review.append({"tableA": a, "tableB": b, "count": cnt,
                       "note": "line evidence only, direction unresolved"})

print("FK rels:", len(rels), "| synth:", len(synth), "| review pairs:", len(review))
print("confidence:", Counter(r["confidence"] for r in rels + synth))
json.dump({"relationships": rels + synth, "review_pairs": review},
          open(sys.argv[4], "w", encoding="utf-8"), indent=1)
