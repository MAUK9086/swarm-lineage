"""E41 - Lineage trees from near-duplicate components (frozen, dataset-agnostic).

Usage:
    python -I experiments/E41_lineage.py --table data/interim/moltbook_slim.parquet --name moltbook

Input is any standard-table Parquet. Method code (src/lineage.py, src/copydir.py) sees
the public columns only; node times, Kendall tau and the null are computed in
src/evaluate.py. Parameters are frozen in configs/E41_lineage.json.

File structure:
    Constants     config path, colours
    load_config   read the frozen config and check it against library constants
    tree_layout   x / y positions for drawing a rooted tree
    plot_trees    the 4 largest components, nodes coloured by true time rank
    main
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import copydir  # noqa: E402
from src.adapters import STANDARD_COLUMNS  # noqa: E402
from src.copydir import assert_public, minhash_signatures, shingle_hashes_csr  # noqa: E402
from src.evaluate import lineage_evaluation, node_time_ranks, split_truth  # noqa: E402
from src.io_utils import FIGURES_DIR, INTERIM_DIR, REPO_ROOT, append_summary, save_result  # noqa: E402
from src.lineage import build_nodes, build_tree, length_rank, lineage_components, lsh_bucket_components  # noqa: E402

CONFIG = REPO_ROOT / "configs" / "E41_lineage.json"
C_SURFACE, C_TEXT, C_TEXT2, C_EDGE = "#fcfcfb", "#0b0b0b", "#52514e", "#c9c8c3"


def load_config() -> tuple[dict[str, Any], str]:
    """Read the frozen config and verify it matches src/copydir.py constants.

    Returns:
        (config, SHA-256 of the file bytes)

    Raises:
        ValueError: On a mismatch.
    """
    raw = CONFIG.read_bytes()
    cfg = json.loads(raw)
    if (cfg["shingle_k_words"], cfg["num_perm"], cfg["lsh_threshold"]) != (copydir.SHINGLE_K, copydir.NUM_PERM, copydir.LSH_THRESHOLD):
        raise ValueError("config does not match src/copydir.py constants")
    return cfg, hashlib.sha256(raw).hexdigest()


def tree_layout(parent: np.ndarray, root: int, depth: np.ndarray) -> np.ndarray:
    """Positions for a rooted tree: leaves spread left to right, parents centred over children.

    Args:
        parent: Parent per node (-1 for the root).
        root: Root index.
        depth: Hop depth per node.

    Returns:
        Array (n, 2) of x, y positions.
    """
    n = len(parent)
    children: list[list[int]] = [[] for _ in range(n)]
    for v in range(n):
        if parent[v] >= 0:
            children[parent[v]].append(v)
    x = np.zeros(n)
    nxt = [0.0]

    def place(v: int) -> float:
        if not children[v]:
            x[v] = nxt[0]
            nxt[0] += 1.0
        else:
            x[v] = np.mean([place(c) for c in children[v]])
        return x[v]

    sys.setrecursionlimit(max(1000, 4 * n))
    place(root)
    return np.c_[x, -depth.astype(float)]


def plot_trees(comps: list[dict[str, Any]], trees: list[dict[str, Any]], time_ranks: list[np.ndarray],
               taus: list[float]) -> str:
    """Draw the 4 largest lineage components as trees coloured by true time rank.

    Args:
        comps: The 4 components.
        trees: Their trees.
        time_ranks: True time rank per node (0 = earliest), from src/evaluate.py.
        taus: Kendall tau of depth order vs time for each.

    Returns:
        Repo-relative figure path.
    """
    fig, axes = plt.subplots(2, 2, figsize=(12, 9), facecolor=C_SURFACE)
    cmap = plt.get_cmap("Blues")
    for ax, comp, tr, rk, tau in zip(axes.ravel(), comps, trees, time_ranks, taus):
        ax.set_facecolor(C_SURFACE)
        pos = tree_layout(tr["parent"], tr["root"], tr["depth"])
        for v, p in enumerate(tr["parent"]):
            if p >= 0:
                ax.plot([pos[v, 0], pos[p, 0]], [pos[v, 1], pos[p, 1]], color=C_EDGE, linewidth=0.8, zorder=1)
        n = len(rk)
        col = cmap(0.15 + 0.85 * rk / max(1, n - 1))
        ax.scatter(pos[:, 0], pos[:, 1], c=col, s=28, edgecolors=C_SURFACE, linewidths=0.6, zorder=2)
        r = tr["root"]
        ax.scatter([pos[r, 0]], [pos[r, 1]], s=120, facecolors="none", edgecolors=C_TEXT, linewidths=1.5, zorder=3)
        ax.annotate("root", (pos[r, 0], pos[r, 1]), xytext=(8, 6), textcoords="offset points", fontsize=8, color=C_TEXT)
        ax.set_title(f"{n} nodes, max depth {int(tr['depth'].max())}; depth-vs-time Kendall tau = {tau:+.2f}",
                     loc="left", fontsize=9, color=C_TEXT)
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, 1))
    cb = fig.colorbar(sm, ax=axes.ravel().tolist(), shrink=0.5, pad=0.02)
    cb.set_ticks([0, 1], labels=["earliest", "latest"])
    cb.set_label("true first-appearance time (rank within component)", color=C_TEXT2, fontsize=8)
    cb.outline.set_visible(False)
    fig.suptitle("Inferred lineage trees for the 4 largest near-duplicate components (root circled; depth increases downward)",
                 x=0.01, ha="left", fontsize=11, color=C_TEXT)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES_DIR / "E41_lineage_trees.png", dpi=150, facecolor=C_SURFACE)
    plt.close(fig)
    return "figures/E41_lineage_trees.png"


def main() -> None:
    """Run E41 on one standard table."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True)
    ap.add_argument("--name", required=True)
    args = ap.parse_args()
    cfg, cfg_hash = load_config()
    table = pd.read_parquet(args.table)
    if list(table.columns) != STANDARD_COLUMNS:
        raise ValueError("not a standard table")
    public, truth = split_truth(table)
    del table
    assert_public(public)

    nodes = build_nodes(public)
    n_nodes = len(nodes["rep_text"])
    flat, offsets = shingle_hashes_csr(nodes["rep_text"], n_nodes)
    sig = minhash_signatures(flat, offsets, seed=cfg["seed"])
    cand = lsh_bucket_components(sig, np.diff(offsets) > 0, threshold=cfg["lsh_threshold"])
    del sig
    comps, counts = lineage_components(cand, flat, offsets, cfg)
    counts.update({"posts": int(len(public)), "posts_with_empty_text": nodes["dropped_empty"], "nodes": int(n_nodes),
                   "nodes_with_more_than_one_post": int((nodes["count"] > 1).sum())})

    rng_tree = np.random.default_rng(cfg["seed"])
    rng_len = np.random.default_rng(cfg["seed"] + 1)
    lengths = np.array([len(t) for t in nodes["rep_text"]])
    trees, depth_ranks, len_ranks = [], [], []
    root_is_shortest = 0
    for c in comps:
        tr = build_tree(c, rng_tree)
        trees.append(tr)
        depth_ranks.append(tr["rank"])
        lr = length_rank(lengths[c["nodes"]], rng_len)
        len_ranks.append(lr)
        root_is_shortest += int(lengths[c["nodes"]][tr["root"]] == lengths[c["nodes"]].min())
    sizes = np.array([len(c["nodes"]) for c in comps])
    maxd = np.array([int(t["depth"].max()) for t in trees])
    counts["component_nodes"] = {"min": int(sizes.min()), "median": float(np.median(sizes)), "max": int(sizes.max())}
    counts["tree_max_depth"] = {"min": int(maxd.min()), "median": float(np.median(maxd)), "max": int(maxd.max())}
    counts["components_where_root_is_shortest_text"] = root_is_shortest
    counts["node_post_count_in_components"] = {"total_posts": int(sum(nodes["count"][c["nodes"]].sum() for c in comps))}

    ev = lineage_evaluation(truth, nodes["node_docs"], [c["nodes"] for c in comps],
                            {"depth": depth_ranks, "length": len_ranks},
                            n_boot=cfg["n_boot"], n_null=cfg["n_null"], seed=cfg["seed"])

    top = np.argsort(-sizes, kind="stable")[:4]
    time_ranks = [node_time_ranks(truth, nodes["node_docs"], comps[k]["nodes"]) for k in top]
    taus = []
    for k, rk in zip(top, time_ranks):
        r = depth_ranks[k]
        s = np.sign(r[:, None] - r[None, :]) * np.sign(rk[:, None] - rk[None, :])
        n = len(r)
        taus.append(float(s[np.triu_indices(n, 1)].sum() / (n * (n - 1) / 2)))
    fig = plot_trees([comps[k] for k in top], [trees[k] for k in top], time_ranks, taus)

    rows = []
    for k, (c, tr) in enumerate(zip(comps, trees)):
        for v in range(len(c["nodes"])):
            rows.append((k, int(c["nodes"][v]), int(c["nodes"][tr["parent"][v]]) if tr["parent"][v] >= 0 else -1,
                         int(tr["depth"][v]), int(tr["rank"][v]), int(len_ranks[k][v])))
    pd.DataFrame(rows, columns=["component", "node", "parent_node", "depth", "rank_depth", "rank_length"]).to_parquet(
        INTERIM_DIR / f"E41_trees_{args.name}.parquet", index=False)

    d, ln = ev["depth"], ev["length"]
    go = {"depth_macro_tau": d["macro_tau"], "depth_macro_ci": d["macro_ci"],
          "ci_excludes_0": d["macro_ci"][0] > 0 or d["macro_ci"][1] < 0,
          "length_macro_tau": ln["macro_tau"], "depth_above_length": d["macro_tau"] > ln["macro_tau"],
          "ci_entirely_below_0": d["macro_ci"][1] < 0}
    go["go"] = go["ci_excludes_0"] and go["depth_above_length"]
    res = {"table": args.name, "config_sha256": cfg_hash, "counts": counts, "evaluation": ev,
           "figure": fig, "figure_component_sizes": [int(sizes[k]) for k in top], "figure_taus_tau_a": taus, "go_no_go": go}
    save_result(f"E41_lineage_{args.name}", res, {"config": cfg, "config_sha256": cfg_hash, "table": args.table})
    append_summary(f"E41_{args.name}", {"components": ev["components"], "depth_macro_tau": d["macro_tau"],
                                        "length_macro_tau": ln["macro_tau"], "depth_naive_tau": d["naive_pooled_tau"],
                                        "go": go["go"]})
    print(json.dumps(counts))
    for m in ("depth", "length"):
        e = ev[m]
        print(m, round(e["macro_tau"], 4), [round(x, 4) for x in e["macro_ci"]], "naive", round(e["naive_pooled_tau"], 4),
              [round(x, 4) for x in e["naive_ci"]], "null", e["null"]["macro_fpr"], e["null"]["naive_fpr"])
    print(go)


if __name__ == "__main__":
    main()
