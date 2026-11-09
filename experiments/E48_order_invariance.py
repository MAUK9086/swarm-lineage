"""E48 - Input-order invariance of the v2 lineage pipeline (Moltbook).

The table is shuffled with six row-shuffle seeds (42 as anchor, then 101-105); every other
seed is 42. For each order: candidate partition, lineage components, tree edges and macro
tau for depth and length. Partitions and edges are compared as sets of node hashes, which do
not depend on row order. Method code never reads t.

File structure:
    run_order   full v2 pipeline for one row order
    main
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.adapters import STANDARD_COLUMNS  # noqa: E402
from src.copydir import assert_public, minhash_signatures, shingle_hashes_csr  # noqa: E402
from src.evaluate import lineage_tau_summary, split_truth  # noqa: E402
from src.io_utils import INTERIM_DIR, REPO_ROOT, RESULTS_DIR, append_summary, save_result  # noqa: E402
from src.lineage import build_nodes, build_tree, length_rank, lineage_components_scoped, lsh_bucket_components  # noqa: E402

CONFIG = REPO_ROOT / "configs" / "E41_lineage_v2.json"
ORDERS = (42, 101, 102, 103, 104, 105)


def run_order(table: pd.DataFrame, order_seed: int, cfg: dict[str, Any]) -> dict[str, Any]:
    """Run the v2 pipeline on one row order.

    Args:
        table: Standard table (unshuffled).
        order_seed: Row-shuffle seed.
        cfg: Frozen config (all other seeds).

    Returns:
        Partition (node hash -> min hash in its candidate component), tree edge sets and taus.
    """
    t = table.sample(frac=1.0, random_state=order_seed).reset_index(drop=True)
    public, truth = split_truth(t)
    assert_public(public)
    nodes = build_nodes(public)
    group_of = dict(zip(public["doc_id"], public["group_id"]))
    node_groups = [frozenset(str(group_of[d]) for d in docs if pd.notna(group_of[d])) for docs in nodes["node_docs"]]
    n = len(nodes["rep_text"])
    flat, off = shingle_hashes_csr(nodes["rep_text"], n)
    sig = minhash_signatures(flat, off, seed=cfg["seed"])
    cand = lsh_bucket_components(sig, np.diff(off) > 0, threshold=cfg["lsh_threshold"])
    del sig
    h = nodes["node_hash"]
    part = pd.Series(h).groupby(cand).transform("min")
    partition = dict(zip(h, part))
    by_scope, counts = lineage_components_scoped(cand, flat, off, cfg, node_groups)
    lengths = np.array([len(x) for x in nodes["rep_text"]])
    out: dict[str, Any] = {"counts": counts, "partition": partition, "scopes": {}}
    for sc in cfg["pair_scopes"]:
        comps = by_scope[sc]
        rt, rl = np.random.default_rng(cfg["seed"]), np.random.default_rng(cfg["seed"] + 1)
        dr, lr, edges, members = [], [], set(), set()
        for c in comps:
            tr = build_tree(c, rt)
            dr.append(tr["rank"])
            lr.append(length_rank(lengths[c["nodes"]], rl))
            for v, p in enumerate(tr["parent"]):
                if p >= 0:
                    edges.add(frozenset((h[c["nodes"][v]], h[c["nodes"][p]])))
            members.add(frozenset(h[c["nodes"]]))
        ev = lineage_tau_summary(truth, nodes["node_docs"], [c["nodes"] for c in comps], {"depth": dr, "length": lr},
                                 n_boot=cfg["n_boot"], seed=cfg["seed"])
        d = ev["depth"]
        ev["go"] = bool((d["macro_ci"][0] > 0 or d["macro_ci"][1] < 0) and d["macro_tau"] > ev["length"]["macro_tau"])
        out["scopes"][sc] = {"eval": ev, "edges": edges, "members": members}
    return out


def main() -> None:
    """Run E48 and write results/E48_order_invariance.json."""
    cfg = json.loads(CONFIG.read_bytes())
    table = pd.read_parquet(INTERIM_DIR / "moltbook_slim.parquet")
    if list(table.columns) != STANDARD_COLUMNS:
        raise ValueError("not a standard table")
    runs = {s: run_order(table, s, cfg) for s in ORDERS}
    ref = runs[42]
    res: dict[str, Any] = {"orders": {}}
    for s, r in runs.items():
        row: dict[str, Any] = {"candidate_partition_identical_to_42": r["partition"] == ref["partition"],
                               "candidate_components_ge_min": r["counts"]["candidate_components_ge_min"],
                               "candidate_components_capped": r["counts"]["candidate_components_capped"]}
        for sc in cfg["pair_scopes"]:
            e, e0 = r["scopes"][sc], ref["scopes"][sc]
            row[sc] = {"lineage_components": e["eval"]["components"], "nodes": e["eval"]["nodes"],
                       "components_identical_to_42": len(e["members"] & e0["members"]) / max(1, len(e0["members"])),
                       "tree_edges_shared_with_42": len(e["edges"] & e0["edges"]) / max(1, len(e0["edges"] | e["edges"])),
                       "depth_tau": e["eval"]["depth"]["macro_tau"], "depth_ci": e["eval"]["depth"]["macro_ci"],
                       "length_tau": e["eval"]["length"]["macro_tau"], "go": e["eval"]["go"]}
        res["orders"][str(s)] = row
    e41 = json.loads((RESULTS_DIR / "E41v2_lineage_moltbook.json").read_text())["results"]["scopes"]["all"]["evaluation"]
    res["anchor_check_vs_E41v2"] = {"depth": [res["orders"]["42"]["all"]["depth_tau"], e41["depth"]["macro_tau"]],
                                    "length": [res["orders"]["42"]["all"]["length_tau"], e41["length"]["macro_tau"]]}
    res["anchor_check_vs_E41v2"]["exact_1e-12"] = all(abs(a - b) < 1e-12 for a, b in res["anchor_check_vs_E41v2"].values())
    res["partitions_identical_all"] = all(v["candidate_partition_identical_to_42"] for v in res["orders"].values())
    res["go_met_any"] = any(v[sc]["go"] for v in res["orders"].values() for sc in cfg["pair_scopes"])
    res["invariant_by_rule"] = bool(res["partitions_identical_all"] and not res["go_met_any"])
    save_result("E48_order_invariance", res, {"config": cfg, "row_shuffle_seeds": list(ORDERS)})
    append_summary("E48", {"partitions_identical": res["partitions_identical_all"], "go_any": res["go_met_any"],
                           "anchor_exact": res["anchor_check_vs_E41v2"]["exact_1e-12"]})
    print(json.dumps(res, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
