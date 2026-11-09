"""E36-v2 - Frozen copy-direction pipeline, v2: seeded row shuffle and pair scopes.

Usage:
    python -I experiments/E36_replication_v2.py --table data/interim/moltbook_slim.parquet --name moltbook --check

Changes from v1 (experiments/E36_replication.py, unchanged and imported here): the
standard table is shuffled with a seeded permutation before any processing, and results
are reported for three pair scopes (all, within_group, cross_group) from one pair-finding
run. Parameters are frozen in configs/E36_pipeline_v2.json.

File structure:
    Constants       config path, v1 module
    load_v1         import the frozen v1 script as a module
    load_config     read the v2 config and check it against library constants
    scope_masks     within / cross group masks for scored pairs
    reproduction    pre-registered row-order check of scope all against E31 / E32
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

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import copydir  # noqa: E402
from src.adapters import STANDARD_COLUMNS  # noqa: E402
from src.copydir import assert_public  # noqa: E402
from src.evaluate import pairwise_order_truth, split_truth  # noqa: E402
from src.io_utils import REPO_ROOT, RESULTS_DIR, append_summary, save_result  # noqa: E402

CONFIG = REPO_ROOT / "configs" / "E36_pipeline_v2.json"
V1_PATH = REPO_ROOT / "experiments" / "E36_replication.py"
EXACT_ITEMS = ["docs", "docs_with_shingles", "lsh_band_pair_upper_bound", "pair_generation_path",
               "exact_duplicate_pairs_all_analytic", "exact_duplicate_pairs_different_authors_analytic"]


def load_v1():
    """Import the frozen v1 script as a module (its main is not run).

    Returns:
        Module object.
    """
    spec = importlib.util.spec_from_file_location("e36_v1", V1_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def scope_masks(groups: np.ndarray, i: np.ndarray, j: np.ndarray) -> dict[str, np.ndarray]:
    """Boolean masks per scope for pairs (i, j).

    Args:
        groups: group_id per document (object array, may contain missing values).
        i: First document index per pair.
        j: Second document index per pair.

    Returns:
        Dict scope -> mask.
    """
    gi, gj = groups[i], groups[j]
    known = pd.notna(gi) & pd.notna(gj)
    same = np.zeros(len(i), dtype=bool)
    same[known] = gi[known] == gj[known]
    return {"all": np.ones(len(i), dtype=bool), "within_group": same, "cross_group": ~same}


def reproduction(res: dict[str, Any]) -> dict[str, Any]:
    """Pre-registered row-order check of scope all against the saved E31 / E32 results.

    Args:
        res: This run's results.

    Returns:
        Dict with exact items, agreement items and the pass flag.
    """
    e31 = json.loads((RESULTS_DIR / "E31_copy_direction_pilot.json").read_text())["results"]
    e32 = json.loads((RESULTS_DIR / "E32_copy_direction_v2.json").read_text())["results"]
    exact = {k: {"v2": res["pairs"]["counts"][k], "E31": e31["counts"][k],
                 "match": res["pairs"]["counts"][k] == e31["counts"][k]} for k in EXACT_ITEMS}
    a = res["scopes"]["all"]
    comp = {}
    for m in ("a_random", "b_longer_is_later", "i_extension", "ii_insertion_vs_deletion"):
        v2 = a["component_level"]["methods"][m]["macro"]
        lo, hi = e32["methods"][m]["ci_low"], e32["methods"][m]["ci_high"]
        comp[m] = {"v2_macro": v2, "E32_macro": e32["methods"][m]["macro"], "E32_ci": [lo, hi], "inside": lo <= v2 <= hi}
    pair = {}
    for m in ("a_random", "b_longer_is_later", "c_containment"):
        v2 = a["pair_level"][m]["accuracy"]
        e = e31["methods"][m]["accuracy"]
        pair[m] = {"v2": v2, "E31": e, "diff_points": 100 * (v2 - e), "within_2_points": abs(v2 - e) <= 0.02}
    ok_i = all(x["match"] for x in exact.values())
    ok_ii = all(x["inside"] for x in comp.values()) and all(x["within_2_points"] for x in pair.values())
    return {"exact_items": exact, "component_level_inside_E32_ci": comp, "pair_level_within_2_points": pair,
            "passes_i_exact": ok_i, "passes_ii_expectation": ok_ii, "passes": ok_i and ok_ii}


def main() -> None:
    """Run E36-v2 on one standard table."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--check", action="store_true", help="row-order check against E31/E32 (Moltbook only)")
    args = ap.parse_args()
    cfg, cfg_hash = load_config()
    v1 = load_v1()
    table = pd.read_parquet(args.table)
    if list(table.columns) != STANDARD_COLUMNS:
        raise ValueError("not a standard table")
    table = table.sample(frac=1.0, random_state=cfg["row_shuffle_seed"]).reset_index(drop=True)
    public, truth = split_truth(table)
    del table
    assert_public(public)

    kept, counts, arrays = v1.find_pairs(public, cfg)
    doc_ids = public["doc_id"].to_numpy()
    a_earlier, valid = pairwise_order_truth(truth, doc_ids[kept["i"]], doc_ids[kept["j"]])
    counts["pairs_equal_or_missing_time_excluded"] = int((~valid).sum())
    kept = kept[valid].reset_index(drop=True)
    a_earlier = a_earlier[valid]
    counts["pairs_scored"] = int(len(kept))
    groups = public["group_id"].to_numpy(dtype=object)
    masks = scope_masks(groups, kept["i"].to_numpy(), kept["j"].to_numpy())
    gi = groups[kept["i"].to_numpy()]
    gj = groups[kept["j"].to_numpy()]
    counts["pairs_with_missing_group"] = int((pd.isna(gi) | pd.isna(gj)).sum())

    res: dict[str, Any] = {"table": args.name, "config_sha256": cfg_hash, "pairs": {"counts": counts}, "scopes": {}}
    for sc in cfg["pair_scopes"]:
        m = masks[sc]
        sub = kept[m].reset_index(drop=True)
        entry: dict[str, Any] = {"pairs_scored": int(m.sum()),
                                 "distinct_docs": int(pd.unique(np.concatenate([sub["i"], sub["j"]])).size) if len(sub) else 0}
        if len(sub):
            entry["pair_level"] = v1.pair_level(sub, a_earlier[m], public, arrays["lens"], cfg)
            pairs = pd.DataFrame({"doc_a": doc_ids[sub["i"]], "doc_b": doc_ids[sub["j"]]})
            entry["component_level"] = v1.component_level(pairs, public, truth, cfg)
        res["scopes"][sc] = entry
    if args.check:
        res["row_order_check"] = reproduction(res)
    save_result(f"E36v2_replication_{args.name}", res, {"config": cfg, "config_sha256": cfg_hash, "table": args.table})
    summ: dict[str, Any] = {}
    for sc, e in res["scopes"].items():
        summ[f"{sc}_pairs"] = e["pairs_scored"]
        if "component_level" in e:
            summ[f"{sc}_macro_length"] = e["component_level"]["methods"]["b_longer_is_later"]["macro"]
            summ[f"{sc}_pair_length"] = e["pair_level"]["b_longer_is_later"]["accuracy"]
    if args.check:
        summ["row_order_check_passes"] = res["row_order_check"]["passes"]
    append_summary(f"E36v2_{args.name}", summ)
    print(json.dumps(summ))
    if args.check:
        print(json.dumps(res["row_order_check"])[:3000])


if __name__ == "__main__":
    main()
