"""Extract text runs from an ERD PDF in CONTENT ORDER using pdfium (Chrome's engine).

Why pdfium: many diagram-tool PDF exports (e.g. Oracle Data Modeler) have text
coordinates that pypdf/most viewers corrupt; pdfium (pypdfium2) resolves them
correctly — same engine as Chrome, which renders these files fine.

Why content order (no global y-sort): each table box is drawn as one unit, so
its header + rows stay contiguous in the content stream. A global sort merges
unrelated boxes that share a baseline. Runs break on baseline change or x-gap.

Usage: python extract_runs_ordered.py <erd.pdf> <runs.json> [page_index]
"""
import json, sys
import pypdfium2 as pdfium

PDF, OUT = sys.argv[1], sys.argv[2]
PAGE = int(sys.argv[3]) if len(sys.argv) > 3 else 0

pdf = pdfium.PdfDocument(PDF)
page = pdf[PAGE]
tp = page.get_textpage()
n = tp.count_chars()
all_text = tp.get_text_range(0, n)

runs = []
cur = None
for i in range(n):
    ch = all_text[i] if i < len(all_text) else ""
    if ch in ("\r", "\n"):
        cur = None
        continue
    l, b, r, t = tp.get_charbox(i, loose=False)
    yc = (b + t) / 2
    if cur is not None and (abs(yc - cur["yc"]) > 3.0 or l - cur["x1"] > 15.0 or l < cur["x1"] - 30):
        cur = None
    if cur is None:
        cur = {"text": ch, "x0": l, "x1": r, "y0": b, "y1": t, "yc": yc}
        runs.append(cur)
    else:
        cur["text"] += ch
        cur["x1"] = max(cur["x1"], r); cur["x0"] = min(cur["x0"], l)
        cur["y0"] = min(cur["y0"], b); cur["y1"] = max(cur["y1"], t)
        cur["yc"] = (cur["y0"] + cur["y1"]) / 2

runs = [r_ for r_ in runs if r_["text"].strip()]
w, h = page.get_size()
print(f"page {PAGE}: {w:.0f}x{h:.0f}pt, {n} chars -> {len(runs)} runs")
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(runs, f, ensure_ascii=False)
