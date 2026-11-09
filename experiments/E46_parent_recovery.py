"""E46 - Revision-parent recovery on collusion.wiki, scored against diff_base.

Method side: the frozen E41-v2 lineage pipeline on the standard wiki table (rows shuffled
with seed 42; MinHash/LSH seed 42). The method never sees diff_base. Evaluation side
(src/evaluate.py): true parent links from collusion_slim.parquet are mapped to nodes and
compared with predicted parent links. Baselines: a random spanning tree of the same verified
edges, and "length parent" (most similar shorter neighbour).

File structure:
    Constants         paths, config
    random_tree       random spanning tree on the verified edges of one component
    length_parents    most similar shorter neighbour per node
    main
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import breadth_first_order, minimum_spanning_tree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import copydir  # noqa: E402
from src.adapters import STANDARD_COLUMNS  # noqa: E402
from src.copydir import assert_public, minhash_signatures, shingle_hashes_csr  # noqa: E402
from src.evaluate import parent_edge_evaluation, revision_parents, split_truth  # noqa: E402
from src.io_utils import INTERIM_DIR, REPO_ROOT, RESULTS_DIR, append_summary, save_result  # noqa: E402
from src.lineage import build_nodes, build_tree, lineage_components_scoped, lsh_bucket_components  # noqa: E402

CONFIG = REPO_ROOT / "configs" / "E41_lineage_v2.json"
TABLE = INTERIM_DIR / "collusion_standard.parquet"
SLIM = INTERIM_DIR / "collusion_slim.parquet"
F1_MARGIN = 0.10
DIR_MARGIN = 0.05


def random_tree(comp: dict[str, Any], rng: np.random.Generator) -> np.ndarray:
    """Random spanning tree of the verified-edge graph, rooted at a random node.

    Args:
        comp: Lineage component (edges matrix).
        rng: Seeded generator.

    Returns:
        Local parent array (-1 at the root).
    """
    n = len(comp["nodes"])
    w = np.where(comp["edges"], rng.random((n, n)) + 1e-9, 0.0)
    w = np.triu(w, 1)
    mst = minimum_spanning_tree(coo_matrix(w).tocsr())
    sym = mst + mst.T
    root = int(rng.integers(0, n))
    _, pred = breadth_first_order(sym, root, directed=False, return_predecessors=True)
    return np.where(pred < 0, -1, pred)


def length_parents(comp: dict[str, Any], lengths: np.ndarray) -> np.ndarray:
    """Each node's parent is its most similar strictly shorter verified neighbour.

    Args:
        comp: Lineage component (edges, jaccard).
        lengths: Text length per local node.

    Returns:
        Local parent array (-1 where no shorter neighbour exists).
    """
    n = len(lengths)
    par = np.full(n, -1)
    for v in range(n):
        cand = np.flatnonzero(comp["edges"][v] & (lengths < lengths[v]))
        if cand.size:
            par[v] = int(cand[np.argmax(comp["jaccard"][v, cand])])
    return par


def main() -> None:
    """Run E46 and write results/E46_parent_recovery.json."""
    cfg = json.loads(CONFIG.read_bytes())
    table = pd.read_parquet(TABLE)
    if list(table.columns) != STANDARD_COLUMNS:
        raise ValueError("not a standard table")
    table = table.sample(frac=1.0, random_state=cfg["row_shuffle_seed"]).reset_index(drop=True)
    public, _truth = split_truth(table)
    del table
    assert_public(public)
    nodes = build_nodes(public)
    group_of = dict(zip(public["doc_id"], public["group_id"]))
    node_groups = [frozenset(str(group_of[d]) for d in docs if pd.notna(group_of[d])) for docs in nodes["node_docs"]]
    flat, offsets = shingle_hashes_csr(nodes["rep_text"], len(nodes["rep_text"]))
    sig = minhash_signatures(flat, offsets, seed=cfg["seed"])
    cand = lsh_bucket_components(sig, np.diff(offsets) > 0, threshold=cfg["lsh_threshold"])
    del sig
    by_scope, counts = lineage_components_scoped(cand, flat, offsets, cfg, node_groups)
    lengths = np.array([len(t) for t in nodes["rep_text"]])
    parent_of = revision_parents(str(SLIM))
    res: dict[str, Any] = {"counts": counts, "scopes": {}}
    for sc in cfg["pair_scopes"]:
        comps = by_scope[sc]
        rng_tree = np.random.default_rng(cfg["seed"])
        rng_rand = np.random.default_rng(cfg["seed"] + 2)
        mst, rnd, lnp = [], [], []
        for c in comps:
            mst.append(build_tree(c, rng_tree)["parent"])
            rnd.append(random_tree(c, rng_rand))
            lnp.append(length_parents(c, lengths[c["nodes"]]))
        ev = parent_edge_evaluation(parent_of, nodes["node_docs"], [c["nodes"] for c in comps],
                                    {"mst_tree": mst, "random_spanning_tree": rnd, "length_parent": lnp},
                                    lengths, n_boot=cfg["n_boot"], seed=cfg["seed"])
        ev["lineage_components"] = len(comps)
        ev["nodes"] = int(sum(len(c["nodes"]) for c in comps))
        m, r = ev["mst_tree"], ev["random_spanning_tree"]
        go: dict[str, Any] = {}
        if "f1" in m and "f1" in r:
            go["a_structure"] = {"mst_f1": m["f1"]["macro"], "random_f1": r["f1"]["macro"],
                                 "passes": bool(m["f1"]["macro"] - r["f1"]["macro"] >= F1_MARGIN
                                                and m["f1"]["ci"][0] > r["f1"]["macro"])}
        if "orientation_by_method" in m:
            d, ln = m["orientation_by_method"], m["orientation_by_length_same_edges"]
            go["b_direction"] = {"depth": d["macro"], "length": ln["macro"],
                                 "passes": bool(d["macro"] - ln["macro"] >= DIR_MARGIN and d["ci"][0] > ln["macro"])}
        ev["go_no_go"] = go
        res["scopes"][sc] = ev
    e41 = json.loads((RESULTS_DIR / "E41v2_lineage_collusion_wiki.json").read_text())["results"]["counts"]
    res["anchor_check_vs_E41v2"] = {"components_all": [counts["all_lineage_components"], e41["all_lineage_components"]],
                                    "nodes_all": [counts["all_nodes_in_lineage_components"], e41["all_nodes_in_lineage_components"]]}
    res["anchor_check_vs_E41v2"]["exact"] = all(a == b for a, b in res["anchor_check_vs_E41v2"].values())
    save_result("E46_parent_recovery", res, {"config": cfg, "truth": "collusion_slim.parquet diff_base (evaluator only)",
                                             "f1_margin": F1_MARGIN, "direction_margin": DIR_MARGIN,
                                             "baselines": ["random spanning tree on verified edges (seed 44)",
                                                           "length parent: most similar shorter neighbour"]})
    summ = {"anchor_exact": res["anchor_check_vs_E41v2"]["exact"]}
    for sc, ev in res["scopes"].items():
        for k, g in ev["go_no_go"].items():
            summ[f"{sc}_{k}"] = g["passes"]
    append_summary("E46", summ)
    print(json.dumps(res["anchor_check_vs_E41v2"]))
    for sc, ev in res["scopes"].items():
        print(sc, json.dumps(ev["coverage"]))
        for mth in ("mst_tree", "random_spanning_tree", "length_parent"):
            print("  ", mth, {k: (round(v["macro"], 3), [round(x, 3) for x in v["ci"]]) for k, v in ev[mth].items()
                               if isinstance(v, dict)}, round(ev[mth]["pooled_precision"] or 0, 3), round(ev[mth]["pooled_recall"] or 0, 3))
        print("  go", json.dumps(ev["go_no_go"]))


if __name__ == "__main__":
    main()
