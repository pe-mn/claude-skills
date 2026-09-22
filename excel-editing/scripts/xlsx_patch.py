#!/usr/bin/env python
"""Edit an .xlsx/.xlsm by patching the OOXML zip — no Excel, nothing dropped.

An Office file is a zip of XML parts. Rewriting the two or three parts you meant
to change and copying the rest through BYTE-FOR-BYTE is the only write path that
cannot destroy a feature it does not understand: macros, in-cell checkboxes,
pivot caches and slicers survive by construction, not by good intentions.

    bk = Book("book.xlsx")
    sh = bk.sheet("STTM")
    sh.set_text("P57", "3.30")                 # a shared string: uncoercible
    sh.set_cells({"A5": "EM01-001", "A6": "EM01-002"})    # bulk, one pass
    sh.add_rule("A20:AW34,A80:AW94", dxf_font("FF808080"))  # ONE dxf, not N styles
    bk.save()                                  # backs up to ../_backups first

What it does NOT do: anything needing Excel's engine — inserting or deleting
rows/columns, sorting, autofilter, autofit, recalculation. Those rewrite every
cell reference, CF range and validation in the file; use COM (see xl_com.py).

Reads are for verification, not analysis: read data with
``openpyxl.load_workbook(path, read_only=True)``.
"""
from __future__ import annotations

import re
import shutil
import time
import zipfile
from datetime import datetime
from pathlib import Path

__all__ = ["Book", "Sheet", "dxf_font", "dxf_fill", "col_index", "col_letter",
           "split_ref"]

#: A cell element: self-closing form FIRST, else a non-greedy match to </c>.
#: (Alternation order matters — an element with children holds nested '/>'.)
_CELL_RE = re.compile(r'<c\b[^>]*/>|<c\b[^>]*>.*?</c>', re.S)
_ROW_RE = re.compile(r'<row\b[^>]*/>|<row\b[^>]*>.*?</row>', re.S)
#: Where a <conditionalFormatting> element may sit, in CT_Worksheet order. We
#: append after the last existing one; with none present, insert before the first
#: element that must follow it. Excel rejects a misplaced child outright.
_AFTER_CF = ("<dataValidations", "<hyperlinks", "<printOptions", "<pageMargins",
             "<pageSetup", "<headerFooter", "<rowBreaks", "<colBreaks", "<drawing",
             "<legacyDrawing", "<tableParts", "<extLst")


# --- refs --------------------------------------------------------------------
def col_index(letters: str) -> int:
    """'A' -> 1, 'AW' -> 49."""
    n = 0
    for ch in letters.upper():
        n = n * 26 + (ord(ch) - 64)
    return n


def col_letter(index: int) -> str:
    """1 -> 'A', 49 -> 'AW'."""
    s = ""
    while index:
        index, r = divmod(index - 1, 26)
        s = chr(65 + r) + s
    return s


def split_ref(ref: str) -> tuple[str, int]:
    """'AW34' -> ('AW', 34)."""
    m = re.fullmatch(r"\$?([A-Za-z]+)\$?(\d+)", ref)
    if not m:
        raise ValueError(f"not a cell reference: {ref!r}")
    return m.group(1).upper(), int(m.group(2))


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


_ENTITY = re.compile(r"&(?:amp|lt|gt|quot|apos|#\d+|#x[0-9A-Fa-f]+);")


def _esc_formula(f: str) -> str:
    """XML-escape a worksheet formula, leaving any entity it already has alone.

    Excel formulas are full of characters XML reserves: `<>` `<=` `>=` for
    comparison and `&` for concatenation. A raw formula written straight into
    `<formula>…</formula>` produces a file Excel reports as needing repair —
    `<formula>$D4<>$D3</formula>` parses `<>` as a tag. Measured: one such rule
    made a 648-row sheet unopenable, and the corruption is invisible until
    something parses the XML.
    """
    out, i = [], 0
    for m in _ENTITY.finditer(f):
        out.append(_esc(f[i:m.start()]))
        out.append(m.group(0))          # already an entity — pass through
        i = m.end()
    out.append(_esc(f[i:]))
    return "".join(out)


def _splice(x: str, edits: list[tuple[int, int, str]]) -> str:
    """Apply non-overlapping (start, end, replacement) edits in ONE pass.

    ``x = x[:a] + el + x[b:]`` in a loop copies the whole part per edit: 362 cells
    in a 1.5 MB sheet is half a gigabyte of copying, and it is the difference
    between 0.2s and 1.9s.
    """
    if not edits:
        return x
    out, prev = [], 0
    for a, b, el in sorted(edits):
        if a < prev:
            raise ValueError(f"overlapping edits at offset {a}")
        out.append(x[prev:a])
        out.append(el)
        prev = b
    out.append(x[prev:])
    return "".join(out)


# --- differential formats (the ONLY sane way to restyle in bulk) -------------
def dxf_font(rgb: str, *, bold: bool | None = None, italic: bool | None = None,
             strike: bool | None = None) -> str:
    """A <dxf> that changes font only. ``rgb`` is ARGB, e.g. 'FF808080'."""
    bits = ""
    if bold is not None:
        bits += "<b/>" if bold else "<b val=\"0\"/>"
    if italic is not None:
        bits += "<i/>" if italic else "<i val=\"0\"/>"
    if strike is not None:
        bits += "<strike/>" if strike else "<strike val=\"0\"/>"
    return f'<dxf><font>{bits}<color rgb="{rgb}"/></font></dxf>'


def dxf_fill(rgb: str, *, font_rgb: str | None = None) -> str:
    """A <dxf> with a solid fill.

    A dxf fill is drawn from **bgColor**, the reverse of a normal cell fill: set
    only fgColor (what every styling helper does) and the rule applies its font
    colour and NO FILL AT ALL, silently.
    """
    font = f'<font><color rgb="{font_rgb}"/></font>' if font_rgb else ""
    return (f'<dxf>{font}<fill><patternFill patternType="solid">'
            f'<fgColor rgb="{rgb}"/><bgColor rgb="{rgb}"/></patternFill></fill></dxf>')


class Sheet:
    """One worksheet part. Edits are buffered and applied in a single pass."""

    def __init__(self, book: "Book", name: str, part: str):
        self.book, self.name, self.part = book, name, part
        self._cells: dict[str, tuple[int, int]] = {}
        self._rows: dict[int, tuple[int, int]] = {}
        self._edits: dict[str, str] = {}          # ref -> replacement element
        self._inserts: dict[int, dict[int, str]] = {}   # row -> {colidx: element}
        self._indexed = False

    # --- raw part ---------------------------------------------------------
    @property
    def xml(self) -> str:
        self.flush()
        return self.book.parts_text[self.part]

    @xml.setter
    def xml(self, v: str) -> None:
        self.flush()
        self.book.parts_text[self.part] = v
        self._indexed = False

    def _raw(self) -> str:
        return self.book.parts_text[self.part]

    def _index(self) -> None:
        if self._indexed:
            return
        x = self._raw()
        self._cells, self._rows = {}, {}
        for m in _ROW_RE.finditer(x):
            r = re.match(r'<row\b[^>]*?\sr="(\d+)"', m.group(0))
            if r:
                self._rows[int(r.group(1))] = (m.start(), m.end())
        for m in _CELL_RE.finditer(x):
            r = re.match(r'<c\b[^>]*?\sr="([A-Z]+\d+)"', m.group(0))
            if r:
                self._cells[r.group(1)] = (m.start(), m.end())
        self._indexed = True

    # --- reads ------------------------------------------------------------
    def element(self, ref: str) -> str | None:
        """The <c> element for ``ref``, or None (a truly empty cell is not stored).

        Reads do NOT flush: buffered edits are answered from the buffer, and the
        span index stays valid because the raw part is untouched until flush().
        Flushing here would turn a loop of 362 writes into 362 full passes.
        """
        ref = ref.upper()
        if ref in self._edits:
            return self._edits[ref]
        row = split_ref(ref)[1]
        queued = self._inserts.get(row, {}).get(col_index(split_ref(ref)[0]))
        if queued is not None:
            return queued
        self._index()
        span = self._cells.get(ref)
        return self._raw()[span[0]:span[1]] if span else None

    def style_of(self, ref: str) -> str | None:
        el = self.element(ref)
        m = re.search(r'\ss="(\d+)"', el) if el else None
        return m.group(1) if m else None

    def has_formula(self, ref: str) -> bool:
        """True if the cell holds a FORMULA.

        `value()` cannot answer this — it returns the cached RESULT, so a guard
        written as `if not str(sh.value(ref)).startswith("=")` is blind and will
        happily literalise a mirror/echo cell, severing the inheritance silently.
        Ask here instead, or read with openpyxl `data_only=False`.
        """
        el = self.element(ref)
        return bool(el) and "<f" in el

    def value(self, ref: str):
        """The cell's cached VALUE, shared strings resolved. For read-back checks.

        NOT a formula test: a formula cell returns its cached result here, and a
        freshly generated file has no cache at all. Use `has_formula()`.
        """
        el = self.element(ref)
        if el is None:
            return None
        t = re.search(r'\st="([^"]+)"', el)
        kind = t.group(1) if t else "n"
        if kind == "inlineStr":
            m = re.search(r"<is>.*?<t[^>]*>(.*?)</t>", el, re.S)
            return _unesc(m.group(1)) if m else None
        v = re.search(r"<v>(.*?)</v>", el, re.S)
        if v is None:
            return None
        raw = v.group(1)
        if kind == "s":
            return self.book.shared_string_at(int(raw))
        if kind == "str":
            return _unesc(raw)
        if kind == "b":
            return raw == "1"
        try:
            return float(raw) if "." in raw or "e" in raw.lower() else int(raw)
        except ValueError:
            return _unesc(raw)

    def used_refs(self, col: str, first_row: int = 1, last_row: int | None = None):
        """Existing cell refs in a column, ascending — for building bulk edits."""
        self._index()
        out = []
        for ref in self._cells:
            c, r = split_ref(ref)
            if c == col.upper() and r >= first_row and (last_row is None or r <= last_row):
                out.append((r, ref))
        return [ref for _, ref in sorted(out)]

    # --- writes -----------------------------------------------------------
    def _write(self, ref: str, body: str, *, extra_attrs: str = "",
               keep_style: bool = True) -> None:
        """Queue a replacement element for ``ref``, preserving its style index."""
        ref = ref.upper()
        col, row = split_ref(ref)
        self._index()
        s = self.style_of(ref) if keep_style else None
        attrs = f' r="{ref}"' + (f' s="{s}"' if s else "") + extra_attrs
        el = f"<c{attrs}>{body}</c>" if body else f"<c{attrs}/>"
        if ref in self._cells:
            self._edits[ref] = el
        else:
            self._inserts.setdefault(row, {})[col_index(col)] = el

    def set_inline_text(self, ref: str, text: str) -> None:
        """Write a STRING as an inline `<is><t>` element, no shared-string table.

        Needed because a workbook openpyxl produced has NO xl/sharedStrings.xml
        at all — every string sits inline — so `shared_string()` raises and the
        whole patch route was unavailable on those files. Since openpyxl is what
        generates most of this project's workbooks, that ruled the patcher out
        of exactly the files it is safest on.

        Inline strings carry the same protection as shared ones: the cell has no
        numeric interpretation, so "3.30" cannot become 3.3.

        `xml:space="preserve"` matters — without it a leading or trailing space
        is stripped on read, and a trailing space is load-bearing data here
        (DOCUMENT.EXTERNAL_ID has a ' ' variant covering 10,136 rows).
        """
        self._write(ref, f'<is><t xml:space="preserve">{_esc(str(text))}'
                         f'</t></is>', extra_attrs=' t="inlineStr"')

    def set_text(self, ref: str, text: str) -> None:
        """Write a STRING, via the shared-string table where one exists.

        Use this for every identifier column. A string cell has no numeric
        interpretation, so Excel cannot turn "3.30" into 3.3 or "1:1" into a time
        — the coercion that silently corrupts ids when written through COM.

        Falls back to an inline string when the workbook has no shared-string
        part rather than raising, so openpyxl-produced files are patchable.
        """
        try:
            idx = self.book.shared_string(str(text))
        except KeyError:
            self.set_inline_text(ref, text)
            return
        self._write(ref, f"<v>{idx}</v>", extra_attrs=' t="s"')

    def set_number(self, ref: str, value: float | int) -> None:
        self._write(ref, f"<v>{value}</v>")

    def set_bool(self, ref: str, value: bool) -> None:
        self._write(ref, f"<v>{1 if value else 0}</v>", extra_attrs=' t="b"')

    def set_formula(self, ref: str, formula: str) -> None:
        """Write a formula. It carries NO cached value, so any reader that does not
        calculate (openpyxl data_only=True, a chart cache) sees blank until Excel
        opens the file once."""
        self._write(ref, f"<f>{_esc(formula.lstrip('='))}</f>")

    def set_blank(self, ref: str) -> None:
        """Empty a cell but KEEP its style — fills and borders are per-cell, so
        deleting the <c> element punches a visible hole in the grid."""
        self._write(ref, "")

    def set_cells(self, values: dict[str, object], *, text: bool = True) -> int:
        """Bulk write {ref: value}. All of them cost ONE pass over the part.

        ``text=True`` (default) routes strings through the shared-string table.
        Numbers and bools are written as numbers/bools; None blanks the cell.
        """
        for ref, v in values.items():
            if v is None:
                self.set_blank(ref)
            elif isinstance(v, bool):
                self.set_bool(ref, v)
            elif isinstance(v, (int, float)) and not text:
                self.set_number(ref, v)
            else:
                self.set_text(ref, str(v))
        return len(values)

    def copy_cell_value(self, ref: str, source_ref: str) -> None:
        """Give ``ref`` the VALUE of ``source_ref``, keeping ref's own style."""
        src = self.element(source_ref)
        if src is None:
            raise KeyError(f"{self.name}!{source_ref} is empty")
        v = re.search(r"<v>(.*?)</v>", src, re.S)
        if v is None:
            raise ValueError(f"{source_ref} holds no <v> value to copy")
        t = re.search(r'\st="([^"]+)"', src)
        self._write(ref, f"<v>{v.group(1)}</v>",
                    extra_attrs=f' t="{t.group(1)}"' if t else "")

    # --- geometry ---------------------------------------------------------
    def set_col_width(self, index: int | str, width: float) -> None:
        """Set a column's width, extending <cols> when it has no entry."""
        index = col_index(index) if isinstance(index, str) else index
        xml = self.xml
        pat = rf'<col([^>]*?)\bmin="{index}"([^>]*?)max="{index}"([^>]*?)/>'
        m = re.search(pat, xml)
        if m:
            new = m.group(0)
            new = (re.sub(r'\swidth="[^"]*"', f' width="{width}"', new)
                   if 'width="' in new else new[:-2] + f' width="{width}"/>')
            if "customWidth" not in new:
                new = new[:-2] + ' customWidth="1"/>'
            self.xml = xml.replace(m.group(0), new, 1)
            return
        entry = f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        if "<cols>" in xml:
            self.xml = xml.replace("<cols>", f"<cols>{entry}", 1)
        else:
            at = xml.find("<sheetData")
            self.xml = xml[:at] + f"<cols>{entry}</cols>" + xml[at:]

    def set_col_hidden(self, index: int | str, hidden: bool = True) -> None:
        index = col_index(index) if isinstance(index, str) else index
        xml = self.xml
        m = re.search(rf'<col([^>]*?)\bmin="{index}"([^>]*?)max="{index}"([^>]*?)/>', xml)
        if not m:
            raise KeyError(f"{self.name} has no <col> entry for column {index}")
        new = re.sub(r'\shidden="[^"]*"', "", m.group(0))
        if hidden:
            new = new[:-2] + ' hidden="1"/>'
        self.xml = xml.replace(m.group(0), new, 1)

    def set_row_heights(self, heights: dict[int, float]) -> None:
        """Set several row heights in one pass (customHeight, so Excel keeps them)."""
        xml = self.xml
        out, last = [], 0
        for m in _ROW_RE.finditer(xml):
            r = re.match(r'<row\b([^>]*?)\sr="(\d+)"([^>]*?)(/?)>', m.group(0))
            if not r:
                continue
            n = int(r.group(2))
            if n not in heights:
                continue
            attrs = re.sub(r'\s(ht|customHeight)="[^"]*"', "", r.group(1) + r.group(3))
            out.append((m.start(), m.start() + len(r.group(0)),
                        f'<row{attrs} r="{n}" ht="{heights[n]}"'
                        f' customHeight="1"{r.group(4)}>'))
        xml = _splice(xml, out)
        self.xml = xml
        missing = set(heights) - {int(re.match(r'<row\b[^>]*?\sr="(\d+)"', m.group(0)).group(1))
                                  for m in _ROW_RE.finditer(xml)
                                  if re.match(r'<row\b[^>]*?\sr="(\d+)"', m.group(0))}
        if missing:
            raise KeyError(f"{self.name} has no <row> element for {sorted(missing)} "
                           f"(a row with no cells is not stored)")

    def set_row_height(self, row: int, points: float) -> None:
        self.set_row_heights({row: points})

    # --- formatting by rule ----------------------------------------------
    def add_rule(self, sqref: str, dxf: str, *, priority: int = 100,
                 formula: str = "TRUE") -> int:
        """Apply ``dxf`` over ``sqref`` as ONE conditional-formatting rule.

        Restyling cells individually mints a new style record per distinct format
        touched — thousands of them for a whole-row sweep — and in a workbook whose
        cell controls are bound to the style table that is not merely slow.
        A cfRule costs a single <dxf>, survives re-sorts, and can be removed again.

        ``priority`` defaults to 100 so existing rules (usually 1..20) keep winning
        on their own cells. ``sqref`` takes several space- or comma-separated blocks.

        ``formula`` is XML-escaped for you — pass the formula as you would type it
        in Excel (`$D4<>$D3`), not pre-escaped.
        """
        dxf_id = self.book.add_dxf(dxf)
        block = (f'<conditionalFormatting sqref="{sqref.replace(",", " ")}">'
                 f'<cfRule type="expression" dxfId="{dxf_id}" priority="{priority}">'
                 f"<formula>{_esc_formula(formula)}</formula>"
                 f"</cfRule></conditionalFormatting>")
        xml = self.xml
        last = xml.rfind("</conditionalFormatting>")
        if last != -1:
            at = last + len("</conditionalFormatting>")
        else:
            nxt = [xml.find(t) for t in _AFTER_CF if xml.find(t) != -1]
            at = min(nxt) if nxt else xml.find("</worksheet>")
        self.xml = xml[:at] + block + xml[at:]
        return dxf_id

    # kept for callers of the original helper
    def add_font_rule(self, sqref: str, rgb: str, *, priority: int = 100) -> int:
        return self.add_rule(sqref, dxf_font(rgb), priority=priority)

    def cf_blocks(self) -> list[str]:
        return re.findall(r'<conditionalFormatting sqref="([^"]+)"', self.xml)

    def drop_rules(self, dxf_id: int) -> int:
        """Remove every cfRule pointing at ``dxf_id`` (the dxf itself stays, harmless)."""
        xml, n = self.xml, 0
        for m in reversed(list(re.finditer(
                r'<conditionalFormatting\b[^>]*>.*?</conditionalFormatting>', xml, re.S))):
            body = m.group(0)
            hit = re.findall(rf'<cfRule\b[^>]*\bdxfId="{dxf_id}"[^>]*>.*?</cfRule>', body, re.S)
            if not hit:
                continue
            n += len(hit)
            for h in hit:
                body = body.replace(h, "")
            if "<cfRule" not in body:
                body = ""
            xml = xml[:m.start()] + body + xml[m.end():]
        self.xml = xml
        return n

    # --- apply ------------------------------------------------------------
    def flush(self) -> None:
        """Apply every buffered edit in ONE pass over the part."""
        if not (self._edits or self._inserts):
            return
        edits, inserts = self._edits, self._inserts
        self._edits, self._inserts = {}, {}
        self._index()
        x = self._raw()

        # 1. in-place replacements — all of them in a single pass
        x = _splice(x, [(self._cells[r][0], self._cells[r][1], el)
                        for r, el in edits.items() if r in self._cells])
        self._indexed = False

        # 2. insertions — need a fresh index (the offsets above have moved).
        # Each touched row is REBUILT from its cells sorted by column: a row whose
        # <c> children are out of column order makes Excel offer to repair the file.
        if inserts:
            self.book.parts_text[self.part] = x
            self._indexed = False
            self._index()
            x = self._raw()
            plan: list[tuple[int, int, str]] = []
            for row in sorted(inserts):
                cells = dict(inserts[row])
                if row in self._rows:
                    a, b = self._rows[row]
                    row_xml = x[a:b]
                    open_tag = re.match(r"<row\b[^>]*?/?>", row_xml).group(0)
                    for m in _CELL_RE.finditer(row_xml):
                        rr = re.match(r'<c\b[^>]*?\sr="([A-Z]+)\d+"', m.group(0))
                        if rr:
                            cells[col_index(rr.group(1))] = m.group(0)
                    body = "".join(cells[k] for k in sorted(cells))
                    plan.append((a, b, open_tag.rstrip("/>") + ">" + body + "</row>"
                                 if open_tag.endswith("/>")
                                 else open_tag + body + "</row>"))
                else:
                    body = "".join(cells[k] for k in sorted(cells))
                    later = [r for r in self._rows if r > row]
                    at = self._rows[min(later)][0] if later else x.find("</sheetData>")
                    plan.append((at, at, f'<row r="{row}">{body}</row>'))
            x = _splice(x, plan)

        self.book.parts_text[self.part] = x
        self._indexed = False
        self._fix_geometry()

    def _fix_geometry(self) -> None:
        """Keep <dimension> and each row's @spans consistent with the cells present.

        Both are hints, but a stale <dimension> makes Excel's used-range wrong and
        a stale @spans confuses other readers.
        """
        self._index()
        x = self._raw()
        if not self._cells:
            return
        cols = [col_index(split_ref(r)[0]) for r in self._cells]
        rows = [split_ref(r)[1] for r in self._cells]
        want = f"{col_letter(min(cols))}{min(rows)}:{col_letter(max(cols))}{max(rows)}"
        m = re.search(r'<dimension ref="([^"]+)"/>', x)
        if m and m.group(1) != want:
            x = x[:m.start()] + f'<dimension ref="{want}"/>' + x[m.end():]
        out = []
        for m in _ROW_RE.finditer(x):
            row_xml = m.group(0)
            sp = re.search(r'\sspans="[^"]*"', row_xml)
            if not sp:
                continue
            idx = [col_index(rr.group(1)) for rr in
                   re.finditer(r'<c\b[^>]*?\sr="([A-Z]+)\d+"', row_xml)]
            if not idx:
                continue
            new = f' spans="{min(idx)}:{max(idx)}"'
            if sp.group(0) != new:
                out.append((m.start() + sp.start(), m.start() + sp.end(), new))
        self.book.parts_text[self.part] = _splice(x, out)
        self._indexed = False


def _unesc(s: str) -> str:
    for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
                 ("&apos;", "'"), ("&amp;", "&")):
        s = s.replace(a, b)
    return s


_ATTR_RE = re.compile(r'([A-Za-z_][\w:.\-]*)\s*=\s*"([^"]*)"')


def _attrs(tag: str) -> dict[str, str]:
    """Attributes of one XML start-tag, as a dict.

    Attribute ORDER is not significant in XML and writers disagree on it — Excel
    writes <Relationship Id=.. Type=.. Target=..>, openpyxl writes Type first.
    A regex that pins two attributes in sequence matches one writer and returns
    None on the other, which surfaces as an AttributeError three lines later
    instead of a useful error. Parse, don't pattern-match a layout.
    """
    return {k: v for k, v in _ATTR_RE.findall(tag)}


class Book:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        with zipfile.ZipFile(self.path) as z:
            self.names = z.namelist()
            self.info = {i.filename: i for i in z.infolist()}
            self.parts = {n: z.read(n) for n in self.names}
        self.parts_text: dict[str, str] = {}
        self._sheets: dict[str, Sheet] = {}
        self._sst: list[str] | None = None

    # --- parts ------------------------------------------------------------
    def _text(self, part: str) -> str:
        if part not in self.parts_text:
            if part not in self.parts:
                raise KeyError(f"{self.path.name} has no part {part!r}")
            self.parts_text[part] = self.parts[part].decode("utf-8")
        return self.parts_text[part]

    def sheet_names(self) -> list[str]:
        wbx = self._text("xl/workbook.xml")
        return [_unesc(m.group(1)) for m in
                re.finditer(r'<sheet\b[^>]*?name="([^"]*)"', wbx)]

    def sheet(self, name: str | None = None) -> Sheet:
        """A sheet by name, or the first sheet when called with no name."""
        if name is None:
            name = self.sheet_names()[0]
        if name not in self._sheets:
            # XML attribute ORDER IS NOT SIGNIFICANT, and writers disagree: Excel
            # emits <sheet name= .. r:id=..> and Target after Id, openpyxl emits
            # Type before Id. Matching 'name="..."[^>]*r:id="..."' in one regex
            # silently returns None on the other writer's ordering, so parse the
            # start-tag's attributes instead of assuming a layout.
            wbx = self._text("xl/workbook.xml")
            rid = next((a.get("r:id") or a.get("id") for a in
                        map(_attrs, re.findall(r"<sheet\b[^>]*?/?>", wbx))
                        if _unesc(a.get("name", "")) == name), None)
            if rid is None:
                raise KeyError(f"no sheet named {name!r}; have {self.sheet_names()}")
            rels = self._text("xl/_rels/workbook.xml.rels")
            target = next((a.get("Target") for a in
                           map(_attrs, re.findall(r"<Relationship\b[^>]*?/?>", rels))
                           if a.get("Id") == rid), None)
            if target is None:
                raise KeyError(
                    f"sheet {name!r} points at relationship {rid!r}, which "
                    f"xl/_rels/workbook.xml.rels does not define")
            # Target is relative to xl/ ('worksheets/sheet1.xml') OR absolute from
            # the package root ('/xl/worksheets/sheet1.xml') — normalise both.
            t = target.replace("../", "").lstrip("/")
            part = t if t.startswith("xl/") else "xl/" + t
            self._text(part)
            self._sheets[name] = Sheet(self, name, part)
        return self._sheets[name]

    # --- shared strings ---------------------------------------------------
    SST = "xl/sharedStrings.xml"

    def _sst_list(self) -> list[str]:
        if self._sst is None:
            xml = self._text(self.SST)
            self._sst = re.findall(r"<si>(.*?)</si>", xml, re.S)
            # An index for O(1) lookup. Rebuilding the part per new string turned
            # 362 writes into 4.4s of pure string copying; appends are buffered
            # and written once, at save.
            self._sst_index = {si: i for i, si in enumerate(self._sst)}
            self._sst_new: list[str] = []
        return self._sst

    def shared_string_at(self, index: int) -> str:
        """Resolve a shared-string index to plain text (rich runs concatenated)."""
        si = self._sst_list()[index]
        return _unesc("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S)))

    def shared_string(self, text: str) -> int:
        """Index of ``text`` in sharedStrings.xml, queueing an append if absent."""
        if self.SST not in self.parts:
            raise KeyError(
                "this workbook has no xl/sharedStrings.xml (every string is inline "
                "— likely written by openpyxl). Use set_number/copy_cell_value, or "
                "add the part with COM by typing one string into a cell.")
        items = self._sst_list()
        esc = _esc(text)
        want, want_sp = f"<t>{esc}</t>", f'<t xml:space="preserve">{esc}</t>'
        for form in (want, want_sp):
            if form in self._sst_index:
                return self._sst_index[form]
        node = want_sp if esc != esc.strip() else want
        items.append(node)
        self._sst_new.append(node)
        self._sst_index[node] = len(items) - 1
        return len(items) - 1

    def _flush_sst(self) -> None:
        if not getattr(self, "_sst_new", None):
            return
        n, xml = len(self._sst_new), self._text(self.SST)
        xml = xml.replace("</sst>", "".join(f"<si>{s}</si>" for s in self._sst_new) + "</sst>")
        for attr in ("count", "uniqueCount"):
            m = re.search(rf'\s{attr}="(\d+)"', xml)
            if m:
                xml = xml[:m.start()] + f' {attr}="{int(m.group(1)) + n}"' + xml[m.end():]
        self.parts_text[self.SST] = xml
        self._sst_new = []

    def add_dxf(self, dxf_xml: str) -> int:
        """Append a differential format; returns its dxfId.

        The id comes from the ACTUAL number of <dxf> children, never from the
        `count` attribute. Trusting the attribute is how a style table drifts:
        one bad append leaves count ahead of the children, every later id is off
        by that much, and the cfRules end up pointing PAST THE END of the table.
        openpyxl then raises IndexError on load and Excel silently DROPS the
        conditional formatting when it "repairs" the file. Reading the real
        count also self-heals a table that has already drifted.
        """
        if not isinstance(dxf_xml, str) or not dxf_xml.lstrip().startswith("<dxf"):
            raise TypeError(
                "add_dxf() takes <dxf> XML (e.g. dxf_font('FF808080')), not "
                f"{type(dxf_xml).__name__} {dxf_xml!r}. Sheet.add_rule() takes the "
                "SAME XML and mints the dxfId for you — passing an id you got back "
                "from add_dxf appends that number as text inside <dxfs>, so the "
                "count advances while the children do not.")
        part = "xl/styles.xml"
        xml = self._text(part)
        m = re.search(r'<dxfs count="(\d+)"\s*>(.*?)</dxfs>', xml, re.S)
        if m:
            body = m.group(2)
            n = len(re.findall(r"<dxf[ >]", body))        # ACTUAL children, not the attr
            xml = (xml[:m.start()] + f'<dxfs count="{n + 1}">{body}{dxf_xml}</dxfs>'
                   + xml[m.end():])
        elif re.search(r'<dxfs count="0"\s*/>', xml):
            n = 0
            xml = re.sub(r'<dxfs count="0"\s*/>', f'<dxfs count="1">{dxf_xml}</dxfs>',
                         xml, count=1)
        else:                       # no <dxfs> at all: it belongs after <cellStyles>
            n = 0
            for anchor in ("</cellStyles>", "</cellXfs>"):
                if anchor in xml:
                    xml = xml.replace(anchor, f"{anchor}<dxfs count=\"1\">{dxf_xml}</dxfs>", 1)
                    break
            else:
                raise ValueError("styles.xml has nowhere to put <dxfs>")
        self.parts_text[part] = xml
        return n

    # --- save -------------------------------------------------------------
    def save(self, target: str | Path | None = None, *,
             backup: bool = True, backup_dir: str | Path | None = None,
             tag: str = "patch") -> Path:
        """Rewrite the zip. Untouched parts are copied through byte-for-byte.

        Backs up the existing target first, timestamped, into a sibling
        ``_backups/`` folder (never beside the deliverable) unless told otherwise.
        """
        for sh in self._sheets.values():
            sh.flush()
        self._flush_sst()
        target = Path(target) if target else self.path
        if backup and target.exists():
            d = Path(backup_dir) if backup_dir else target.parent / "_backups"
            d.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(target, d / f"{target.stem}_{tag}_{stamp}{target.suffix}")
        tmp = target.with_suffix(target.suffix + ".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
            for n in self.names:                      # original part order preserved
                data = (self.parts_text[n].encode("utf-8")
                        if n in self.parts_text else self.parts[n])
                out.writestr(self.info[n], data)
        with zipfile.ZipFile(tmp) as check:           # never swap in a corrupt zip
            if check.testzip() is not None:
                tmp.unlink(missing_ok=True)
                raise OSError(f"{tmp.name} failed its CRC check — not swapped in")
        # The swap loses to a virus scanner holding the freshly-written target for a
        # moment (WinError 5), then succeeds on the very next try. Retry; never abort.
        for attempt in range(12):
            try:
                tmp.replace(target)
                return target
            except PermissionError:
                if attempt == 11:
                    break
                time.sleep(1)

        # STILL DENIED AFTER 12 TRIES — this is NOT a transient hold, and the
        # retry advice does not apply. Measured 2026-09-03: a file inside a
        # OneDrive folder carries `Attributes: Archive, ReparsePoint` once
        # Files-On-Demand has virtualised it, and os.replace() onto a reparse
        # point is refused by OneDrive's filter driver — WinError 5 — even
        # though the file is NOT locked and opens cleanly for ReadWrite. The
        # diagnosis that matters: if `[IO.File]::Open(path,'Open','ReadWrite',
        # 'None')` succeeds, nothing holds the file and no amount of retrying
        # will help.
        #
        # Writing THROUGH the placeholder works, because it is a content change
        # rather than a directory-entry swap. The CRC check above has already
        # passed, so the bytes are known good before they land.
        try:
            with open(target, "wb") as fh:
                fh.write(tmp.read_bytes())
        except OSError:
            raise
        else:
            tmp.unlink(missing_ok=True)
            return target
