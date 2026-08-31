"""Extract vector path objects (relationship lines, box rects) from the ERD PDF."""
import pypdfium2 as pdfium
import pypdfium2.raw as raw
import ctypes, json, sys

PDF = sys.argv[1]
pdf = pdfium.PdfDocument(PDF)
page = pdf[0]
n = raw.FPDFPage_CountObjects(page)
print("page objects:", n)

paths = []
type_count = {}
for i in range(n):
    obj = raw.FPDFPage_GetObject(page, i)
    typ = raw.FPDFPageObj_GetType(obj)
    type_count[typ] = type_count.get(typ, 0) + 1
    if typ != raw.FPDF_PAGEOBJ_PATH:
        continue
    ns = raw.FPDFPath_CountSegments(obj)
    pts = []
    closed = False
    for j in range(ns):
        seg = raw.FPDFPath_GetPathSegment(obj, j)
        x = ctypes.c_float(); y = ctypes.c_float()
        raw.FPDFPathSegment_GetPoint(seg, ctypes.byref(x), ctypes.byref(y))
        st = raw.FPDFPathSegment_GetType(seg)
        if raw.FPDFPathSegment_GetClose(seg):
            closed = True
        pts.append((round(x.value, 1), round(y.value, 1), st))
    if pts:
        paths.append({"pts": pts, "closed": closed})

print("path objects:", len(paths), "| type histogram:", type_count)
# classify: closed 4-5pt rects vs open polylines
rects, lines, other = [], [], []
for p in paths:
    xs = [q[0] for q in p["pts"]]; ys = [q[1] for q in p["pts"]]
    w = max(xs) - min(xs); h = max(ys) - min(ys)
    if p["closed"] and len(p["pts"]) <= 6:
        rects.append({"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)})
    elif not p["closed"]:
        lines.append(p)
    else:
        other.append(p)
print(f"closed rects: {len(rects)}, open polylines: {len(lines)}, other closed: {len(other)}")
# polyline stats
import statistics
if lines:
    lens = [len(p["pts"]) for p in lines]
    print("polyline pts min/med/max:", min(lens), statistics.median(lens), max(lens))
    # sample a few long ones
    for p in lines[:5]:
        print("  sample line:", p["pts"][:6])
json.dump({"rects": rects, "lines": lines, "other": other}, open(sys.argv[2], "w"), indent=None)
