"""E44 - Lineage robustness on Moltbook: sampling / tie-break seeds, depth-only tau-b, 200-node cap.

Runs the E41-v2 pipeline (rows shuffled with seed 42; MinHash and LSH buckets with seed 42)
once up to the candidate components. Then, for each seed, the seed sets both the node
sample of components larger than 200 nodes and the tree / length tie-break generators.
Scores: depth with random tie-break (as E41-v2), depth with ties kept (tau-b) and length.
Seed 42 must reproduce E41-v2. Method code never reads t; scoring is in src/evaluate.py.

File structure:
    Constants     seeds, config path
    score_seed    components, trees and tau summary for one seed (all scopes)
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
from src import copydir  # noqa: E402
from src.adapters import STANDARD_COLUMNS  # noqa: E402
from src.copydir import assert_public, minhash_signatures, shingle_hashes_csr  # noqa: E402
from src.evaluate import lineage_tau_summary, split_truth  # noqa: E402
from src.io_utils import INTERIM_DIR, REPO_ROOT, RESULTS_DIR, append_summary, save_result  # noqa: E402
from src.lineage import build_nodes, build_tree, length_rank, lineage_components_scoped, lsh_bucket_components  # noqa: E402

SEEDS = (42, 43, 44, 45, 46)
CONFIG = REPO_ROOT / "configs" / "E41_lineage_v2.json"


def score_seed(seed: int, cand: np.ndarray, flat: np.ndarray, offsets: np.ndarray, cfg: dict[str, Any],
               node_groups: list[frozenset], lengths: np.ndarray, nodes: dict[str, Any],
               truth: pd.Series) -> dict[str, Any]:
    """Components, trees and tau summary for one seed.

    Args:
        seed: Seed for node sampling and tie-breaks.
        cand: Candidate component id per node.
        flat: CSR shingle hashes.
        offsets: CSR offsets.
        cfg: Frozen E41-v2 config.
        node_groups: Group ids per node.
        lengths: Representative text length per node.
        nodes: Output of build_nodes.
        truth: t indexed by doc_id (passed to src/evaluate.py only).

    Returns:
        Results per scope plus coverage counts.
    """
    cfg_s = dict(cfg, seed=seed)
    by_scope, counts = lineage_components_scoped(cand, flat, offsets, cfg_s, node_groups)
    out: dict[str, Any] = {"counts": counts}
    for sc in cfg["pair_scopes"]:
        comps = by_scope[sc]
        rng_tree = np.random.default_rng(seed)
        rng_len = np.random.default_rng(seed + 1)
        depth_rank, depth_only, len_rank = [], [], []
        for c in comps:
            tr = build_tree(c, rng_tree)
            depth_rank.append(tr["rank"])
            depth_only.append(tr["depth"])
            len_rank.append(length_rank(lengths[c["nodes"]], rng_len))
        ev = lineage_tau_summary(truth, nodes["node_docs"], [c["nodes"] for c in comps],
                                 {"depth": depth_rank, "depth_ties_kept": depth_only, "length": len_rank},
                                 n_boot=cfg["n_boot"], seed=seed)
        d, dt, ln = ev["depth"], ev["depth_ties_kept"], ev["length"]
        ev["e41v2_go_rule"] = bool((d["macro_ci"][0] > 0 or d["macro_ci"][1] < 0) and d["macro_tau"] > ln["macro_tau"])
        ev["depth_ties_kept_below_length"] = bool(dt["macro_tau"] < ln["macro_tau"])
        out[sc] = ev
    return out


def main() -> None:
    """Run E44 and write results/E44_lineage_robustness.json."""
    raw = CONFIG.read_bytes()
    cfg = json.loads(raw)
    if (cfg["shingle_k_words"], cfg["num_perm"], cfg["lsh_threshold"]) != (copydir.SHINGLE_K, copydir.NUM_PERM, copydir.LSH_THRESHOLD):
        raise ValueError("config does not match src/copydir.py constants")
    table = pd.read_parquet(INTERIM_DIR / "moltbook_slim.parquet")
    if list(table.columns) != STANDARD_COLUMNS:
        raise ValueError("not a standard table")
    table = table.sample(frac=1.0, random_state=cfg["row_shuffle_seed"]).reset_index(drop=True)
    public, truth = split_truth(table)
    del table
    assert_public(public)
    nodes = build_nodes(public)
    group_of = dict(zip(public["doc_id"], public["group_id"]))
    node_groups = [frozenset(str(group_of[d]) for d in docs if pd.notna(group_of[d])) for docs in nodes["node_docs"]]
    flat, offsets = shingle_hashes_csr(nodes["rep_text"], len(nodes["rep_text"]))
    sig = minhash_signatures(flat, offsets, seed=cfg["seed"])
    cand = lsh_bucket_components(sig, np.diff(offsets) > 0, threshold=cfg["lsh_threshold"])
    del sig
    lengths = np.array([len(t) for t in nodes["rep_text"]])
    res: dict[str, Any] = {"seeds": {}}
    for s in SEEDS:
        res["seeds"][str(s)] = score_seed(s, cand, flat, offsets, cfg, node_groups, lengths, nodes, truth)

    e41 = json.loads((RESULTS_DIR / "E41v2_lineage_moltbook.json").read_text())["results"]["scopes"]
    s42 = res["seeds"]["42"]
    chk = {f"{sc}.{m}": {"E44": s42[sc][m]["macro_tau"], "E41v2": e41[sc]["evaluation"][m]["macro_tau"]}
           for sc in cfg["pair_scopes"] for m in ("depth", "length")}
    chk["exact_1e-12"] = all(abs(v["E44"] - v["E41v2"]) < 1e-12 for v in chk.values())
    res["anchor_check_vs_E41v2"] = chk
    summary: dict[str, Any] = {}
    for sc in cfg["pair_scopes"]:
        for m in ("depth", "depth_ties_kept", "length"):
            vals = np.array([res["seeds"][str(s)][sc][m]["macro_tau"] for s in SEEDS])
            summary[f"{sc}.{m}"] = {"min": float(vals.min()), "max": float(vals.max()), "mean": float(vals.mean()),
                                    "sd": float(vals.std(ddof=1))}
        summary[f"{sc}.go_met_any_seed"] = any(res["seeds"][str(s)][sc]["e41v2_go_rule"] for s in SEEDS)
        summary[f"{sc}.ties_kept_below_length_all_seeds"] = all(res["seeds"][str(s)][sc]["depth_ties_kept_below_length"] for s in SEEDS)
        summary[f"{sc}.share_pairs_tied_in_depth"] = [res["seeds"][str(s)][sc]["depth_ties_kept"]["share_pairs_tied_in_order"] for s in SEEDS]
    summary["robust"] = bool(not any(summary[f"{sc}.go_met_any_seed"] for sc in cfg["pair_scopes"])
                             and all(summary[f"{sc}.ties_kept_below_length_all_seeds"] for sc in cfg["pair_scopes"]))
    c42 = s42["counts"]
    summary["cap_coverage"] = {"candidate_components_ge_min": c42["candidate_components_ge_min"],
                               "candidate_components_capped": c42["candidate_components_capped"],
                               "nodes_in_candidates_ge_min": c42["nodes_in_candidates_ge_min"],
                               "nodes_in_lineage_components_all": c42["all_nodes_in_lineage_components"]}
    res["summary"] = summary
    save_result("E44_lineage_robustness", res, {"config": cfg, "seeds": list(SEEDS),
                                                "seed_controls": "node sample of capped components, tree and length tie-breaks, bootstrap"})
    append_summary("E44", {"anchor_exact": chk["exact_1e-12"], "robust": summary["robust"],
                           "all_depth_min": summary["all.depth"]["min"], "all_depth_max": summary["all.depth"]["max"],
                           "all_length_min": summary["all.length"]["min"], "all_length_max": summary["all.length"]["max"]})
    print(json.dumps(chk))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
