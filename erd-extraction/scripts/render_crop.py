"""Render a region of the ERD PDF to PNG (pdfium = Chrome's engine, coordinate-correct).

Usage:
  python render_crop.py <pdf> <out.png> --tables T1,T2 [--pad 60] [--maxpx 2200]
  python render_crop.py <pdf> <out.png> --box x0,y0,x1,y1 [--maxpx 2200]

--tables mode needs tables.json + paths.json next to this script (or --data DIR):
it crops the union of the named tables' box rects.
NOTE: occluded tables (painted under other boxes) will NOT be visible in the render
even though their text exists — check tables.json for their parsed content instead.
"""
import argparse, json, os, sys
import pypdfium2 as pdfium

ap = argparse.ArgumentParser()
ap.add_argument("pdf"); ap.add_argument("out")
ap.add_argument("--tables", default=None)
ap.add_argument("--box", default=None)
ap.add_argument("--pad", type=float, default=60.0)
ap.add_argument("--maxpx", type=int, default=2200)
ap.add_argument("--data", default=os.path.dirname(os.path.abspath(__file__)))
ap.add_argument("--schema", default="", help="default schema prefix for bare table names, e.g. SCHEMA")
a = ap.parse_args()

pdf = pdfium.PdfDocument(a.pdf)
page = pdf[0]
W, H = page.get_size()

if a.tables:
    tabs = json.load(open(os.path.join(a.data, "tables.json"), encoding="utf-8"))
    paths = json.load(open(os.path.join(a.data, "paths.json"), encoding="utf-8"))
    want = [t.strip().upper() for t in a.tables.split(",")]
    xs, ys = [], []
    for w in want:
        key = w if "." in w or not a.schema else f"{a.schema}.{w}"
        t = tabs.get(key)
        if not t:
            print(f"WARNING: {key} not in tables.json", file=sys.stderr); continue
        hx, hy = t["hx0"], t["hy"]
        best = None
        for r in paths["rects"]:
            if r["x0"] - 2 <= hx + 5 <= r["x1"] + 2 and r["y0"] - 2 <= hy <= r["y1"] + 2 and r["y1"] - r["y0"] >= 6:
                area = (r["x1"] - r["x0"]) * (r["y1"] - r["y0"])
                if best is None or area < best[0]: best = (area, r)
        if best:
            r = best[1]
            xs += [r["x0"], r["x1"]]; ys += [r["y0"], r["y1"]]
        else:
            xs += [hx, hx + 200]; ys += [hy - 100, hy + 10]
    if not xs:
        sys.exit("no tables found")
    x0, x1 = min(xs) - a.pad, max(xs) + a.pad
    y0, y1 = min(ys) - a.pad, max(ys) + a.pad
else:
    x0, y0, x1, y1 = [float(v) for v in a.box.split(",")]

x0 = max(0, x0); y0 = max(0, y0); x1 = min(W, x1); y1 = min(H, y1)
scale = min(a.maxpx / (x1 - x0), a.maxpx / (y1 - y0), 6.0)
img = page.render(scale=scale, crop=(x0, y0, W - x1, H - y1)).to_pil()
img.save(a.out)
print(f"saved {a.out}  region=({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f})  {img.size[0]}x{img.size[1]}px scale={scale:.2f}")
