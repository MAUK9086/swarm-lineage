"""T03 - Redraw E41's stored-order lineage trees with the v2 figure layout (appendix figure).

Rebuilds nodes from the unshuffled Moltbook table exactly as E41 v1 did, reads the saved
trees (data/interim/E41_trees_moltbook.parquet), takes true time ranks from
src/evaluate.py, and draws the four largest components. No new analysis.

File structure:
    load_tree_layout  import the frozen v1 tree layout
    plot              four trees coloured by true time rank
    main
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.evaluate import node_time_ranks, split_truth  # noqa: E402
from src.io_utils import FIGURES_DIR, INTERIM_DIR, REPO_ROOT  # noqa: E402
from src.lineage import build_nodes  # noqa: E402

SURFACE, TEXT, TEXT2, EDGE = "#fcfcfb", "#0b0b0b", "#52514e", "#c9c8c3"


def load_tree_layout():
    """Import tree_layout from the frozen E41 v1 script.

    Returns:
        The function.
    """
    spec = importlib.util.spec_from_file_location("e41_v1", REPO_ROOT / "experiments" / "E41_lineage.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.tree_layout


def plot(trees: list[dict], out: Path, title: str) -> None:
    """Draw up to four trees coloured by true time rank.

    Args:
        trees: Dicts with parent, root, depth, rank_time, tau.
        out: Output path.
        title: Figure title.
    """
    layout = load_tree_layout()
    fig = plt.figure(figsize=(13, 9), facecolor=SURFACE)
    axes = [fig.add_axes([0.03 + 0.43 * (k % 2), 0.52 - 0.47 * (k // 2), 0.40, 0.38]) for k in range(4)]
    cax = fig.add_axes([0.90, 0.30, 0.012, 0.40])
    cmap = plt.get_cmap("Blues")
    for ax in axes:
        ax.set_axis_off()
    for ax, tr in zip(axes, trees):
        pos = layout(tr["parent"], tr["root"], tr["depth"])
        for v, p in enumerate(tr["parent"]):
            if p >= 0:
                ax.plot([pos[v, 0], pos[p, 0]], [pos[v, 1], pos[p, 1]], color=EDGE, linewidth=0.8, zorder=1)
        n = len(tr["rank_time"])
        ax.scatter(pos[:, 0], pos[:, 1], c=cmap(0.15 + 0.85 * tr["rank_time"] / max(1, n - 1)), s=28,
                   edgecolors=SURFACE, linewidths=0.6, zorder=2)
        r = tr["root"]
        ax.scatter([pos[r, 0]], [pos[r, 1]], s=120, facecolors="none", edgecolors=TEXT, linewidths=1.5, zorder=3)
        ax.annotate("root", (pos[r, 0], pos[r, 1]), xytext=(8, 6), textcoords="offset points", fontsize=8, color=TEXT)
        ax.set_title(f"{n} nodes, max depth {int(tr['depth'].max())}; depth-vs-time tau = {tr['tau']:+.2f}",
                     loc="left", fontsize=9, color=TEXT)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, 1))
    cb = fig.colorbar(sm, cax=cax)
    cb.set_ticks([0, 1], labels=["earliest", "latest"])
    cb.set_label("true first-appearance time (rank within component)", color=TEXT2, fontsize=8)
    cb.outline.set_visible(False)
    fig.suptitle(title, x=0.01, ha="left", fontsize=11, color=TEXT)
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    print(out)


def main() -> None:
    """Redraw the stored-order trees."""
    table = pd.read_parquet(INTERIM_DIR / "moltbook_slim.parquet")
    public, truth = split_truth(table)
    nodes = build_nodes(public)
    t = pd.read_parquet(INTERIM_DIR / "E41_trees_moltbook.parquet")
    sizes = t.groupby("component").size().sort_values(ascending=False, kind="stable")
    trees = []
    for comp in sizes.index[:4]:
        g = t[t["component"] == comp].reset_index(drop=True)
        local = {nd: k for k, nd in enumerate(g["node"])}
        parent = np.array([local[p] if p >= 0 else -1 for p in g["parent_node"]])
        rank_time = node_time_ranks(truth, nodes["node_docs"], g["node"].to_numpy())
        r = g["rank_depth"].to_numpy()
        n = len(r)
        s = np.sign(r[:, None] - r[None, :]) * np.sign(rank_time[:, None] - rank_time[None, :])
        trees.append({"parent": parent, "root": int(np.flatnonzero(parent < 0)[0]), "depth": g["depth"].to_numpy(),
                      "rank_time": rank_time, "tau": float(s[np.triu_indices(n, 1)].sum() / (n * (n - 1) / 2))})
    plot(trees, FIGURES_DIR / "A1_trees_stored_order.png",
         "Inferred lineage trees, rows in stored (time-like) order (E41; 4 largest components; root circled)")


if __name__ == "__main__":
    main()
