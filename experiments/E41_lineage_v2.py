"""E41-v2 - Lineage trees, v2: seeded row shuffle and pair scopes.

Usage:
    python -I experiments/E41_lineage_v2.py --table data/interim/moltbook_slim.parquet --name moltbook --check

Changes from v1 (experiments/E41_lineage.py, unchanged; its tree layout is imported): the
standard table is shuffled with a seeded permutation before any processing, and lineage
components are built separately for three edge scopes (all, within_group, cross_group).
Method code never reads t; node times, Kendall tau and the null are in src/evaluate.py.
Parameters are frozen in configs/E41_lineage_v2.json.

File structure:
    Constants     config path, colours, v1 module path
    load_config   read the v2 config and check it against library constants
    plot_trees    the 4 largest components of one scope, nodes coloured by true time rank
    run_scope     trees, baseline ranks, evaluation and GO for one scope
    main
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
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
from src.io_utils import FIGURES_DIR, REPO_ROOT, RESULTS_DIR, append_summary, save_result  # noqa: E402
from src.lineage import build_nodes, build_tree, length_rank, lineage_components_scoped, lsh_bucket_components  # noqa: E402

CONFIG = REPO_ROOT / "configs" / "E41_lineage_v2.json"
V1_PATH = REPO_ROOT / "experiments" / "E41_lineage.py"
C_SURFACE, C_TEXT, C_TEXT2, C_EDGE = "#fcfcfb", "#0b0b0b", "#52514e", "#c9c8c3"


def load_config() -> tuple[dict[str, Any], str]:
    """Read the v2 config and verify it matches src/copydir.py constants.

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


def _tree_layout():
    """Import the frozen v1 tree layout function.

    Returns:
        The tree_layout function from experiments/E41_lineage.py.
    """
    spec = importlib.util.spec_from_file_location("e41_v1", V1_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.tree_layout


def plot_trees(trees: list[dict[str, Any]], time_ranks: list[np.ndarray], taus: list[float], scope: str, out: Path) -> str:
    """Draw up to 4 components of one scope as trees coloured by true time rank.

    Args:
        trees: Trees to draw.
        time_ranks: True time rank per node (0 = earliest), from src/evaluate.py.
        taus: Depth-vs-time tau-a per tree.
        scope: Scope label for the title.
        out: Output path.

    Returns:
        Repo-relative figure path.
    """
    layout = _tree_layout()
    fig = plt.figure(figsize=(13, 9), facecolor=C_SURFACE)
    axes = [fig.add_axes([0.03 + 0.43 * (k % 2), 0.52 - 0.47 * (k // 2), 0.40, 0.38]) for k in range(4)]
    cax = fig.add_axes([0.90, 0.30, 0.012, 0.40])
    cmap = plt.get_cmap("Blues")
    for ax in axes:
        ax.set_axis_off()
    for ax, tr, rk, tau in zip(axes, trees, time_ranks, taus):
        pos = layout(tr["parent"], tr["root"], tr["depth"])
        for v, p in enumerate(tr["parent"]):
            if p >= 0:
                ax.plot([pos[v, 0], pos[p, 0]], [pos[v, 1], pos[p, 1]], color=C_EDGE, linewidth=0.8, zorder=1)
        n = len(rk)
        ax.scatter(pos[:, 0], pos[:, 1], c=cmap(0.15 + 0.85 * rk / max(1, n - 1)), s=28, edgecolors=C_SURFACE,
                   linewidths=0.6, zorder=2)
        r = tr["root"]
        ax.scatter([pos[r, 0]], [pos[r, 1]], s=120, facecolors="none", edgecolors=C_TEXT, linewidths=1.5, zorder=3)
        ax.annotate("root", (pos[r, 0], pos[r, 1]), xytext=(8, 6), textcoords="offset points", fontsize=8, color=C_TEXT)
        ax.set_title(f"{n} nodes, max depth {int(tr['depth'].max())}; depth-vs-time tau = {tau:+.2f}",
                     loc="left", fontsize=9, color=C_TEXT)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, 1))
    cb = fig.colorbar(sm, cax=cax)
    cb.set_ticks([0, 1], labels=["earliest", "latest"])
    cb.set_label("true first-appearance time (rank within component)", color=C_TEXT2, fontsize=8)
    cb.outline.set_visible(False)
    fig.suptitle(f"Inferred lineage trees, rows shuffled, scope = {scope} (4 largest components; root circled)",
                 x=0.01, ha="left", fontsize=11, color=C_TEXT)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, facecolor=C_SURFACE)
    plt.close(fig)
    return str(out.relative_to(REPO_ROOT)).replace("\\", "/")


def run_scope(comps: list[dict[str, Any]], lengths: np.ndarray, nodes: dict[str, Any], truth: pd.Series,
              cfg: dict[str, Any], scope: str, name: str) -> dict[str, Any]:
    """Trees, baseline ranks, evaluation and GO for one scope (generators seeded as in v1).

    Args:
        comps: Lineage components of this scope.
        lengths: Representative text length per node.
        nodes: Output of build_nodes.
        truth: t indexed by doc_id (passed to src/evaluate.py only).
        cfg: Frozen config.
        scope: Scope name.
        name: Table name for output files.

    Returns:
        Results for the scope.
    """
    if not comps:
        return {"lineage_components": 0}
    rng_tree = np.random.default_rng(cfg["seed"])
    rng_len = np.random.default_rng(cfg["seed"] + 1)
    trees, depth_ranks, len_ranks, root_short = [], [], [], 0
    for c in comps:
        tr = build_tree(c, rng_tree)
        trees.append(tr)
        depth_ranks.append(tr["rank"])
        len_ranks.append(length_rank(lengths[c["nodes"]], rng_len))
        root_short += int(lengths[c["nodes"]][tr["root"]] == lengths[c["nodes"]].min())
    sizes = np.array([len(c["nodes"]) for c in comps])
    maxd = np.array([int(t["depth"].max()) for t in trees])
    ev = lineage_evaluation(truth, nodes["node_docs"], [c["nodes"] for c in comps],
                            {"depth": depth_ranks, "length": len_ranks},
                            n_boot=cfg["n_boot"], n_null=cfg["n_null"], seed=cfg["seed"])
    top = np.argsort(-sizes, kind="stable")[:4]
    tranks = [node_time_ranks(truth, nodes["node_docs"], comps[k]["nodes"]) for k in top]
    taus = []
    for k, rk in zip(top, tranks):
        r = depth_ranks[k]
        s = np.sign(r[:, None] - r[None, :]) * np.sign(rk[:, None] - rk[None, :])
        n = len(r)
        taus.append(float(s[np.triu_indices(n, 1)].sum() / (n * (n - 1) / 2)))
    fig = plot_trees([trees[k] for k in top], tranks, taus, scope, FIGURES_DIR / f"E41v2_trees_{name}_{scope}.png")
    d, ln = ev["depth"], ev["length"]
    go = {"depth_macro_tau": d["macro_tau"], "depth_macro_ci": d["macro_ci"],
          "ci_excludes_0": d["macro_ci"][0] > 0 or d["macro_ci"][1] < 0, "length_macro_tau": ln["macro_tau"],
          "depth_above_length": d["macro_tau"] > ln["macro_tau"], "ci_entirely_below_0": d["macro_ci"][1] < 0}
    go["go"] = go["ci_excludes_0"] and go["depth_above_length"]
    return {"lineage_components": int(len(comps)),
            "component_nodes": {"min": int(sizes.min()), "median": float(np.median(sizes)), "max": int(sizes.max())},
            "tree_max_depth": {"min": int(maxd.min()), "median": float(np.median(maxd)), "max": int(maxd.max())},
            "components_where_root_is_shortest_text": root_short, "evaluation": ev, "figure": fig,
            "figure_component_sizes": [int(sizes[k]) for k in top], "figure_taus_tau_a": taus, "go_no_go": go}


def main() -> None:
    """Run E41-v2 on one standard table."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--check", action="store_true", help="compare scope all with E41b (Moltbook only)")
    args = ap.parse_args()
    cfg, cfg_hash = load_config()
    table = pd.read_parquet(args.table)
    if list(table.columns) != STANDARD_COLUMNS:
        raise ValueError("not a standard table")
    table = table.sample(frac=1.0, random_state=cfg["row_shuffle_seed"]).reset_index(drop=True)
    public, truth = split_truth(table)
    del table
    assert_public(public)

    nodes = build_nodes(public)
    group_of = dict(zip(public["doc_id"], public["group_id"]))
    node_groups = [frozenset(str(group_of[d]) for d in docs if pd.notna(group_of[d])) for docs in nodes["node_docs"]]
    n_nodes = len(nodes["rep_text"])
    flat, offsets = shingle_hashes_csr(nodes["rep_text"], n_nodes)
    sig = minhash_signatures(flat, offsets, seed=cfg["seed"])
    cand = lsh_bucket_components(sig, np.diff(offsets) > 0, threshold=cfg["lsh_threshold"])
    del sig
    by_scope, counts = lineage_components_scoped(cand, flat, offsets, cfg, node_groups)
    counts.update({"posts": int(len(public)), "nodes": int(n_nodes),
                   "nodes_with_more_than_one_group": int(sum(1 for g in node_groups if len(g) > 1))})
    lengths = np.array([len(t) for t in nodes["rep_text"]])
    res: dict[str, Any] = {"table": args.name, "config_sha256": cfg_hash, "counts": counts, "scopes": {}}
    for sc in cfg["pair_scopes"]:
        res["scopes"][sc] = run_scope(by_scope[sc], lengths, nodes, truth, cfg, sc, args.name)

    if args.check:
        e41b = json.loads((RESULTS_DIR / "E41_lineage_moltbook_rowshuffled.json").read_text())["results"]["evaluation"]
        a = res["scopes"]["all"]["evaluation"]
        chk = {}
        for m in ("depth", "length"):
            for f in ("macro_tau", "naive_pooled_tau"):
                chk[f"{m}.{f}"] = {"v2": a[m][f], "E41b": e41b[m][f], "abs_diff": abs(a[m][f] - e41b[m][f])}
            chk[f"{m}.inside_E41b_ci"] = e41b[m]["macro_ci"][0] <= a[m]["macro_tau"] <= e41b[m]["macro_ci"][1]
        chk["components"] = {"v2": res["scopes"]["all"]["lineage_components"], "E41b": e41b["components"]}
        diffs = [v["abs_diff"] for v in chk.values() if isinstance(v, dict) and "abs_diff" in v]
        chk["exact_1e-9"] = max(diffs) <= 1e-9 and chk["components"]["v2"] == chk["components"]["E41b"]
        chk["in_expectation"] = bool(chk["depth.inside_E41b_ci"] and chk["length.inside_E41b_ci"])
        res["check_vs_E41b"] = chk
    save_result(f"E41v2_lineage_{args.name}", res, {"config": cfg, "config_sha256": cfg_hash, "table": args.table})
    summ: dict[str, Any] = {}
    for sc, e in res["scopes"].items():
        summ[f"{sc}_components"] = e["lineage_components"]
        if "evaluation" in e:
            summ[f"{sc}_depth_macro"] = e["evaluation"]["depth"]["macro_tau"]
            summ[f"{sc}_length_macro"] = e["evaluation"]["length"]["macro_tau"]
            summ[f"{sc}_go"] = e["go_no_go"]["go"]
    if args.check:
        summ["reproduces_E41b_exact"] = res["check_vs_E41b"]["exact_1e-9"]
    append_summary(f"E41v2_{args.name}", summ)
    print(json.dumps(counts))
    print(json.dumps(summ))


if __name__ == "__main__":
    main()
