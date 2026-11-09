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
    fig.savefig(FIGURES_DIR / name, dpi=300, facecolor=SURFACE, bbox_inches="tight")
    fig.savefig(FIGURES_DIR / name.replace(".png", ".pdf"), facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)
    print("figures/" + name + " (+ .pdf)")


def fig_pipeline() -> None:
    """Two-lane schematic: the method lane never sees t; only the evaluator lane reads it."""
    fig, ax = plt.subplots(figsize=(7.2, 2.9), facecolor=SURFACE)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.05)
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((0.0, 1.78), 10.0, 2.22, boxstyle="round,pad=0,rounding_size=0.08",
                                facecolor="#f3f7fd", edgecolor="none"))
    ax.add_patch(FancyBboxPatch((0.0, 0.0), 10.0, 1.6, boxstyle="round,pad=0,rounding_size=0.08",
                                facecolor="#fdf3ee", edgecolor="none"))
    ax.text(0.08, 3.84, "A. Method: text only, never reads t", fontsize=8, fontweight="bold", color=BLUE, va="center")
    ax.text(1.2, 1.44, "B. Evaluator only (src/evaluate.py)", fontsize=8, fontweight="bold", color=ORANGE, va="center")
    top = [(0.08, "Adapter", "public table:\ndoc, text, group,\nauthor; rows\nshuffled"),
           (2.08, "Pairs", "near-duplicates\nMinHash + LSH\nJaccard 0.5-0.95"),
           (4.08, "Clusters", "connected\ncomponents: the\nunit of evidence"),
           (6.08, "Predict order", "length, contain-\nment, edit cues,\nlineage tree")]
    for x, head, body in top:
        ax.add_patch(FancyBboxPatch((x, 1.98), 1.72, 1.6, boxstyle="round,pad=0.02,rounding_size=0.1",
                                    facecolor="#ffffff", edgecolor=GRID))
        ax.text(x + 0.86, 3.32, head, ha="center", va="center", fontsize=8.5, fontweight="bold", color=TEXT)
        ax.text(x + 0.86, 2.55, body, ha="center", va="center", fontsize=7, color=TEXT2, linespacing=1.2)
    for x in (1.84, 3.84, 5.84):
        ax.annotate("", xy=(x + 0.22, 2.78), xytext=(x, 2.78), arrowprops=dict(arrowstyle="-|>", color=TEXT2, lw=1))
    bottom = [(0.08, "Hidden time t", "split off by the\nadapter; not\npassed on"),
              (8.08, "Score", "per cluster, then\naverage; null:\nshuffle t in clusters")]
    for x, head, body in bottom:
        ax.add_patch(FancyBboxPatch((x, 0.12), 1.72, 1.12, boxstyle="round,pad=0.02,rounding_size=0.1",
                                    facecolor="#ffffff", edgecolor=GRID))
        ax.text(x + 0.86, 1.0, head, ha="center", va="center", fontsize=8.5, fontweight="bold", color=TEXT)
        ax.text(x + 0.86, 0.5, body, ha="center", va="center", fontsize=7, color=TEXT2, linespacing=1.2)
    ax.annotate("", xy=(0.94, 1.27), xytext=(0.94, 1.96), arrowprops=dict(arrowstyle="-|>", color=ORANGE, lw=1.1))
    ax.annotate("", xy=(8.06, 0.62), xytext=(1.84, 0.62),
                arrowprops=dict(arrowstyle="-|>", color=ORANGE, lw=1.2, linestyle=(0, (3, 2))))
    ax.text(4.95, 0.74, "t goes only to scoring", ha="center", fontsize=7, color=ORANGE)
    ax.annotate("", xy=(8.6, 1.27), xytext=(7.82, 2.6),
                arrowprops=dict(arrowstyle="-|>", color=TEXT2, lw=1, connectionstyle="arc3,rad=-0.25"))
    ax.text(9.1, 2.35, "predicted order\n+ cluster ids", ha="center", fontsize=7, color=TEXT2, va="center")
    save(fig, "R1_pipeline.png")


def fig_naive_vs_cluster() -> None:
    """Headline: E34 inflation curve (left) and null false-positive rates (right)."""
    e34, e35 = load("E34_inflation_curve"), load("E35_null_simulation")
    l_m, l_c = load("E41v2_lineage_moltbook"), load("E41v2_lineage_collusion_wiki")
    rows = e34["grid"]["0.5-0.95"]
    t02 = load("T02_cluster_concentration")
    fig, (c0, a, b) = plt.subplots(1, 3, figsize=(7.6, 2.9), facecolor=SURFACE, gridspec_kw={"width_ratios": [0.62, 1.05, 1]})
    s1 = t02["share_of_pairs_in_largest"]["1"]
    s2 = t02["share_of_pairs_in_largest"]["2"]
    shares = [100 * s1, 100 * (s2 - s1), 100 * (1 - s2)]
    labs = ["largest\ncluster", "2nd\nlargest", f"other\n{t02['clusters'] - 2:,}"]
    c0.bar(range(3), shares, 0.66, color=[ORANGE, ORANGE, BLUE])
    for k, v in enumerate(shares):
        c0.text(k, v + 2, f"{v:.1f}%", ha="center", fontsize=7.5, color=TEXT)
    c0.set_xticks(range(3), labs, fontsize=7.2)
    c0.set_ylim(0, 100)
    c0.set_ylabel(f"share of all {t02['pairs']/1e6:.1f}M pairs (%)", color=TEXT2)
    c0.set_title("A. Where the pairs are", loc="left", fontsize=9, color=TEXT)
    style(c0)
    x = np.arange(len(rows))
    for key, lab, col, off in (("pair_level", "every pair counted", ORANGE, -0.07),
                               ("component_level", "each cluster counted once", BLUE, 0.07)):
        est = np.array([r[key]["accuracy" if key == "pair_level" else "macro"] for r in rows])
        lo = np.array([r[key]["ci"][0] for r in rows])
        hi = np.array([r[key]["ci"][1] for r in rows])
        a.errorbar(x + off, est, yerr=[est - lo, hi - est], color=col, marker="o", ms=6, lw=2, elinewidth=1.4,
                   mec=SURFACE, mew=1.2, label=lab)
    a.axhline(0.5, color=TEXT2, lw=0.8, ls=(0, (3, 3)))
    a.set_xticks(x, ["1", "5", "20", "100", "all"])
    a.set_xlabel("maximum pairs kept per cluster", color=TEXT2)
    a.set_ylabel('"longer is later" accuracy', color=TEXT2)
    a.set_ylim(0.42, 0.75)
    a.set_title("B. Same data, two answers", loc="left", fontsize=9, color=TEXT)
    a.legend(handles=[Line2D([], [], color=ORANGE, marker="o", lw=2, label="every pair counted"),
                      Line2D([], [], color=BLUE, marker="o", lw=2, label="each cluster counted once")],
             frameon=False, fontsize=7.5, loc="upper left")
    style(a)
    groups = [("copy\ndirection", e35["pair_level"]["false_positive_rate"], e35["component_level"]["false_positive_rate"]),
              ("lineage\n(Moltbook)", l_m["scopes"]["all"]["evaluation"]["depth"]["null"]["naive_fpr"],
               l_m["scopes"]["all"]["evaluation"]["depth"]["null"]["macro_fpr"]),
              ("lineage\n(wiki)", l_c["scopes"]["all"]["evaluation"]["depth"]["null"]["naive_fpr"],
               l_c["scopes"]["all"]["evaluation"]["depth"]["null"]["macro_fpr"])]
    gx = np.arange(len(groups))
    w = 0.36
    for k, (_, naive, macro) in enumerate(groups):
        b.bar(gx[k] - w / 2, 100 * naive, w * 0.94, color=ORANGE)
        b.bar(gx[k] + w / 2, 100 * macro, w * 0.94, color=BLUE)
        b.text(gx[k] - w / 2, 100 * naive + 2, f"{100*naive:.0f}%", ha="center", fontsize=7.5, color=TEXT)
        b.text(gx[k] + w / 2, 100 * macro + 2, f"{100*macro:.0f}%", ha="center", fontsize=7.5, color=TEXT)
    b.axhline(5, color=TEXT2, lw=0.8, ls=(0, (3, 3)))
    b.set_xticks(gx, [g[0] for g in groups], fontsize=7.5)
    b.set_ylim(0, 128)
    b.set_yticks([0, 25, 50, 75, 100])
    b.set_ylabel("% of 1,000 null draws\ncalled significant", color=TEXT2)
    b.set_title("C. False alarms under a null", loc="left", fontsize=9, color=TEXT)
    b.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=ORANGE, label="pair-pooled Wald CI"),
                      plt.Rectangle((0, 0), 1, 1, color=BLUE, label="cluster bootstrap CI")],
             frameon=False, fontsize=7, loc="upper right")
    style(b)
    fig.tight_layout()
    save(fig, "R2_naive_vs_cluster.png")


def fig_forest() -> None:
    """Cluster-level estimates: length vs the other cues (left), tree depth vs length (right)."""
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
    for ax in (a, b):
        ax.axhspan(ys[-1] - 0.45, ys[-1] + 0.45, color="#fbe9df", zorder=0)
    others = [("c_containment", "s"), ("i_extension", "^"), ("ii_insertion_vs_deletion", "D")]
    for (key, mk), off in zip(others, (-0.22, -0.11, 0.0)):
        for y, (_, s) in zip(ys, rows):
            r = s["component_level"]["methods"][key]
            a.errorbar(r["macro"], y + off, xerr=[[r["macro"] - r["ci_low"]], [r["ci_high"] - r["macro"]]], fmt=mk,
                       color="#a9a8a3", ms=3.2, elinewidth=0.8, mec=SURFACE, mew=0.4, zorder=2)
    for y, (_, s) in zip(ys, rows):
        r = s["component_level"]["methods"]["a_random"]
        a.plot(r["macro"], y - 0.33, "|", color="#c9c8c3", ms=6, zorder=2)
        r = s["component_level"]["methods"]["b_longer_is_later"]
        a.errorbar(r["macro"], y + 0.18, xerr=[[r["macro"] - r["ci_low"]], [r["ci_high"] - r["macro"]]], fmt="o",
                   color=BLUE, ms=5.5, elinewidth=1.6, mec=SURFACE, mew=0.7, zorder=3)
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
    handles = [Line2D([], [], color=BLUE, marker="o", ls="", ms=5.5, label="length (longer is later)"),
               Line2D([], [], color="#a9a8a3", marker="s", ls="", ms=3.5,
                      label="containment, extension,\ninsertion vs deletion"),
               Line2D([], [], color="#c9c8c3", marker="|", ls="", ms=6, label="random")]
    a.legend(handles=handles, frameon=False, fontsize=6.6, loc="upper right", bbox_to_anchor=(1.0, 0.9), ncol=1)
    style(a, "x")
    lrows = [(f"Moltbook: {lab}", lm["scopes"][sc]["evaluation"]) for sc, lab in scopes] + \
            [(f"collusion.wiki: {lab}", lc["scopes"][sc]["evaluation"]) for sc, lab in scopes]
    for (key, col, mk, off) in (("depth", ORANGE, "s", 0.12), ("length", BLUE, "o", -0.12)):
        for y, (_, ev) in zip(ys, lrows):
            r = ev[key]
            b.errorbar(r["macro_tau"], y + off, xerr=[[r["macro_tau"] - r["macro_ci"][0]], [r["macro_ci"][1] - r["macro_tau"]]],
                       fmt=mk, color=col, ms=4.5, elinewidth=1.1, mec=SURFACE, mew=0.6, zorder=3)
    b.axvline(0, color=TEXT2, lw=0.8, ls=(0, (3, 3)))
    b.axhline(2.5, color=GRID, lw=0.8)
    b.set_yticks(ys, [""] * len(ys))
    b.set_xlabel("Kendall tau with true time, per cluster (95% CI)", color=TEXT2)
    b.set_title("B. Does a lineage tree order them?", loc="left", fontsize=9, color=TEXT)
    b.legend(handles=[Line2D([], [], color=ORANGE, marker="s", ls="", ms=5, label="tree depth"),
                      Line2D([], [], color=BLUE, marker="o", ls="", ms=5, label="length")], frameon=False, fontsize=6.8,
             loc="upper right")
    style(b, "x")
    fig.tight_layout()
    save(fig, "R3_forest.png")


def fig_leak_monitor() -> None:
    """Row-order leak (left) and metadata-monitor AUROC steps (right)."""
    e41, e41b = load("E41_lineage_moltbook"), load("E41_lineage_moltbook_rowshuffled")
    t01 = load("T01_report_numbers")
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.4, 2.9), facecolor=SURFACE, gridspec_kw={"width_ratios": [1.0, 1.15]})
    for k, (lab, ev) in enumerate((("rows in stored\n(time-like) order", e41["evaluation"]), ("rows shuffled", e41b["evaluation"]))):
        for key, col, mk, off in (("depth", ORANGE, "s", -0.12), ("length", BLUE, "o", 0.12)):
            r = ev[key]
            a.errorbar(k + off, r["macro_tau"], yerr=[[r["macro_tau"] - r["macro_ci"][0]], [r["macro_ci"][1] - r["macro_tau"]]],
                       fmt=mk, color=col, ms=6, elinewidth=1.4, mec=SURFACE, mew=0.8)
    a.set_xticks([0, 1], ["rows in stored\n(time-like) order", "rows shuffled"], fontsize=7.5)
    a.set_xlim(-0.5, 1.5)
    a.axhline(0, color=TEXT2, lw=0.8, ls=(0, (3, 3)))
    a.set_ylabel("Kendall tau with true time", color=TEXT2)
    a.set_title("A. Row-order leak (E41): tau with true time", loc="left", fontsize=9, color=TEXT)
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
            b.text(s["auroc"] + 0.012, yy - 0.32, "no CI: one cluster holds most held-out authors",
                   fontsize=6.3, color=TEXT2, style="italic")
        b.text(s["auroc"] + 0.012, yy + 0.22, f"{s['auroc']:.2f}", fontsize=7.2, color=TEXT)
    b.set_yticks(y, [s["label"] for s in steps], fontsize=7.2)
    b.axvline(0.5, color=TEXT2, lw=0.8, ls=(0, (3, 3)))
    b.axvline(0.75, color=GRID, lw=1.0)
    b.text(0.755, y[0] + 0.55, "pre-registered bar 0.75", fontsize=6.3, color=TEXT2, va="bottom")
    b.set_xlim(0.4, 1.02)
    b.set_ylim(y[-1] - 0.5, y[0] + 1.1)
    b.set_xlabel("AUROC (95% CI where available)", color=TEXT2)
    b.set_title("B. Metadata monitor, fairer comparisons", loc="left", fontsize=9, color=TEXT)
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
