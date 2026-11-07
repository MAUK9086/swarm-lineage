"""FIG1 - Naive vs proper estimates for the dating task and the monitor task.

Built only from saved results: E34 (dating), E35 (null false-positive rates),
E37 (naive monitor) and E38 (proper monitor).

File structure:
    Constants   colours, result paths
    load        read one results file
    panel       draw one naive-vs-proper panel
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.io_utils import FIGURES_DIR, RESULTS_DIR  # noqa: E402

C_NAIVE, C_PROPER = "#eb6834", "#2a78d6"
C_SURFACE, C_TEXT, C_TEXT2, C_GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"


def load(name: str) -> dict[str, Any]:
    """Read results/<name>.json.

    Args:
        name: File stem.

    Returns:
        The 'results' block.
    """
    return json.loads((RESULTS_DIR / f"{name}.json").read_text())["results"]


def panel(ax, title: str, ylabel: str, items: list[tuple[str, str, float, list[float], str]], note: str) -> None:
    """Draw one panel of labelled point estimates with CIs.

    Args:
        ax: Matplotlib axes.
        title: Panel title.
        ylabel: Y-axis label.
        items: (label, sublabel, estimate, [lo, hi], colour) per point.
        note: Small text under the points.
    """
    ax.set_facecolor(C_SURFACE)
    ax.axhline(0.5, color=C_TEXT2, linewidth=0.8, linestyle=(0, (3, 3)))
    ax.text(1.45, 0.5, "chance", fontsize=7, color=C_TEXT2, va="bottom", ha="right")
    for x, (lab, sub, est, ci, col) in enumerate(items):
        ax.errorbar([x], [est], yerr=[[est - ci[0]], [ci[1] - est]], color=col, marker="o", markersize=9,
                    markeredgecolor=C_SURFACE, markeredgewidth=1.5, elinewidth=2, capsize=0)
        ax.text(x + 0.08, est, f"{est:.3f}\n[{ci[0]:.3f}, {ci[1]:.3f}]", fontsize=7.5, color=C_TEXT2, va="center")
    ax.set_xticks(range(len(items)), [f"{lab}\n{sub}" for lab, sub, *_ in items], fontsize=7.5, color=C_TEXT2)
    ax.set_xlim(-0.5, len(items) - 0.5 + 0.5)
    ax.set_ylim(0.3, 1.02)
    ax.set_ylabel(ylabel, color=C_TEXT2, fontsize=9)
    ax.set_title(title, loc="left", fontsize=10, color=C_TEXT)
    ax.tick_params(axis="y", colors=C_TEXT2, labelsize=8)
    ax.grid(axis="y", color=C_GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(C_GRID)
    ax.text(0.0, -0.32, note, transform=ax.transAxes, fontsize=7, color=C_TEXT2, va="top")


def main() -> None:
    """Build figures/FIG1_naive_vs_proper.png."""
    e34, e35, e37, e38 = load("E34_inflation_curve"), load("E35_null_simulation"), load("E37_metadata_monitor_pilot"), load("E38_monitor_matched")
    rows = {str(r["cap"]): r for r in e34["grid"]["0.5-0.95"]}
    naive_d, proper_d = rows["none"], rows["20"]
    m37, m38 = e37["metrics"]["gbt"], e38["feature_sets"]["a_full"]["pooled"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), facecolor=C_SURFACE)
    panel(axes[0], "Copy direction: \"longer post is later\"", "pairwise accuracy",
          [("Naive", f"pair-level, {naive_d['pairs']:,} pairs", naive_d["pair_level"]["accuracy"], naive_d["pair_level"]["ci"], C_NAIVE),
           ("Cluster-aware", f"component-level, {proper_d['components']:,} components",
            proper_d["component_level"]["macro"], proper_d["component_level"]["ci"], C_PROPER)],
          f"Known null (times permuted within clusters, {e35['draws']:,} draws): naive analysis 'significant' in "
          f"{100 * e35['pair_level']['false_positive_rate']:.1f}% of draws,\ncluster-aware in "
          f"{100 * e35['component_level']['false_positive_rate']:.1f}% (nominal 5%).")
    panel(axes[1], "Coordination monitor (metadata only)", "AUROC",
          [("Naive", "E37: unmatched activity, unbalanced split", m37["auroc"], m37["auroc_ci"], C_NAIVE),
           ("Cluster-aware", "E38: matched activity, grouped 5-fold CV", m38["auroc"], m38["auroc_ci"], C_PROPER)],
          f"Recall at 1% FPR: naive {m37['recall_at_1pct_fpr']:.2f}, cluster-aware {m38['recall_at_1pct_fpr']:.2f}.")
    fig.suptitle("Naive evaluation of clustered agent text overstates both results (95% CIs)",
                 x=0.01, ha="left", fontsize=11, color=C_TEXT)
    fig.tight_layout(rect=(0, 0.04, 1, 0.97))
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES_DIR / "FIG1_naive_vs_proper.png", dpi=150, facecolor=C_SURFACE)
    print("figures/FIG1_naive_vs_proper.png")


if __name__ == "__main__":
    main()
