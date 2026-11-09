"""Build the report as LaTeX (XeLaTeX) from the Markdown draft, mirroring the sprint template.

Template look reproduced (read from the template's document.xml): Old Standard TT
throughout; Letter page, 1 in margins; body 11 pt, line spacing 1.15; title bold 20 pt
centred between rules; authors centred; "Abstract" bold 14 pt centred; abstract
justified, indented 0.375 in; section headings bold 14 pt #434343; subsection headings
bold 13 pt #666666; lists indented 0.5 in.

Usage:
    python -I tools/build_report_tex.py --draft docs/report_draft.md --out report/swarm_lineage_report.tex

File structure:
    PREAMBLE        LaTeX preamble with the template's typography
    esc             escape text for LaTeX, convert **bold** / *italic* and a few symbols
    md_tables       read Table 1 / Table 2 from results/T01_tables.md
    table_tex       one booktabs table
    build           main conversion
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage[letterpaper,margin=1in]{geometry}
\usepackage{fontspec}
\setmainfont{OldStandard}[Path=./fonts/, Extension=.ttf, UprightFont=*-Regular, BoldFont=*-Bold, ItalicFont=*-Italic]
\usepackage{xcolor}
\definecolor{h2}{HTML}{434343}
\definecolor{h3}{HTML}{666666}
\usepackage{setspace}
\setstretch{1.15}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{tabularx}
\usepackage{array}
\usepackage{enumitem}
\setlist{leftmargin=0.5in, itemsep=1pt, topsep=3pt}
\usepackage[font=small, labelfont=bf, skip=4pt]{caption}
\usepackage{titlesec}
\titleformat{\section}{\fontsize{14}{18}\selectfont\bfseries\color{h2}}{}{0pt}{}
\titlespacing*{\section}{0pt}{10pt}{2pt}
\titleformat{\subsection}{\fontsize{13}{16}\selectfont\bfseries\color{h3}}{}{0pt}{}
\titlespacing*{\subsection}{0pt}{8pt}{1pt}
\usepackage[section]{placeins}
\usepackage{float}
\emergencystretch=3em
\usepackage[hidelinks]{hyperref}
\usepackage{xurl}
\urlstyle{same}
\setlength{\parindent}{0pt}
\setlength{\parskip}{4pt}
\renewcommand{\arraystretch}{1.15}
\newcolumntype{L}{>{\raggedright\arraybackslash}X}
\setcounter{secnumdepth}{0}
\begin{document}
"""

SYMBOLS = {"→": r"$\rightarrow$", "∩": r"$\cap$", "≥": r"$\geq$", "≤": r"$\leq$", "−": r"$-$", "×": r"$\times$"}


def esc(text: str) -> str:
    """Escape LaTeX specials and convert inline Markdown emphasis.

    Args:
        text: Markdown-ish text.

    Returns:
        LaTeX string.
    """
    out = []
    for part in re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            out.append(r"\textbf{" + _plain(part[2:-2]) + "}")
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append(r"\textit{" + _plain(part[1:-1]) + "}")
        else:
            out.append(_plain(part))
    return "".join(out)


def _plain(s: str) -> str:
    """Escape one plain-text fragment.

    Args:
        s: Text without emphasis markers.

    Returns:
        LaTeX string.
    """
    s = s.replace(">=", "≥").replace("<=", "≤").replace("->", "→")
    s = s.replace("\\", r"\textbackslash{}")
    for ch in "&%$#_{}":
        s = s.replace(ch, "\\" + ch)
    s = s.replace("~", r"\textasciitilde{}").replace("^", r"\textasciicircum{}")
    for k, v in SYMBOLS.items():
        s = s.replace(k, v)
    s = re.sub(r'"([^"]+)"', "“\\1”", s)
    s = s.replace("'", "’")
    s = re.sub(r"(https?://\S+?)([.,;)]?)(\s|$)", lambda m: r"\url{" + m.group(1).replace("\\", "") + "}" + m.group(2) + m.group(3), s)
    return s


def md_tables(path: Path) -> dict[str, list[list[str]]]:
    """Parse the Markdown tables in results/T01_tables.md.

    Args:
        path: File path.

    Returns:
        {'Table 1': rows, 'Table 2': rows}.
    """
    out: dict[str, list[list[str]]] = {}
    cur = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("|"):
            cur = line.strip()
            out[cur] = []
        elif line.startswith("|") and cur and not set(line.replace("|", "").strip()) <= set("-: "):
            out[cur].append([c.strip() for c in line.strip().strip("|").split("|")])
    return out


def table_tex(rows: list[list[str]], caption: str, label: str) -> str:
    """One booktabs table inside a float.

    Args:
        rows: Header row first.
        caption: Caption text (Markdown-ish).
        label: Label key.

    Returns:
        LaTeX string.
    """
    n = len(rows[0])
    spec = "L" * n
    head = " & ".join(r"\textbf{" + _plain(c) + "}" for c in rows[0]) + r" \\"
    body = "\n".join(" & ".join(_plain(c) for c in r) + r" \\" for r in rows[1:])
    return (r"\begin{table}[htbp]" + "\n" + r"\centering\small" + "\n" + r"\caption{" + esc(caption) + "}\\label{" + label + "}\n"
            + r"\begin{tabularx}{\textwidth}{" + spec + "}\n\\toprule\n" + head + "\n\\midrule\n" + body + "\n\\bottomrule\n"
            + r"\end{tabularx}" + "\n" + r"\end{table}" + "\n")


TABLE_CAPTIONS = {
    "Table 1": "Corpora. Swarm Traces motivates the problem but cannot be evaluated: none of its rows is timestamped. Pairs and clusters are from the v2 pipeline.",
    "Table 2": "Pre-registered claims and outcomes. Every rule was written before the experiment ran; outcomes are as logged.",
}


def build(draft: Path, out: Path) -> None:
    """Convert the Markdown draft to a LaTeX file.

    Args:
        draft: Markdown draft.
        out: Output .tex path (figures referenced relative to the repo root).
    """
    lines = draft.read_text(encoding="utf-8").splitlines()
    title = lines[0].lstrip("# ").strip()
    i_abs = next(k for k, l in enumerate(lines) if l.strip() == "## Abstract")
    head_lines = [l.strip() for l in lines[1:i_abs] if l.strip() and not l.startswith("Track:")]
    i_body = next(k for k, l in enumerate(lines) if l.startswith("## 1."))
    abstract = " ".join(l.strip() for l in lines[i_abs + 1:i_body] if l.strip())
    tables = md_tables(REPO / "results" / "T01_tables.md")

    authors = [l for l in head_lines if not l.startswith("With ")]
    tex = [PREAMBLE]
    tex.append(r"\noindent\rule{\textwidth}{1.2pt}\par\vspace{10pt}")
    tex.append(r"\begin{center}{\fontsize{20}{24}\selectfont\bfseries " + esc(title) + r"\par}\end{center}")
    tex.append(r"\vspace{2pt}\noindent\rule{\textwidth}{0.5pt}\par\vspace{8pt}")
    tex.append(r"\begin{center}\setstretch{1.0}")
    for a in authors:
        name, _, aff = a.partition("—")
        tex.append(esc(name.strip()) + (r"\\ {\small " + esc(aff.strip()) + "}" if aff.strip() else "") + r"\\[6pt]")
    tex.append(r"\textbf{With}\\ Apart Research")
    tex.append(r"\end{center}")
    tex.append(r"\begin{center}{\fontsize{14}{17}\selectfont\bfseries Abstract}\end{center}\vspace{-4pt}")
    tex.append(r"\begin{list}{}{\setlength{\leftmargin}{0.375in}\setlength{\rightmargin}{0.03in}}\item[]")
    tex.append(esc(abstract))
    tex.append(r"\end{list}\vspace{6pt}")

    in_list = False
    k = i_body
    while k < len(lines):
        s = lines[k].strip()
        k += 1
        if not s:
            if in_list:
                tex.append(r"\end{enumerate}")
                in_list = False
            continue
        if re.match(r"^\d+\. ", s) and not s.startswith(("1. Introduction", "2. Related", "3. Methods", "4. Results", "5. Discussion", "6. Conclusion")):
            if not in_list:
                tex.append(r"\begin{enumerate}")
                in_list = True
            tex.append(r"\item " + esc(re.sub(r"^\d+\. ", "", s)))
            continue
        if in_list:
            tex.append(r"\end{enumerate}")
            in_list = False
        if s.startswith("### "):
            tex.append(r"\subsection{" + esc(s[4:]) + "}")
        elif s.startswith("## "):
            name = s[3:]
            if name == "Appendix":
                tex.append(r"\clearpage")
            tex.append(r"\section{" + esc(name) + "}")
            if name == "References":
                tex.append(r"\begingroup\small\setlength{\parskip}{2pt}")
                while k < len(lines) and not lines[k].startswith("## "):
                    r = lines[k].strip()
                    k += 1
                    if r:
                        tex.append(r"\noindent\hangindent=0.3in\hangafter=1 " + esc(r) + r"\par")
                tex.append(r"\endgroup")
        elif s.startswith("**Figure") and "[figures/" in s:
            label = s.split("**")[1].strip()
            path = s.split("[", 1)[1].split("]")[0]
            cap = s.split("]", 1)[1].strip()
            num = re.findall(r"\d+", label)[0]
            if (REPO / path.replace(".png", ".pdf")).exists():
                path = path.replace(".png", ".pdf")
            tex.append(r"\begin{figure}[htbp]\centering" + "\n" + r"\includegraphics[width=\textwidth]{../" + path + "}\n"
                       + r"\caption{" + esc(cap.strip("*")) + "}\\label{fig:" + num + "}\n" + r"\end{figure}")
        elif "[insert " in s and " table]" in s:
            name = s.split("[insert ", 1)[1].split(" table]")[0]
            cap = s.split("]", 1)[1].strip().strip("*")
            tex.append(table_tex(tables[name], cap, "tab:" + name.lower()))
        elif s.startswith("[figures/"):
            paths = re.findall(r"figures/[\w.]+\.png", s)
            cap = ""
            if k < len(lines):
                nxt = k
                while nxt < len(lines) and not lines[nxt].strip():
                    nxt += 1
                if nxt < len(lines) and lines[nxt].strip().startswith("*Figure"):
                    cap = lines[nxt].strip().strip("*")
                    k = nxt + 1
            cap = re.sub(r"^Figure A\d+\.\s*", "", cap)
            tex.append(r"\begin{figure}[htbp]\centering" + "\n" + "\n".join(
                r"\includegraphics[width=0.92\textwidth]{../" + p + r"}\\[4pt]" for p in paths)
                + "\n" + r"\renewcommand{\thefigure}{A1}\caption{" + esc(cap) + "}\n" + r"\end{figure}")
        else:
            tex.append(esc(s) + "\n")
    if in_list:
        tex.append(r"\end{enumerate}")
    tex.append(r"\end{document}")
    text = "\n".join(tex)
    head, sep, tail = text.partition(r"\section{Appendix}")
    if sep:
        tail = tail.replace(r"\begin{table}[htbp]", r"\begin{table}[H]").replace(r"\begin{figure}[htbp]", r"\begin{figure}[H]")
        tail = tail.replace(r"\centering\small", r"\centering\footnotesize\setstretch{1.0}").replace(r"width=0.92\textwidth", r"width=0.70\textwidth")
        text = head + sep + tail
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")


def main() -> None:
    """Parse arguments and build."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", default="docs/report_draft.md")
    ap.add_argument("--out", default="report/swarm_lineage_report.tex")
    a = ap.parse_args()
    build(REPO / a.draft, REPO / a.out)
    print(a.out)


if __name__ == "__main__":
    main()
