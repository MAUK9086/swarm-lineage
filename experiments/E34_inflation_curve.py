"""E34 - Inflation curve: pair-level vs component-level scoring of "longer is later".

File structure:
    Constants     windows, caps, colours
    evaluate_grid pair-level and component-level estimates for one window and every cap
    plot_curve    headline figure, one panel per window
    main
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from tqdm import tqdm  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.clusters import cap_pairs, doc_codes, macro_bootstrap, union_find, wald_ci  # noqa: E402
from src.copydir import assert_public, predict_length, shingles  # noqa: E402
from src.evaluate import order_from_codes, split_truth, truth_codes  # noqa: E402
from src.io_utils import FIGURES_DIR, INTERIM_DIR, SEED, append_summary, save_result  # noqa: E402

WINDOWS = (0.5, 0.7, 0.9)
J_HI = 0.95
CAPS: tuple[int | None, ...] = (1, 5, 20, 100, None)
N_BOOT = 1000
C_PAIR, C_COMP = "#2a78d6", "#eb6834"
C_SURFACE, C_TEXT, C_TEXT2, C_GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"


def evaluate_grid(correct: np.ndarray, comp: np.ndarray) -> list[dict[str, Any]]:
    """Estimates for every cap on one set of pairs.

    Args:
        correct: 1.0 / 0.0 per pair (length rule vs truth).
        comp: Component id per pair.

    Returns:
        One dict per cap.
    """
    rows = []
    for k in CAPS:
        idx = cap_pairs(comp, k, seed=SEED)
        c, g = correct[idx], comp[idx]
        p = float(c.mean())
        pci = wald_ci(p, len(c))
        m = macro_bootstrap(c, g, n_boot=N_BOOT, seed=SEED)
        pw, cw = pci[1] - pci[0], m["ci_high"] - m["ci_low"]
        rows.append({"cap": "none" if k is None else k, "pairs": int(len(c)), "components": m["n_components"],
                     "pair_level": {"accuracy": p, "ci": pci},
                     "component_level": {"macro": m["macro"], "ci": [m["ci_low"], m["ci_high"]]},
                     "inflation_points": 100 * (p - m["macro"]), "ci_width_ratio_comp_over_pair": cw / pw})
    return rows


def plot_curve(windows: dict[str, list[dict[str, Any]]]) -> str:
    """Headline figure: estimate against cap, pair-level vs component-level, per window.

    Args:
        windows: Grid rows keyed by window label.

    Returns:
        Repo-relative figure path.
    """
    labels = [str(c) for c in ("1", "5", "20", "100", "none")]
    x = np.arange(len(labels))
    fig, axes = plt.subplots(1, len(windows), figsize=(11, 3.8), sharey=True, facecolor=C_SURFACE)
    for ax, (wlab, rows) in zip(axes, windows.items()):
        ax.set_facecolor(C_SURFACE)
        ax.axhline(0.5, color=C_TEXT2, linewidth=0.8, linestyle=(0, (3, 3)))
        for key, lab, col, off in (("pair_level", "pair-level", C_PAIR, -0.08), ("component_level", "component-level", C_COMP, 0.08)):
            est = np.array([r[key]["accuracy" if key == "pair_level" else "macro"] for r in rows])
            lo = np.array([r[key]["ci"][0] for r in rows])
            hi = np.array([r[key]["ci"][1] for r in rows])
            ax.errorbar(x + off, est, yerr=[est - lo, hi - est], color=col, linewidth=2, marker="o", markersize=7,
                        markeredgecolor=C_SURFACE, markeredgewidth=1.5, capsize=0, elinewidth=1.5, label=lab)
        ax.set_xticks(x, labels)
        ax.set_xlabel("pairs kept per component (cap)", color=C_TEXT2, fontsize=8)
        comps = rows[-1]["components"]
        ax.set_title(f"Jaccard {wlab}\n{rows[-1]['pairs']:,} pairs in {comps:,} components",
                     loc="left", fontsize=9, color=C_TEXT)
        ax.tick_params(colors=C_TEXT2, labelsize=8)
        ax.grid(axis="y", color=C_GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(C_GRID)
    axes[0].set_ylabel('"longer is later" accuracy', color=C_TEXT2)
    axes[0].set_ylim(0.3, 0.9)
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], color=C_PAIR, marker="o", linewidth=2, label="pair-level"),
               Line2D([], [], color=C_COMP, marker="o", linewidth=2, label="component-level")]
    axes[-1].legend(handles=handles, frameon=False, fontsize=8, loc="upper left")
    fig.suptitle("Pair-level scoring inflates the copy-direction estimate as more pairs per cluster are kept "
                 "(95% CIs; dashed line = chance)", x=0.01, ha="left", fontsize=10, color=C_TEXT)
    fig.tight_layout()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES_DIR / "E34_inflation_curve.png", dpi=150, facecolor=C_SURFACE)
    plt.close(fig)
    return "figures/E34_inflation_curve.png"


def main() -> None:
    """Run E34 and write results/E34_inflation_curve.json."""
    table = pd.read_parquet(INTERIM_DIR / "moltbook_slim.parquet")
    public, truth = split_truth(table)
    del table
    assert_public(public)
    pairs = pd.read_parquet(INTERIM_DIR / "E31_pairs.parquet")
    text_of = dict(zip(public["doc_id"], public["text"]))
    a, b, docs = doc_codes(pairs["doc_a"].to_numpy(), pairs["doc_b"].to_numpy())
    lens = np.array([len(text_of[d]) for d in docs])
    pred, ties = predict_length(lens[a], lens[b], seed=SEED)
    a_earlier, valid = order_from_codes(truth_codes(truth, docs), a, b)
    correct = (pred == a_earlier).astype(float)
    jac = pairs["jaccard"].to_numpy()

    res: dict[str, Any] = {"pairs_total": int(len(pairs)), "pairs_invalid_time": int((~valid).sum()),
                           "length_rule_ties": ties, "reproduces_E31_pair_accuracy": float(correct.mean())}
    rng = np.random.default_rng(SEED)
    boots = [correct[rng.integers(0, len(correct), len(correct))].mean() for _ in tqdm(range(200), desc="pair bootstrap check")]
    res["pair_bootstrap_check_full_none"] = {"ci": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
                                             "wald": wald_ci(float(correct.mean()), len(correct))}

    grid: dict[str, list[dict[str, Any]]] = {}
    for w in WINDOWS:
        sel = np.flatnonzero(jac >= w)
        comp = union_find(a[sel], b[sel])
        grid[f"{w}-{J_HI}"] = evaluate_grid(correct[sel], comp)
    res["grid"] = grid

    sizes = np.array([len(shingles(text_of[d])) for d in tqdm(docs, desc="shingle sizes", unit="doc")])
    comp_full = union_find(a, b)
    eq = pd.Series(sizes[a] == sizes[b]).groupby(comp_full).all()
    keep = ~pd.Series(comp_full).isin(eq[eq].index).to_numpy()
    res["secondary_template_filter_0.5-0.95"] = {"components_dropped": int(eq.sum()), "pairs_dropped": int((~keep).sum()),
                                                 "grid": evaluate_grid(correct[keep], comp_full[keep])}
    res["figure"] = plot_curve(grid)
    full_none = grid[f"0.5-{J_HI}"][-1]
    res["criterion"] = {"inflation_points_full_window_cap_none": full_none["inflation_points"],
                        "material_ge_5_points": full_none["inflation_points"] >= 5}
    save_result("E34_inflation_curve", res, {"windows": [f"{w}-{J_HI}" for w in WINDOWS], "caps": [str(c) for c in CAPS],
                                             "n_boot": N_BOOT, "pair_ci": "Wald", "pairs": "E31_pairs.parquet"})
    append_summary("E34", {"pair_acc_full_none": full_none["pair_level"]["accuracy"],
                           "comp_macro_full_none": full_none["component_level"]["macro"],
                           "inflation_points": full_none["inflation_points"],
                           "ci_width_ratio": full_none["ci_width_ratio_comp_over_pair"]})
    for wl, rows in grid.items():
        for r in rows:
            print(wl, r["cap"], r["pairs"], r["components"], round(r["pair_level"]["accuracy"], 4),
                  round(r["component_level"]["macro"], 4), round(r["ci_width_ratio_comp_over_pair"], 1))
    print(res["criterion"], res["reproduces_E31_pair_accuracy"])


if __name__ == "__main__":
    main()
