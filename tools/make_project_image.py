"""Project image (figures/project_image.png, 2400 x 1350 px) built from results/*.json.

Left: title and three headline numbers. Right: the E34 inflation curve redrawn from the saved
results (pair-level vs cluster-level accuracy of "longer is later" by pairs kept per cluster).

Usage:
    python tools/make_project_image.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
BLUE, ORANGE, INK, MUTED, GRID, BG = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#e4e3df", "#ffffff"


def font(name: str, fallback: str) -> str:
    """Use a system font if matplotlib can find it, else a fallback."""
    names = {f.name for f in font_manager.fontManager.ttflist}
    return name if name in names else fallback


def main() -> None:
    """Draw and save the image."""
    head, body = font("Cambria", "DejaVu Serif"), font("Calibri", "DejaVu Sans")
    res = lambda n: json.loads((REPO / "results" / f"{n}.json").read_text())["results"]
    rows = res("E34_inflation_curve")["grid"]["0.5-0.95"]
    t02, e35 = res("T02_cluster_concentration"), res("E35_null_simulation")
    share2 = 100 * t02["share_of_pairs_in_largest"]["2"]
    pairs_m = t02["pairs"] / 1e6
    p_fpr, c_fpr = 100 * e35["pair_level"]["false_positive_rate"], 100 * e35["component_level"]["false_positive_rate"]
    pair_all = rows[-1]["pair_level"]["accuracy"]

    fig = plt.figure(figsize=(12, 6.75), dpi=200, facecolor=BG)
    fig.text(0.05, 0.89, "APART RESEARCH  ·  SWARM ALIGNMENT SPRINT 2026  ·  TRACK 4", fontsize=11, color=BLUE,
             fontweight="bold", family=body)
    fig.text(0.05, 0.75, "Counting Clusters,\nNot Pairs", fontsize=40, color=INK, fontweight="bold", family=head,
             va="top", linespacing=1.05)
    fig.text(0.05, 0.52, "Evaluating content-only forensics on agent-swarm text", fontsize=15, color=MUTED, family=head)
    stats = [(f"{share2:.0f}%", f"of {pairs_m:.1f}M near-duplicate pairs sit in two clusters"),
             (f"0.50 → {pair_all:.2f}", "accuracy once every pair is counted"),
             (f"{p_fpr:.0f}% vs {c_fpr:.0f}%", "false alarms under a null: pairs vs clusters")]
    for k, (big, small) in enumerate(stats):
        y = 0.40 - 0.105 * k
        fig.text(0.05, y, big, fontsize=24, color=ORANGE if k == 0 else INK, fontweight="bold", family=head, va="center")
        fig.text(0.245, y, small, fontsize=13, color=MUTED, family=body, va="center")
    fig.text(0.05, 0.05, "Mohammad Ahmadullah Khan  ·  github.com/MAUK9086/swarm-lineage", fontsize=11, color=MUTED, family=body)

    ax = fig.add_axes([0.62, 0.20, 0.34, 0.60], facecolor=BG)
    x = np.arange(len(rows))
    for key, lab, col, off in (("pair_level", "every pair counted", ORANGE, -0.06),
                               ("component_level", "each cluster counted once", BLUE, 0.06)):
        est = np.array([r[key]["accuracy" if key == "pair_level" else "macro"] for r in rows])
        lo = np.array([r[key]["ci"][0] for r in rows])
        hi = np.array([r[key]["ci"][1] for r in rows])
        ax.errorbar(x + off, est, yerr=[est - lo, hi - est], color=col, marker="o", ms=8, lw=2.6, elinewidth=1.8,
                    mec=BG, mew=1.5, label=lab)
    ax.axhline(0.5, color=MUTED, lw=1, ls=(0, (3, 3)))
    ax.set_xticks(x, ["1", "5", "20", "100", "all"], fontsize=12, family=body)
    ax.tick_params(axis="y", labelsize=12, colors=MUTED)
    ax.tick_params(axis="x", colors=MUTED)
    ax.set_ylim(0.42, 0.75)
    ax.set_xlabel("maximum pairs kept per cluster", fontsize=12, color=MUTED, family=body)
    ax.set_ylabel('"longer is later" accuracy', fontsize=12, color=MUTED, family=body)
    ax.set_title("Same data, two answers", loc="left", fontsize=15, color=INK, family=head, fontweight="bold", pad=12)
    ax.legend(frameon=False, fontsize=12, loc="upper left", prop={"family": body, "size": 12})
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(GRID)
    out = REPO / "figures" / "project_image.png"
    fig.savefig(out, dpi=200, facecolor=BG)
    plt.close(fig)
    print(out)


if __name__ == "__main__":
    main()
