"""Report figures, built only from results/*.json.

Outputs (figures/):
    R1_pipeline.png        method and evaluation schematic
    R2_naive_vs_cluster.png headline: inflation curve and null false-positive rates
    R3_forest.png          cluster-level estimates for every cue, corpus and scope
    R4_leak_monitor.png    row-order leak (lineage) and the metadata-monitor AUROC steps

File structure:
    Constants   palette, method labels
    load        read one results block
    style       shared axis styling
    fig_pipeline, fig_naive_vs_cluster, fig_forest, fig_leak_monitor
    main
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.io_utils import FIGURES_DIR, RESULTS_DIR  # noqa: E402

BLUE, ORANGE, AQUA, YELLOW, GREY = "#2a78d6", "#eb6834", "#1baf7a", "#c98500", "#8a8985"
SURFACE, TEXT, TEXT2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
METHODS = [("a_random", "random", GREY, "o"), ("b_longer_is_later", "longer is later", BLUE, "o"),
           ("c_containment", "containment", ORANGE, "s"), ("i_extension", "extension", AQUA, "^"),
           ("ii_insertion_vs_deletion", "insertion vs deletion", YELLOW, "D")]
plt.rcParams.update({"font.size": 8.5, "font.family": "DejaVu Sans"})


def load(name: str) -> dict[str, Any]:
    """Read the results block of results/<name>.json.

    Args:
        name: File stem.

    Returns:
        The 'results' dict ({} if missing).
    """
    p = RESULTS_DIR / f"{name}.json"
    return json.loads(p.read_text())["results"] if p.exists() else {}


def style(ax, grid_axis: str = "y") -> None:
    """Recessive axes: no top/right spines, light grid.

    Args:
        ax: Axes.
        grid_axis: 'x' or 'y'.
    """
    ax.set_facecolor(SURFACE)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=TEXT2)


def save(fig, name: str) -> None:
    """Save a figure to figures/<name>.

    Args:
        fig: Figure.
        name: File name.
    """
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES_DIR / name, dpi=200, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    print("figures/" + name)


def fig_pipeline() -> None:
    """Method and evaluation schematic."""
    fig, ax = plt.subplots(figsize=(7.2, 2.3), facecolor=SURFACE)
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.4, 3.2)
    ax.axis("off")
    boxes = [(0.05, "Adapter", "any corpus ->\nstandard table\n(doc, text, group,\nauthor | t)"),
             (2.05, "Pairs", "near-duplicates\nMinHash + LSH\nJaccard 0.5-0.95"),
             (4.05, "Clusters", "connected\ncomponents\n(the real unit\nof evidence)"),
             (6.05, "Predict order", "from text only:\nlength, contain-\nment, edit cues,\nlineage tree"),
             (8.05, "Score", "per cluster,\nthen average;\nnull: shuffle time\nwithin clusters")]
    for x, head, body in boxes:
        ax.add_patch(FancyBboxPatch((x, 0.75), 1.8, 1.95, boxstyle="round,pad=0.02,rounding_size=0.12",
                                    facecolor="#eef4fc" if head != "Score" else "#fdeee7", edgecolor=GRID))
        ax.text(x + 0.9, 2.42, head, ha="center", va="center", fontsize=9, fontweight="bold", color=TEXT)
        ax.text(x + 0.9, 1.55, body, ha="center", va="center", fontsize=7.4, color=TEXT2, linespacing=1.25)
    for x in (1.87, 3.87, 5.87, 7.87):
        ax.annotate("", xy=(x + 0.17, 1.72), xytext=(x, 1.72), arrowprops=dict(arrowstyle="-|>", color=TEXT2, lw=1))
    ax.annotate("", xy=(8.95, 0.72), xytext=(0.95, 0.72),
                arrowprops=dict(arrowstyle="-|>", color=ORANGE, lw=1.2, linestyle=(0, (3, 2)),
                                connectionstyle="arc3,rad=0.12"))
    ax.text(4.95, -0.33, "true time t bypasses the method: only the scoring step (src/evaluate.py) reads it",
            ha="center", fontsize=7.4, color=ORANGE)
    save(fig, "R1_pipeline.png")


def fig_naive_vs_cluster() -> None:
    """Headline: E34 inflation curve (left) and null false-positive rates (right)."""
    e34, e35 = load("E34_inflation_curve"), load("E35_null_simulation")
    l_m, l_c = load("E41v2_lineage_moltbook"), load("E41v2_lineage_collusion_wiki")
    rows = e34["grid"]["0.5-0.95"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.4, 3.0), facecolor=SURFACE, gridspec_kw={"width_ratios": [1.15, 1]})
    x = np.arange(len(rows))
    for key, lab, col, off in (("pair_level", "every pair counted", ORANGE, -0.07),
                               ("component_level", "each cluster counted once", BLUE, 0.07)):
        est = np.array([r[key]["accuracy" if key == "pair_level" else "macro"] for r in rows])
        lo = np.array([r[key]["ci"][0] for r in rows])
        hi = np.array([r[key]["ci"][1] for r in rows])
        a.errorbar(x + off, est, yerr=[est - lo, hi - est], color=col, marker="o", ms=6, lw=2, elinewidth=1.4,
                   mec=SURFACE, mew=1.2, label=lab)
    a.axhline(0.5, color=TEXT2, lw=0.8, ls=(0, (3, 3)))
    a.text(-0.35, 0.508, "chance", fontsize=7, color=TEXT2)
    a.set_xticks(x, ["1", "5", "20", "100", "all"])
    a.set_xlabel("pairs kept per cluster", color=TEXT2)
    a.set_ylabel('"longer post is later" accuracy', color=TEXT2)
    a.set_ylim(0.42, 0.75)
    a.set_title(f"A. {rows[-1]['pairs']:,} pairs, but {rows[-1]['components']:,} clusters", loc="left", fontsize=9, color=TEXT)
    a.legend(handles=[Line2D([], [], color=ORANGE, marker="o", lw=2, label="every pair counted"),
                      Line2D([], [], color=BLUE, marker="o", lw=2, label="each cluster counted once")],
             frameon=False, fontsize=7.5, loc="upper left")
    style(a)
    groups = [("copy direction\n(Moltbook, E35)", e35["pair_level"]["false_positive_rate"], e35["component_level"]["false_positive_rate"]),
              ("lineage depth\n(Moltbook)", l_m["scopes"]["all"]["evaluation"]["depth"]["null"]["naive_fpr"],
               l_m["scopes"]["all"]["evaluation"]["depth"]["null"]["macro_fpr"]),
              ("lineage depth\n(collusion.wiki)", l_c["scopes"]["all"]["evaluation"]["depth"]["null"]["naive_fpr"],
               l_c["scopes"]["all"]["evaluation"]["depth"]["null"]["macro_fpr"])]
    gx = np.arange(len(groups))
    w = 0.36
    for k, (_, naive, macro) in enumerate(groups):
        b.bar(gx[k] - w / 2, 100 * naive, w * 0.94, color=ORANGE)
        b.bar(gx[k] + w / 2, 100 * macro, w * 0.94, color=BLUE)
        b.text(gx[k] - w / 2, 100 * naive + 2, f"{100*naive:.0f}%", ha="center", fontsize=7.5, color=TEXT)
        b.text(gx[k] + w / 2, 100 * macro + 2, f"{100*macro:.0f}%", ha="center", fontsize=7.5, color=TEXT)
    b.axhline(5, color=TEXT2, lw=0.8, ls=(0, (3, 3)))
    b.text(-0.42, 6.5, "5% expected", fontsize=7, color=TEXT2, ha="left")
    b.set_xticks(gx, [g[0] for g in groups], fontsize=7.5)
    b.set_ylim(0, 100)
    b.set_ylabel("'significant' under a null with\nno real order (% of 1,000 draws)", color=TEXT2)
    b.set_title("B. False alarms when nothing is there", loc="left", fontsize=9, color=TEXT)
    style(b)
    fig.tight_layout()
    save(fig, "R2_naive_vs_cluster.png")


def fig_forest() -> None:
    """Cluster-level estimates for every cue (left) and lineage tau (right)."""
    m, c = load("E36v2_replication_moltbook"), load("E36v2_replication_collusion_wiki")
    lm, lc = load("E41v2_lineage_moltbook"), load("E41v2_lineage_collusion_wiki")
    e42 = load("E42_pair_sample_sensitivity")
    scopes = [("all", "all pairs"), ("within_group", "same group"), ("cross_group", "across groups")]
    mol = ("all pairs", "same submolt", "across submolts")
    wik = ("all pairs", "same page", "across pages")
    rows = [(f"Moltbook: {mol[k]}", m["scopes"][sc]) for k, (sc, _) in enumerate(scopes)] + \
           [(f"collusion.wiki: {wik[k]}", c["scopes"][sc]) for k, (sc, _) in enumerate(scopes)]
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.4, 3.4), facecolor=SURFACE, gridspec_kw={"width_ratios": [1.45, 1]})
    ys = np.arange(len(rows))[::-1].astype(float)
    offs = np.linspace(-0.28, 0.28, len(METHODS))
    for (key, lab, col, mk), off in zip(METHODS, offs):
        for y, (_, s) in zip(ys, rows):
            r = s["component_level"]["methods"][key]
            a.errorbar(r["macro"], y + off, xerr=[[r["macro"] - r["ci_low"]], [r["ci_high"] - r["macro"]]], fmt=mk,
                       color=col, ms=4.2, elinewidth=1.1, mec=SURFACE, mew=0.6)
    if e42:
        vals = e42["across_seeds"]["b_longer_is_later"]["macro_per_seed"]
        a.plot([min(vals), max(vals)], [ys[0] + 0.45] * 2, color=BLUE, lw=3, alpha=0.35, solid_capstyle="round")
        a.text(max(vals) + 0.012, ys[0] + 0.45, f"length over {len(vals)} pair samples (E42)", fontsize=6.5, color=BLUE, va="center")
    a.axvline(0.5, color=TEXT2, lw=0.8, ls=(0, (3, 3)))
    a.set_yticks(ys, [r[0] for r in rows], fontsize=7.5)
    a.axhline(2.5, color=GRID, lw=0.8)
    a.set_xlabel("accuracy, each cluster counted once (95% CI)", color=TEXT2)
    a.set_xlim(0.3, 1.0)
    a.set_title("A. Which post came first?", loc="left", fontsize=9, color=TEXT)
    handles = [Line2D([], [], color=col, marker=mk, ls="", ms=5, label=lab) for _, lab, col, mk in METHODS]
    a.legend(handles=handles, frameon=False, fontsize=6.8, loc="lower right", ncol=1)
    style(a, "x")
    lrows = [(f"Moltbook: {lab}", lm["scopes"][sc]["evaluation"]) for sc, lab in scopes] + \
            [(f"collusion.wiki: {lab}", lc["scopes"][sc]["evaluation"]) for sc, lab in scopes]
    for (key, lab, col, mk, off) in (("depth", "lineage-tree depth", ORANGE, "s", 0.12), ("length", "length", BLUE, "o", -0.12)):
        for y, (_, ev) in zip(ys, lrows):
            r = ev[key]
            b.errorbar(r["macro_tau"], y + off, xerr=[[r["macro_tau"] - r["macro_ci"][0]], [r["macro_ci"][1] - r["macro_tau"]]],
                       fmt=mk, color=col, ms=4.5, elinewidth=1.1, mec=SURFACE, mew=0.6)
    b.axvline(0, color=TEXT2, lw=0.8, ls=(0, (3, 3)))
    b.axhline(2.5, color=GRID, lw=0.8)
    b.set_yticks(ys, [""] * len(ys))
    b.set_xlabel("Kendall tau with true time, per cluster (95% CI)", color=TEXT2)
    b.set_title("B. Does a lineage tree order them?", loc="left", fontsize=9, color=TEXT)
    b.legend(handles=[Line2D([], [], color=ORANGE, marker="s", ls="", ms=5, label="tree depth"),
                      Line2D([], [], color=BLUE, marker="o", ls="", ms=5, label="length")], frameon=False, fontsize=6.8, loc="lower right")
    style(b, "x")
    fig.tight_layout()
    save(fig, "R3_forest.png")


def fig_leak_monitor() -> None:
    """Row-order leak (left) and metadata-monitor AUROC steps (right)."""
    e41, e41b = load("E41_lineage_moltbook"), load("E41_lineage_moltbook_rowshuffled")
    t01 = load("T01_report_numbers")
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.4, 2.8), facecolor=SURFACE, gridspec_kw={"width_ratios": [0.8, 1.2]})
    for k, (lab, ev) in enumerate((("rows in stored\n(time-like) order", e41["evaluation"]), ("rows shuffled", e41b["evaluation"]))):
        for key, col, mk, off in (("depth", ORANGE, "s", -0.12), ("length", BLUE, "o", 0.12)):
            r = ev[key]
            a.errorbar(k + off, r["macro_tau"], yerr=[[r["macro_tau"] - r["macro_ci"][0]], [r["macro_ci"][1] - r["macro_tau"]]],
                       fmt=mk, color=col, ms=6, elinewidth=1.4, mec=SURFACE, mew=0.8)
    a.set_xticks([0, 1], ["rows in stored\n(time-like) order", "rows shuffled"], fontsize=7.5)
    a.set_xlim(-0.5, 1.5)
    a.axhline(0, color=TEXT2, lw=0.8, ls=(0, (3, 3)))
    a.set_ylabel("Kendall tau with true time", color=TEXT2)
    a.set_title("A. A leak through row order (E41)", loc="left", fontsize=9, color=TEXT)
    a.legend(handles=[Line2D([], [], color=ORANGE, marker="s", ls="", ms=5, label="tree depth"),
                      Line2D([], [], color=BLUE, marker="o", ls="", ms=5, label="length")], frameon=False, fontsize=7, loc="upper right")
    style(a)
    steps = t01["monitor"]["steps"]
    y = np.arange(len(steps))[::-1]
    for yy, s in zip(y, steps):
        col = ORANGE if yy >= len(steps) - 2 else BLUE
        if s["ci"]:
            b.errorbar(s["auroc"], yy, xerr=[[s["auroc"] - s["ci"][0]], [s["ci"][1] - s["auroc"]]], fmt="o", color=col, ms=6,
                       elinewidth=1.4, mec=SURFACE, mew=0.8)
        else:
            b.plot(s["auroc"], yy, "o", color=col, ms=6, mec=SURFACE, mew=0.8)
        b.text(s["auroc"] + 0.012, yy + 0.22, f"{s['auroc']:.2f}", fontsize=7.2, color=TEXT)
    b.set_yticks(y, [s["label"] for s in steps], fontsize=7.2)
    b.axvline(0.5, color=TEXT2, lw=0.8, ls=(0, (3, 3)))
    b.axvline(0.75, color=GRID, lw=1.0)
    b.text(0.755, y[0] + 0.55, "pre-registered bar 0.75", fontsize=6.3, color=TEXT2, va="bottom")
    b.set_xlim(0.4, 1.02)
    b.set_ylim(y[-1] - 0.5, y[0] + 1.1)
    b.set_xlabel("AUROC (95% CI where available)", color=TEXT2)
    b.set_title("B. Metadata monitor: the score shrinks with each control", loc="left", fontsize=9, color=TEXT)
    style(b, "x")
    fig.tight_layout()
    save(fig, "R4_leak_monitor.png")


def main() -> None:
    """Build all report figures."""
    fig_pipeline()
    fig_naive_vs_cluster()
    fig_forest()
    fig_leak_monitor()


if __name__ == "__main__":
    main()
