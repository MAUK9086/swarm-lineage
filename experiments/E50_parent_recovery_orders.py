"""E50 - E46 revision-parent recovery under six input orders (collusion.wiki).

Same method and evaluation as experiments/E46_parent_recovery.py (its baselines are
imported); only the row-shuffle seed changes. Seed 42 must reproduce E46.

File structure:
    Constants   seeds
    run_order   E46 pipeline and evaluation for one row order (all and within-page scopes)
    main
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.adapters import STANDARD_COLUMNS  # noqa: E402
from src.copydir import assert_public, minhash_signatures, shingle_hashes_csr  # noqa: E402
from src.evaluate import parent_edge_evaluation, revision_parents, split_truth  # noqa: E402
from src.io_utils import REPO_ROOT, RESULTS_DIR, append_summary, save_result  # noqa: E402
from src.lineage import build_nodes, build_tree, lineage_components_scoped, lsh_bucket_components  # noqa: E402

ORDERS = (42, 101, 102, 103, 104, 105)
SCOPES = ("all", "within_group")
spec = importlib.util.spec_from_file_location("e46", REPO_ROOT / "experiments" / "E46_parent_recovery.py")
E46 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(E46)


def run_order(table: pd.DataFrame, seed: int, cfg: dict[str, Any], parent_of: dict[str, str]) -> dict[str, Any]:
    """E46 for one row order.

    Args:
        table: Standard wiki table (unshuffled).
        seed: Row-shuffle seed.
        cfg: Frozen E41-v2 config.
        parent_of: True parents (evaluator only).

    Returns:
        Per-scope metrics and rule outcomes.
    """
    t = table.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    public, _ = split_truth(t)
    assert_public(public)
    nodes = build_nodes(public)
    group_of = dict(zip(public["doc_id"], public["group_id"]))
    node_groups = [frozenset(str(group_of[d]) for d in docs if pd.notna(group_of[d])) for docs in nodes["node_docs"]]
    flat, off = shingle_hashes_csr(nodes["rep_text"], len(nodes["rep_text"]))
    sig = minhash_signatures(flat, off, seed=cfg["seed"])
    cand = lsh_bucket_components(sig, np.diff(off) > 0, threshold=cfg["lsh_threshold"])
    by_scope, _ = lineage_components_scoped(cand, flat, off, cfg, node_groups)
    lengths = np.array([len(x) for x in nodes["rep_text"]])
    out: dict[str, Any] = {}
    for sc in SCOPES:
        comps = by_scope[sc]
        rt, rr = np.random.default_rng(cfg["seed"]), np.random.default_rng(cfg["seed"] + 2)
        mst, rnd, lnp = [], [], []
        for c in comps:
            mst.append(build_tree(c, rt)["parent"])
            rnd.append(E46.random_tree(c, rr))
            lnp.append(E46.length_parents(c, lengths[c["nodes"]]))
        ev = parent_edge_evaluation(parent_of, nodes["node_docs"], [c["nodes"] for c in comps],
                                    {"mst_tree": mst, "random_spanning_tree": rnd, "length_parent": lnp},
                                    lengths, n_boot=cfg["n_boot"], seed=cfg["seed"])
        m, r = ev["mst_tree"], ev["random_spanning_tree"]
        out[sc] = {"eligible_node_edges": ev["coverage"]["eligible_node_edges"],
                   "mst_f1": m["f1"]["macro"], "mst_f1_ci": m["f1"]["ci"], "random_f1": r["f1"]["macro"],
                   "length_parent_f1": ev["length_parent"]["f1"]["macro"],
                   "mst_orientation": m["orientation_by_method"]["macro"],
                   "length_orientation_same_edges": m["orientation_by_length_same_edges"]["macro"],
                   "structure_go": bool(m["f1"]["macro"] - r["f1"]["macro"] >= E46.F1_MARGIN and m["f1"]["ci"][0] > r["f1"]["macro"]),
                   "direction_go": bool(m["orientation_by_method"]["macro"] - m["orientation_by_length_same_edges"]["macro"] >= E46.DIR_MARGIN
                                        and m["orientation_by_method"]["ci"][0] > m["orientation_by_length_same_edges"]["macro"])}
    return out


def main() -> None:
    """Run E50 and write results/E50_parent_recovery_orders.json."""
    cfg = json.loads((REPO_ROOT / "configs" / "E41_lineage_v2.json").read_bytes())
    table = pd.read_parquet(E46.TABLE)
    if list(table.columns) != STANDARD_COLUMNS:
        raise ValueError("not a standard table")
    parent_of = revision_parents(str(E46.SLIM))
    res: dict[str, Any] = {"orders": {str(s): run_order(table, s, cfg, parent_of) for s in ORDERS}}
    e46 = json.loads((RESULTS_DIR / "E46_parent_recovery.json").read_text())["results"]["scopes"]["all"]
    base = e46["mst_tree"]["f1"]["macro"]
    res["anchor_exact"] = abs(res["orders"]["42"]["all"]["mst_f1"] - base) < 1e-12
    f1s = [v["all"]["mst_f1"] for v in res["orders"].values()]
    res["all_mst_f1_range"] = [min(f1s), max(f1s)]
    res["stable"] = bool(all(abs(x - base) <= 0.05 for x in f1s)
                         and all(v["all"]["structure_go"] and not v["all"]["direction_go"] for v in res["orders"].values()))
    save_result("E50_parent_recovery_orders", res, {"config": cfg, "row_shuffle_seeds": list(ORDERS)})
    append_summary("E50", {"anchor_exact": res["anchor_exact"], "f1_min": min(f1s), "f1_max": max(f1s), "stable": res["stable"]})
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
