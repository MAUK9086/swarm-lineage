"""E42 - Sensitivity of copy-direction estimates to the Bernoulli pair sample (Moltbook).

Shingle hashes, MinHash signatures and the LSH band bound are computed once (seed 42, as
in E31). The different-author pair sample is then redrawn with several Bernoulli seeds at
E31's fallback rate (20M / band bound). For each seed: exact Jaccard, the 0.5-0.95 window,
pair-level accuracy (Wald CI) and the frozen E32 component pipeline (imported from
experiments/E36_replication.py). Seed 42 reproduces E31's pair sample, so it anchors the
comparison with E32. Method code never reads t.

File structure:
    Constants     seeds, paths
    load_v1       import the frozen E36 v1 script as a module
    main          signatures once, then one pass per seed; save results
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.clusters import wald_ci  # noqa: E402
from src.copydir import (  # noqa: E402
    assert_public,
    band_pair_upper_bound,
    jaccard_csr,
    lsh_pairs_sampled,
    minhash_signatures,
    norm_text_hash,
    predict_containment,
    predict_length,
    predict_random,
    shingle_hashes_csr,
)
from src.evaluate import pairwise_order_truth, split_truth  # noqa: E402
from src.io_utils import INTERIM_DIR, REPO_ROOT, append_summary, save_result  # noqa: E402

SEEDS = (42, 43, 44, 45)
V1_PATH = REPO_ROOT / "experiments" / "E36_replication.py"
CONFIG = REPO_ROOT / "configs" / "E36_pipeline.json"


def load_v1():
    """Import the frozen E36 v1 script as a module (its main is not run).

    Returns:
        Module object.
    """
    spec = importlib.util.spec_from_file_location("e36_v1", V1_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    """Run E42 and write results/E42_pair_sample_sensitivity.json."""
    cfg = json.loads(CONFIG.read_text())
    v1 = load_v1()
    table = pd.read_parquet(INTERIM_DIR / "moltbook_slim.parquet")
    public, truth = split_truth(table)
    del table
    assert_public(public)
    n_docs = len(public)
    hashes = np.array([norm_text_hash(t) for t in tqdm(public["text"], desc="text hashes", unit="doc")], dtype=object)
    lens = public["text"].str.len().to_numpy()
    flat, offsets = shingle_hashes_csr(public["text"], n_docs)
    author_codes, _ = pd.factorize(public["author_id"], use_na_sentinel=True)
    sig = minhash_signatures(flat, offsets, seed=cfg["seed"])
    has = np.diff(offsets) > 0
    bound = band_pair_upper_bound(sig, has)
    rate = min(1.0, cfg["max_pairs"] / bound)
    doc_ids = public["doc_id"].to_numpy()
    lo, hi = cfg["jaccard_window"]

    per_seed: dict[str, Any] = {}
    for k in SEEDS:
        ci, cj = lsh_pairs_sampled(sig, has, author_codes, rate, seed=k)
        df = jaccard_csr(flat, offsets, ci, cj)
        exact = (hashes[df["i"]] == hashes[df["j"]]) & (hashes[df["i"]] != "")
        kept = df[(~exact) & (df["jaccard"] >= lo) & (df["jaccard"] <= hi)].reset_index(drop=True)
        a_earlier, valid = pairwise_order_truth(truth, doc_ids[kept["i"]], doc_ids[kept["j"]])
        kept = kept[valid].reset_index(drop=True)
        a_earlier = a_earlier[valid]
        pa = predict_random(len(kept), seed=cfg["seed"])
        pb, _ = predict_length(lens[kept["i"]], lens[kept["j"]], seed=cfg["seed"])
        pc, _ = predict_containment(kept["inter"].to_numpy(), kept["size_i"].to_numpy(), kept["size_j"].to_numpy(), seed=cfg["seed"])
        pair = {}
        for name, pred in (("a_random", pa), ("b_longer_is_later", pb), ("c_containment", pc)):
            acc = float((pred == a_earlier).mean())
            pair[name] = {"accuracy": acc, "wald_ci": wald_ci(acc, len(kept))}
        pairs = pd.DataFrame({"doc_a": doc_ids[kept["i"]], "doc_b": doc_ids[kept["j"]]})
        comp = v1.component_level(pairs, public, truth, cfg)
        per_seed[str(k)] = {"sampled_pairs": int(len(ci)), "pairs_scored": int(len(kept)),
                            "pair_level": pair, "component_level": comp}
        print(k, len(kept), {m: round(v["macro"], 4) for m, v in comp["methods"].items()}, flush=True)

    methods = ("a_random", "b_longer_is_later", "c_containment", "i_extension", "ii_insertion_vs_deletion")
    across: dict[str, Any] = {}
    for m in methods:
        vals = np.array([per_seed[str(k)]["component_level"]["methods"][m]["macro"] for k in SEEDS])
        lows = np.array([per_seed[str(k)]["component_level"]["methods"][m]["ci_low"] for k in SEEDS])
        across[m] = {"macro_per_seed": vals.tolist(), "mean": float(vals.mean()), "sd": float(vals.std(ddof=1)),
                     "min": float(vals.min()), "max": float(vals.max()),
                     "seeds_with_ci_low_above_0.5": int((lows > 0.5).sum())}
    pb_vals = np.array([per_seed[str(k)]["pair_level"]["b_longer_is_later"]["accuracy"] for k in SEEDS])
    across["pair_level_b"] = {"per_seed": pb_vals.tolist(), "mean": float(pb_vals.mean()), "sd": float(pb_vals.std(ddof=1))}
    e32 = json.loads((REPO_ROOT / "results" / "E32_copy_direction_v2.json").read_text())["results"]["methods"]
    anchor = {m: {"seed42": per_seed["42"]["component_level"]["methods"][m]["macro"], "E32": e32[m]["macro"]}
              for m in ("a_random", "b_longer_is_later", "i_extension", "ii_insertion_vs_deletion")}
    anchor_ok = all(abs(v["seed42"] - v["E32"]) <= 1e-9 for v in anchor.values())
    all_above = across["b_longer_is_later"]["seeds_with_ci_low_above_0.5"] == len(SEEDS)
    res = {"seeds": list(SEEDS), "rate": rate, "band_bound": int(bound), "per_seed": per_seed, "across_seeds": across,
           "seed42_reproduces_E32": {"items": anchor, "exact_1e-9": anchor_ok},
           "reading": "length weakly orders Moltbook copies" if all_above else "unresolved; sample-dependent"}
    save_result("E42_pair_sample_sensitivity", res, {"seeds": list(SEEDS), "rate_rule": "max_pairs / band bound (E31 fallback)",
                                                     "config": "configs/E36_pipeline.json", "minhash_seed": cfg["seed"]})
    append_summary("E42", {"length_macro_mean": across["b_longer_is_later"]["mean"],
                           "length_macro_min": across["b_longer_is_later"]["min"],
                           "length_macro_max": across["b_longer_is_later"]["max"],
                           "seed42_reproduces_E32": anchor_ok, "reading": res["reading"]})
    print(json.dumps(across), anchor_ok, res["reading"])


if __name__ == "__main__":
    main()
