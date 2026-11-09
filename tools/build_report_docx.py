"""Build the report .docx from a Markdown draft, using the sprint template's styles.

Usage:
    python -I tools/build_report_docx.py --draft docs/report_draft.md \
        --template "docs/Copy of Apart Research hackathon submission template.docx" \
        --out docs/swarm_lineage_report.docx

The template is copied, never modified. Title, author and abstract cells are filled;
the guidance info box and guidance text are removed; the body is rebuilt from the draft.

Draft conventions:
    # Title                      document title (first line)
    first non-empty lines after the title until '## Abstract': author lines
    ## Heading / ### Heading      template Heading 2 / Heading 3
    **bold**, *italic*           inline formatting
    [figures/NAME.png]           a figure (full text width); the next *...* paragraph is its caption
    [insert Table N ...]         Table N from results/T01_tables.md
    lines starting '1. '         numbered list items (kept as text)

File structure:
    inline_runs     add a paragraph's text with **bold** / *italic* runs
    set_cell_text   replace all text of a paragraph element
    md_tables       parse Table 1 / Table 2 from results/T01_tables.md
    add_table       write a simple bordered table
    build           main conversion
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

REPO = Path(__file__).resolve().parents[1]
INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*)")


def inline_runs(par, text: str, size: float | None = None, italic_all: bool = False) -> None:
    """Add text to a paragraph, honouring **bold** and *italic* markers.

    Args:
        par: python-docx paragraph.
        text: Markdown-ish text.
        size: Optional font size in points.
        italic_all: Make every run italic.
    """
    for part in INLINE_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = par.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("*") and part.endswith("*"):
            run = par.add_run(part[1:-1])
            run.italic = True
        else:
            run = par.add_run(part)
        if italic_all:
            run.italic = True
        if size:
            run.font.size = Pt(size)


def set_cell_text(p_el, text: str, italic: bool | None = None) -> None:
    """Replace the visible text of a paragraph element, keeping the first run's formatting.

    Args:
        p_el: w:p element.
        text: New text ('' to blank it).
        italic: Force italic on/off if given.
    """
    runs = p_el.findall(qn("w:r"))
    for r in runs[1:]:
        p_el.remove(r)
    if not runs:
        return
    r = runs[0]
    for child in list(r):
        if child.tag in (qn("w:t"), qn("w:br"), qn("w:tab")):
            r.remove(child)
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    r.append(t)
    if italic is not None:
        rpr = r.find(qn("w:rPr"))
        if rpr is None:
            rpr = OxmlElement("w:rPr")
            r.insert(0, rpr)
        for i in rpr.findall(qn("w:i")):
            rpr.remove(i)
        if italic:
            rpr.append(OxmlElement("w:i"))


def md_tables(path: Path) -> dict[str, list[list[str]]]:
    """Parse the Markdown tables in results/T01_tables.md.

    Args:
        path: File path.

    Returns:
        {'Table 1': rows, 'Table 2': rows}, each row a list of cell strings.
    """
    out: dict[str, list[list[str]]] = {}
    cur = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("Table "):
            cur = line.strip()
            out[cur] = []
        elif line.startswith("|") and cur and not set(line.replace("|", "").strip()) <= set("-: "):
            out[cur].append([c.strip() for c in line.strip().strip("|").split("|")])
    return out


def _borders(table) -> None:
    """Give a table thin single borders.

    Args:
        table: python-docx table.
    """
    tblpr = table._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), "4")
        e.set(qn("w:color"), "BFBFBF")
        b.append(e)
    tblpr.append(b)


def add_table(doc, rows: list[list[str]], size: float = 7.5) -> None:
    """Append a simple bordered table with a bold header row.

    Args:
        doc: Document.
        rows: Header row first.
        size: Font size in points.
    """
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    _borders(t)
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = t.cell(i, j)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(val)
            run.font.size = Pt(size)
            run.bold = i == 0


def build(draft: Path, template: Path, out: Path) -> None:
    """Convert the draft into a copy of the template.

    Args:
        draft: Markdown draft.
        template: Template .docx (copied, not modified).
        out: Output .docx.
    """
    shutil.copyfile(template, out)
    doc = docx.Document(str(out))
    lines = draft.read_text(encoding="utf-8").splitlines()
    title = lines[0].lstrip("# ").strip()
    i_abs = next(k for k, l in enumerate(lines) if l.strip() == "## Abstract")
    authors = [l.strip() for l in lines[1:i_abs] if l.strip() and not l.startswith("Track:")]
    i_body = next(k for k, l in enumerate(lines) if l.startswith("## 1."))
    abstract = " ".join(l.strip() for l in lines[i_abs + 1:i_body] if l.strip())

    top = doc.tables[0]
    title_p = [p for p in top.rows[0].cells[0]._tc.iter(qn("w:p")) if "PROJECT TITLE" in "".join(t.text or "" for t in p.iter(qn("w:t")))][0]
    set_cell_text(title_p, title)
    cell = top.rows[1].cells[0]._tc
    # Replace the narrow nested author-slot tables with one centred line per author.
    nested = [t for t in cell.findall(".//" + qn("w:tbl"))
              if "Author name" in "".join(x.text or "" for x in t.iter(qn("w:t")))]
    if nested:
        anchor = nested[0]
        parent = anchor.getparent()
        idx = list(parent).index(anchor)
        for a in authors:
            name, _, aff = a.partition("—")
            p = OxmlElement("w:p")
            ppr = OxmlElement("w:pPr")
            jc = OxmlElement("w:jc")
            jc.set(qn("w:val"), "center")
            ppr.append(jc)
            p.append(ppr)
            plain = a.startswith("With ")
            for text, bold in ((name.strip(), not plain), (("  " + aff.strip()) if aff.strip() else "", False)):
                if not text:
                    continue
                r = OxmlElement("w:r")
                rpr = OxmlElement("w:rPr")
                if bold:
                    rpr.append(OxmlElement("w:b"))
                r.append(rpr)
                t = OxmlElement("w:t")
                t.set(qn("xml:space"), "preserve")
                t.text = text
                r.append(t)
                p.append(r)
            parent.insert(idx, p)
            idx += 1
        for t in nested:
            t.getparent().remove(t)
    abs_p = [p for p in cell.iter(qn("w:p")) if "Summarize your project" in "".join(t.text or "" for t in p.iter(qn("w:t")))][0]
    set_cell_text(abs_p, abstract, italic=False)

    body = doc.element.body
    info_tbl = doc.tables[1]._tbl
    children = list(body)
    start = children.index(info_tbl)
    sectpr = body.find(qn("w:sectPr"))
    for ch in children[start:]:
        if ch is not sectpr:
            body.remove(ch)

    tables = md_tables(REPO / "results" / "T01_tables.md")
    k = i_body
    pending_caption = False
    while k < len(lines):
        line = lines[k].rstrip()
        s = line.strip()
        k += 1
        if not s:
            continue
        if s.startswith("### "):
            doc.add_paragraph(s[4:], style="Heading 3")
        elif s.startswith("## "):
            doc.add_paragraph(s[3:], style="Heading 2")
        elif s.startswith("**Figure") and "[figures/" in s:
            label, _, rest = s.partition("[")
            path = rest.split("]")[0]
            pic = doc.add_paragraph()
            pic.alignment = WD_ALIGN_PARAGRAPH.CENTER
            pic.paragraph_format.keep_with_next = True
            pic.add_run().add_picture(str(REPO / path), width=Inches(6.5))
            cap_text = s.split("]", 1)[1].strip()
            cap = doc.add_paragraph()
            inline_runs(cap, label.strip() + " " + cap_text, size=8.5)
        elif s.startswith("**Table") and "[insert Table" in s:
            label = s.split("[")[0].strip()
            name = "Table 1" if "Table 1" in s.split("[")[1] else "Table 2"
            cap = doc.add_paragraph()
            cap.paragraph_format.keep_with_next = True
            inline_runs(cap, label + " " + TABLE_CAPTIONS.get(name, ""), size=8.5)
            add_table(doc, tables[name])
        elif s.startswith("[insert Table"):
            name = "Table 1" if "Table 1" in s else "Table 2"
            add_table(doc, tables[name])
        elif s.startswith("[figures/"):
            for path in re.findall(r"figures/[\w.]+\.png", s):
                pic = doc.add_paragraph()
                pic.alignment = WD_ALIGN_PARAGRAPH.CENTER
                pic.add_run().add_picture(str(REPO / path), width=Inches(6.0))
        else:
            p = doc.add_paragraph()
            if s.startswith(("Allamanis", "Dias", "Forman", "Grozea", "Hammond", "Holtz", "Hurlbert", "Kapoor", "Li et",
                             "Marmerola", "METR", "Motwani", "Pacheco", "Price", "Roberts", "Von Arx")):
                p.paragraph_format.left_indent = Inches(0.3)
                p.paragraph_format.first_line_indent = Inches(-0.3)
                inline_runs(p, s, size=9)
            else:
                inline_runs(p, s)
    doc.save(str(out))


TABLE_CAPTIONS = {
    "Table 1": "*Corpora. Swarm Traces motivates the problem but cannot be evaluated: none of its rows is timestamped. Pairs and clusters are from the v2 pipeline.*",
    "Table 2": "*Pre-registered claims and outcomes. Every rule was written before the experiment ran; outcomes are as logged.*",
}


def main() -> None:
    """Parse arguments and build."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", default="docs/report_draft.md")
    ap.add_argument("--template", default="docs/Copy of Apart Research hackathon submission template.docx")
    ap.add_argument("--out", default="docs/swarm_lineage_report.docx")
    a = ap.parse_args()
    build(REPO / a.draft, REPO / a.template, REPO / a.out)
    print(a.out)


if __name__ == "__main__":
    main()
