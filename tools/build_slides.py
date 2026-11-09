"""Build the short presentation deck (report/swarm_lineage_deck.pptx) from the report figures.

Usage:
    python tools/build_slides.py

Figures are taken from figures/ (built by experiments/FIG_report.py); single panels are cropped
into report/slide_assets/. Every number on the slides is quoted from the report.

File structure:
    Constants      layout, palette, fonts
    crops          cut single panels out of the report figures
    helpers        title, text, bullets, image, notes, slide number
    slides         one function per slide
    main
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

REPO = Path(__file__).resolve().parents[1]
FIG = REPO / "figures"
OUT = REPO / "report" / "swarm_lineage_deck.pptx"
ASSETS = REPO / "report" / "slide_assets"
W, H = 13.333, 7.5
HEAD, BODY = "Cambria", "Calibri"
INK, MUTED, BLUE, ORANGE = RGBColor(0x0B, 0x0B, 0x0B), RGBColor(0x52, 0x51, 0x4E), RGBColor(0x2A, 0x78, 0xD6), RGBColor(0xEB, 0x68, 0x34)
DARK, ON_DARK, ON_DARK2 = RGBColor(0x1F, 0x29, 0x33), RGBColor(0xFF, 0xFF, 0xFF), RGBColor(0xC9, 0xD1, 0xDA)
REPO_URL = "github.com/MAUK9086/swarm-lineage"


def crops() -> dict[str, Path]:
    """Cut single panels (without their panel titles) out of the report figures.

    Returns:
        Name -> image path.
    """
    ASSETS.mkdir(parents=True, exist_ok=True)
    out = {}
    im = Image.open(FIG / "R2_naive_vs_cluster.png")
    w, h = im.size
    for name, (a, b) in {"R2A": (0, 606), "R2B": (606, 1412), "R2C": (1412, w)}.items():
        out[name] = ASSETS / f"{name}.png"
        im.crop((a, 62, b, h)).save(out[name])
    im = Image.open(FIG / "R4_leak_monitor.png")
    out["R4A"] = ASSETS / "R4A.png"
    im.crop((0, 72, 880, im.size[1])).save(out["R4A"])
    return out


def _run(p, text: str, size: float, color: RGBColor, bold: bool = False, font: str = BODY, italic: bool = False) -> None:
    r = p.add_run()
    r.text = text
    f = r.font
    f.size, f.bold, f.italic, f.name = Pt(size), bold, italic, font
    f.color.rgb = color


def textbox(slide, x: float, y: float, w: float, h: float, paras: list, anchor=MSO_ANCHOR.TOP, name: str = "text"):
    """Text box with one paragraph per item: (text, size, color, bold[, font[, italic]]) or a list of such runs.

    Returns:
        The shape.
    """
    sh = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    sh.name = name
    tf = sh.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for m in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, m, 0)
    for k, item in enumerate(paras):
        p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
        runs = item if isinstance(item, list) else [item]
        for r in runs:
            _run(p, r[0], r[1], r[2], r[3] if len(r) > 3 else False, r[4] if len(r) > 4 else BODY, r[5] if len(r) > 5 else False)
        p.space_after = Pt(runs[0][1] * 0.55)
    return sh


def bullets(slide, x: float, y: float, w: float, h: float, items: list[str], size: float = 17, color: RGBColor = INK, name: str = "list"):
    """Bulleted list (real bullets, one paragraph per item).

    Returns:
        The shape.
    """
    sh = textbox(slide, x, y, w, h, [(t, size, color) for t in items], name=name)
    for p in sh.text_frame.paragraphs:
        pPr = p._p.get_or_add_pPr()
        pPr.set("marL", str(int(Inches(0.28))))
        pPr.set("indent", str(-int(Inches(0.28))))
        bu = pPr.makeelement(qn("a:buChar"), {"char": "•"})
        pPr.append(bu)
        p.space_after = Pt(10)
    return sh


def title(slide, text: str, dark: bool = False) -> None:
    textbox(slide, 0.6, 0.42, 12.1, 0.9, [(text, 32, ON_DARK if dark else INK, True, HEAD)], anchor=MSO_ANCHOR.BOTTOM, name="title")


def kicker(slide, text: str, dark: bool = False) -> None:
    """Small label above the title saying where the slide sits in the story."""
    textbox(slide, 0.6, 0.38, 12.1, 0.3, [(text.upper(), 12, ON_DARK2 if dark else BLUE, True)], name="story label")


def bridge(slide, text: str, dark: bool = False) -> None:
    """One line at the foot of the slide that leads into the next one."""
    textbox(slide, 0.6, 6.72, 11.3, 0.4, [(text, 14, ON_DARK2 if dark else MUTED, False, BODY, True)], name="bridge")


def number(slide, k: int, dark: bool = False) -> None:
    sh = textbox(slide, 12.2, 7.0, 0.55, 0.3, [(str(k), 11, ON_DARK2 if dark else MUTED)], name="slide number")
    sh.text_frame.paragraphs[0].alignment = PP_ALIGN.RIGHT


def image(slide, path: Path, x: float, y: float, w: float | None = None, h: float | None = None, name: str = "figure"):
    """Picture scaled to a width or height, keeping its aspect ratio."""
    kw = {}
    if w is not None:
        kw["width"] = Inches(w)
    if h is not None:
        kw["height"] = Inches(h)
    pic = slide.shapes.add_picture(str(path), Inches(x), Inches(y), **kw)
    pic.name = name
    return pic


def dark_bg(slide) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = DARK


def notes(slide, text: str) -> None:
    slide.notes_slide.notes_text_frame.text = text


def s_title(prs, a: dict[str, Path]) -> None:
    s = prs.slides.add_slide(prs.slide_layouts[6])
    textbox(s, 0.6, 0.55, 7.0, 0.3, [("APART RESEARCH  \u00b7  SWARM ALIGNMENT SPRINT  \u00b7  NOVEMBER 2026", 12, BLUE, True)], name="venue")
    textbox(s, 0.6, 1.3, 7.6, 1.9, [("Counting Clusters, Not Pairs", 40, INK, True, HEAD)], anchor=MSO_ANCHOR.BOTTOM, name="title")
    textbox(s, 0.6, 3.3, 7.6, 0.9, [("Evaluating content-only forensics on agent-swarm text", 20, MUTED, False, HEAD)], name="subtitle")
    textbox(s, 0.6, 4.35, 6.8, 1.0, [("On agent text, copy-direction tools are easy to overrate: the cues add nothing beyond length, "
                                      "and pair-level scoring flatters them.", 16, INK)], name="claim")
    textbox(s, 0.6, 5.75, 7.0, 1.1, [("Mohammad Ahmadullah Khan", 18, INK, True),
                                     ("Independent researcher  \u00b7  Track 4: Multi-Agent Oversight and Control", 14, MUTED),
                                     (REPO_URL, 14, MUTED)], name="byline")
    image(s, a["R2B"], 8.55, 1.6, h=4.0, name="key result")
    textbox(s, 8.55, 5.7, 4.2, 0.8, [("The same data, scored per pair (orange) and per cluster (blue).", 12, MUTED)], name="key result caption")
    notes(s, "This project asks whether the text that agents copy from each other can tell us which copy came first, "
             "and how we should evaluate any tool that claims to do that. The chart on the right is the whole talk in one picture: "
             "the same data gives 0.70 when every pair is counted and chance when each cluster counts once.")


def s_problem(prs, k: int) -> None:
    s = prs.slides.add_slide(prs.slide_layouts[6])
    kicker(s, "The problem")
    title(s, "Agent swarms leave text, not clocks")
    textbox(s, 0.6, 1.75, 6.6, 4.6, [
        ("About 1,200 agents coordinated on a message board before roughly 700 of them attacked Hugging Face. Another swarm used a public wiki as its message board for weeks.", 18, INK),
        ("What investigators are left with is text that agents copied and edited from one another, mostly without reliable timestamps.", 18, INK),
        ("The forensic question: from content alone, which copy came first, and who copied whom?", 18, INK, True)],
        name="problem text")
    st = textbox(s, 8.0, 2.0, 4.7, 3.2, [("0", 96, ORANGE, True, HEAD),
                                         ("timestamps in the 189,579 rows of the public Swarm Traces release from the Hugging Face incident", 16, MUTED)],
                 name="no clocks stat")
    st.text_frame.paragraphs[0].space_after = Pt(0)
    bridge(s, "Next: how we tested whether content can answer that, without letting the method see the clock.")
    number(s, k)
    notes(s, "Recent incidents were reconstructed from traces rather than observed: METR and Redwood Research describe about 1,200 agents "
             "coordinating before roughly 700 attacked Hugging Face, and the collusion.wiki team found a swarm using a public wiki as a "
             "message board. The evidence is text that agents copied from each other, often without timestamps. So the natural forensic "
             "question is whether content alone can order the copies.")


def s_setup(prs, k: int) -> None:
    s = prs.slides.add_slide(prs.slide_layouts[6])
    kicker(s, "Our setup")
    title(s, "We hid the clock from every method")
    image(s, FIG / "R1_pipeline.png", 1.9, 1.7, w=9.5, name="pipeline figure")
    textbox(s, 1.9, 5.8, 9.5, 0.8, [("Developed on 300,000 Moltbook posts; the frozen rules were then run on the collusion.wiki export. "
                                     "Every analysis had a go/no-go rule written before it ran.", 16, INK)], name="setup text")
    bridge(s, "Before testing any cue, we counted how much independent evidence there actually is.")
    number(s, k)
    notes(s, "Every corpus goes through an adapter into one table. The method side sees text, group and author only; true time is split "
             "off and read only by the scoring code. Rows are shuffled first. Moltbook was the development corpus, collusion.wiki the "
             "held-out one, and every rule was written down before the run.")


def s_concentration(prs, a: dict[str, Path], k: int) -> None:
    s = prs.slides.add_slide(prs.slide_layouts[6])
    kicker(s, "Finding 1: the evidence")
    title(s, "Two clusters hold 98% of the evidence")
    bridge(s, "If almost every pair comes from two clusters, what happens when pairs are scored as if independent?")
    stats = [("8.4M", "near-duplicate pairs in the Moltbook sample", INK),
             ("1,198", "clusters (connected groups of near-duplicates)", INK),
             ("98.4%", "of all pairs sit in the two largest clusters", ORANGE)]
    for i, (big, small, col) in enumerate(stats):
        sh = textbox(s, 0.6, 1.85 + 1.6 * i, 5.4, 1.4, [(big, 44, col, True, HEAD), (small, 16, MUTED)], name=f"stat {i + 1}")
        sh.text_frame.paragraphs[0].space_after = Pt(2)
    image(s, a["R2A"], 7.4, 1.6, h=4.85, name="pair share figure")
    number(s, k)
    notes(s, "A family of n near-identical texts produces about n squared over two pairs. On Moltbook, two template families supply "
             "almost every pair. The median cluster has a single pair. So any average over pairs is in practice an average over two clusters.")


def s_inflation(prs, a: dict[str, Path], k: int) -> None:
    s = prs.slides.add_slide(prs.slide_layouts[6])
    kicker(s, "Finding 2: the evaluation trap")
    title(s, "Counting pairs turns chance into 0.70")
    bridge(s, "Scored the honest way, one cluster at a time: does any cue beat simply comparing lengths?")
    textbox(s, 0.6, 1.6, 5.9, 0.5, [("Same data, two answers", 18, INK, True)], name="left heading")
    image(s, a["R2B"], 1.05, 2.15, h=3.8, name="inflation figure")
    textbox(s, 0.6, 6.0, 5.9, 0.7, [("Keep every pair and \"longer is later\" jumps from 0.50 to 0.70; count each cluster once and it stays at chance.", 14, MUTED)], name="left caption")
    textbox(s, 6.9, 1.6, 5.9, 0.5, [("False alarms when there is no real order", 18, INK, True)], name="right heading")
    image(s, a["R2C"], 7.3, 2.15, h=3.8, name="null figure")
    textbox(s, 6.9, 6.0, 5.9, 0.7, [("Shuffle true times within clusters: pair-level tests call 86% of draws significant, cluster-level tests 5%.", 14, MUTED)], name="right caption")
    number(s, k)
    notes(s, "Left: as we allow more pairs per cluster, pair-level accuracy stays at chance until every pair is kept, then jumps to 0.70, "
             "with an interval 81 times narrower. Right: we shuffled the true times inside each cluster, which keeps the clusters and removes "
             "any real order. A pair-pooled test still reported a significant effect in 86% of 1,000 draws; the cluster bootstrap in 5%. Pair-level benchmarks are standard for text reuse and code-clone detection, and shared duplicates are known to inflate results in language modelling and authorship verification; on agent text the effect is extreme.")


def s_cues(prs, k: int) -> None:
    s = prs.slides.add_slide(prs.slide_layouts[6])
    kicker(s, "Finding 3: what content tells")
    title(s, "No cue beats \"the longer text is later\"")
    bridge(s, "But time order is not provenance. Where true parents are recorded, do the trees find them?")
    image(s, FIG / "R3_forest.png", 0.6, 1.55, w=8.6, name="forest figure")
    textbox(s, 9.6, 1.75, 3.2, 5.0, [
        ("Containment and insertion-versus-deletion are length comparisons in disguise.", 16, INK),
        ("Length itself is right for 0.66 of clusters across wiki pages (0.94 within pages, which grow by successive saves).", 16, INK),
        ("On Moltbook length shows no stable gain (0.495 to 0.565 over five pair samples).", 16, INK),
        ("Lineage trees order texts, but less well than length.", 16, INK)], name="takeaways")
    number(s, k)
    notes(s, "Each row is a corpus and scope, scored per cluster. Blue is length; grey markers are the other cues, which sit on top of it. "
             "Algebraically, shingle containment is the shingle-count rule and insertion minus deletion is the word-count rule. "
             "No cue beat length by the pre-registered five-point margin anywhere. The shaded row, wiki pages copied across pages, is closest to agents copying each other.")


def s_parents(prs, k: int) -> None:
    s = prs.slides.add_slide(prs.slide_layouts[6])
    kicker(s, "Ground-truth check")
    title(s, "Against true parents, the tree adds nothing over length")
    bridge(s, "Our own method once seemed to beat length. It did not, and how it fooled us matters.")
    textbox(s, 0.6, 1.75, 4.9, 4.9, [
        ("Time order is not provenance. The wiki records which revision each edit started from, so we scored the trees against those true parent links.", 17, INK),
        ("Trees recover 76% of true links per cluster (69% pooled), far above a random tree.", 17, INK),
        ("A one-line rule, \"parent = most similar shorter text\", does as well, and length orients the links the tree finds better than tree depth (0.96 vs 0.92).", 17, INK)],
        name="parents text")
    rows = [("Predicted parent", "Recall", "F1", "Orientation"),
            ("Spanning tree (depth)", "0.76", "0.70", "0.92"),
            ("Most similar shorter text", "0.74", "0.70", "0.98"),
            ("Random spanning tree", "0.34", "0.31", "0.46")]
    tb = s.shapes.add_table(len(rows), 4, Inches(6.0), Inches(2.1), Inches(6.7), Inches(2.4)).table
    widths = (2.9, 1.1, 1.1, 1.6)
    for j, wd in enumerate(widths):
        tb.columns[j].width = Inches(wd)
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            c = tb.cell(i, j)
            c.fill.solid()
            c.fill.fore_color.rgb = RGBColor(0xEE, 0xF4, 0xFC) if i == 0 else RGBColor(0xFF, 0xFF, 0xFF)
            tf = c.text_frame
            tf.paragraphs[0].text = ""
            _run(tf.paragraphs[0], v, 16, INK, bold=(i == 0 or (i == 2 and j == 3)))
            tf.paragraphs[0].alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
    textbox(s, 6.0, 4.75, 6.7, 1.2, [("collusion.wiki, 3,590 recorded links inside scored clusters; mean over 357 clusters. "
                                      "Orientation: share of recovered links pointing from parent to child. Stable over six input orders.", 12, MUTED)],
            name="table caption")
    number(s, k)
    notes(s, "This test answers the objection that timestamps are only a proxy for who copied whom. Within wiki pages we know the true parent of each revision. "
             "The spanning tree does find the right neighbours, F1 0.70 against 0.31 for a random tree on the same similarity graph. "
             "But choosing the most similar shorter text gives the same F1, and length orients the edges better. The tree adds nothing measurable.")


def s_leak(prs, a: dict[str, Path], k: int) -> None:
    s = prs.slides.add_slide(prs.slide_layouts[6])
    kicker(s, "A trap we fell into")
    title(s, "Our own positive result was a row-order leak")
    bridge(s, "So we tried to break our own conclusions.")
    image(s, FIG / "A1_trees_stored_order.png", 0.6, 1.55, w=6.1, name="stored-order trees")
    textbox(s, 0.6, 5.85, 6.6, 0.6, [("Largest Moltbook trees with rows in stored order; colour is true time. Leaves line up from early to late.", 12, MUTED)], name="trees caption")
    image(s, a["R4A"], 8.3, 1.6, h=3.1, name="leak figure")
    textbox(s, 7.7, 4.95, 5.0, 1.9, [
        ("Stored order: depth tau 0.098 beat length 0.057, and the run passed its pre-registered rule.", 15, INK),
        ("Shuffle the rows and change nothing else: depth 0.033, below length 0.050. We withdrew the result.", 15, INK)], name="leak text")
    number(s, k)
    notes(s, "The method never read time. But the stored table was sampled from files sorted by collection date, and tied similarity weights "
             "were broken by row index, so the row order carried time into the trees. A seeded shuffle removed the effect. "
             "Both frozen pipelines now shuffle rows first. This is a failure of our implementation, and it passed a pre-registered test.")


def s_robust(prs, k: int) -> None:
    s = prs.slides.add_slide(prs.slide_layouts[6])
    kicker(s, "Robustness")
    title(s, "What held up, and what did not")
    bridge(s, "What this means for anyone building or judging swarm-forensic tools:")
    textbox(s, 0.6, 1.7, 5.9, 0.5, [("Held", 20, BLUE, True, HEAD)], name="held heading")
    bullets(s, 0.6, 2.3, 5.9, 4.4, [
        "Stricter similarity thresholds (Jaccard 0.6 to 0.8): same conclusions",
        "Clusters that share an author merged into 113 units: same conclusions",
        "64-bit exact similarity: 0 of 8.36M pair similarities changed",
        "Parent recovery on the wiki: stable over six input orders"], name="held list")
    textbox(s, 6.9, 1.7, 5.9, 0.5, [("Did not hold, or limits", 20, ORANGE, True, HEAD)], name="limits heading")
    bullets(s, 6.9, 2.3, 5.9, 4.4, [
        "Moltbook tree structure depends on input order: about 22% of edges shared; 1 of 18 runs passed the rule",
        "Candidate search finds 49% of truly similar pairs at Jaccard 0.5 to 0.6 (91% or more above 0.6)",
        "Moltbook length moved 7 points across five pair samples",
        "The held-out wiki was profiled first, so it was not fully blind"], name="limits list")
    number(s, k)
    notes(s, "Every check here was registered before it ran. The negative result survives the cluster-definition and hashing checks. "
             "Two findings weaken the method itself: lineage trees on Moltbook change with input order through tied weights and subsampling, "
             "and the candidate search misses about half of the pairs just above the similarity threshold, where the stricter thresholds agree with our conclusions.")


def s_close(prs, k: int) -> None:
    s = prs.slides.add_slide(prs.slide_layouts[6])
    kicker(s, "Takeaway")
    title(s, "Evaluate swarm forensics per cluster")
    items = ["Report clusters next to pairs, and score each cluster once",
             "Check significance against a null that keeps clusters fixed",
             "Shuffle inputs, re-run under several orders, hide fields that reveal order",
             "Separate growth within a page or thread from copying across them",
             "Test provenance against recorded parents where they exist"]
    paras = [[(f"{i + 1}   ", 18, BLUE, True), (t, 18, INK)] for i, t in enumerate(items)]
    textbox(s, 0.6, 1.8, 7.6, 3.9, paras, name="checklist")
    textbox(s, 8.9, 1.9, 3.8, 3.6, [("What we found", 16, INK, True, HEAD),
                                    ("No content cue beat text length.", 15, INK),
                                    ("Trees find true parents, but length orients them better.", 15, INK),
                                    ("Pair-level scoring turned chance into 0.70 and 86% false alarms.", 15, INK)], name="summary")
    textbox(s, 0.6, 5.85, 11.9, 0.9, [("Paper, code, tests, pre-registration log and the full checklist", 14, MUTED),
                                      (REPO_URL, 18, INK, True)], name="links")
    number(s, k)
    notes(s, "Our recommendation for anyone building or judging swarm-forensic tools is short: count clusters, not pairs; calibrate with a "
             "cluster-preserving null; test for order leaks under several input orders; and use recorded provenance where it exists. "
             "Everything, including the failed experiments, is in the repository.")


def main() -> None:
    """Build the deck."""
    a = crops()
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    prs.core_properties.title = "Counting Clusters, Not Pairs"
    prs.core_properties.author = "Mohammad Ahmadullah Khan"
    s_title(prs, a)
    s_problem(prs, 2)
    s_setup(prs, 3)
    s_concentration(prs, a, 4)
    s_inflation(prs, a, 5)
    s_cues(prs, 6)
    s_parents(prs, 7)
    s_leak(prs, a, 8)
    s_robust(prs, 9)
    s_close(prs, 10)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
