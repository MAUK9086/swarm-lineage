"""E36 - Frozen copy-direction pipeline (E31 pair finding + E32 component scoring) for any adapter table.

Usage:
    python -I experiments/E36_replication.py --table data/interim/moltbook_slim.parquet --name moltbook --check

Input is a standard-table Parquet (doc_id, text, group_id, author_id, t). Method code sees
the public columns only; t is read only through src/evaluate.py. Parameters are frozen in
configs/E36_pipeline.json; its SHA-256 is written into the results.

File structure:
    Constants         config path, saved results for the reproduction check
    load_config       read the frozen config and check it matches the library constants
    find_pairs        E31: shingles, MinHash, LSH, different-author pairs, Jaccard window
    pair_level        E31 pair-level scoring, plus edit cues on a seeded subsample
    component_level   E32 component pipeline (union-find, template filter, cap, macro scoring)
    reproduction      compare with results/E31 and results/E32 (Moltbook only)
    main
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import copydir  # noqa: E402
from src.adapters import STANDARD_COLUMNS  # noqa: E402
from src.clusters import union_find  # noqa: E402
from src.copydir import (  # noqa: E402
    TooManyPairs,
    assert_public,
    band_pair_upper_bound,
    exact_duplicate_pair_counts,
    jaccard_csr,
    lsh_pairs_sampled,
    minhash_signatures,
    norm_text_hash,
    predict_containment,
    predict_extension,
    predict_insdel,
    predict_length,
    predict_random,
    shingle_hashes_csr,
    shingles,
    tokens,
)
from src.evaluate import component_accuracy, pairwise_accuracy, pairwise_order_truth, split_truth  # noqa: E402
from src.io_utils import REPO_ROOT, RESULTS_DIR, append_summary, save_result  # noqa: E402

CONFIG = REPO_ROOT / "configs" / "E36_pipeline.json"


def load_config() -> tuple[dict[str, Any], str]:
    """Read the frozen config and verify it matches the library constants.

    Returns:
        (config dict, SHA-256 of the config file bytes)

    Raises:
        ValueError: If the config disagrees with src/copydir.py constants.
    """
    raw = CONFIG.read_bytes()
    cfg = json.loads(raw)
    if (cfg["shingle_k_words"], cfg["num_perm"], cfg["lsh_threshold"]) != (copydir.SHINGLE_K, copydir.NUM_PERM, copydir.LSH_THRESHOLD):
        raise ValueError("config does not match src/copydir.py constants")
    return cfg, hashlib.sha256(raw).hexdigest()


def find_pairs(public: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    """E31 pair finding.

    Args:
        public: Public table (no t).
        cfg: Frozen config.

    Returns:
        (window pairs frame with i, j, inter, size_i, size_j, jaccard; counts; per-doc arrays)
    """
    seed = cfg["seed"]
    n_docs = len(public)
    hashes = np.array([norm_text_hash(t) for t in tqdm(public["text"], desc="text hashes", unit="doc")], dtype=object)
    lens = public["text"].str.len().to_numpy()
    flat, offsets = shingle_hashes_csr(public["text"], n_docs)
    author_codes, _ = pd.factorize(public["author_id"], use_na_sentinel=True)
    sig = minhash_signatures(flat, offsets, seed=seed)
    has = np.diff(offsets) > 0
    bound = band_pair_upper_bound(sig, has)
    path, rate = "exact", 1.0
    try:
        ci, cj = lsh_pairs_sampled(sig, has, author_codes, 1.0, seed=seed, max_keep=cfg["memory_guard_pairs"])
    except TooManyPairs:
        path, rate = "bernoulli_fallback", min(1.0, cfg["max_pairs"] / bound)
        ci, cj = lsh_pairs_sampled(sig, has, author_codes, rate, seed=seed)
    del sig
    n_diff = len(ci)
    capped = False
    if len(ci) > cfg["max_pairs"]:
        keep = np.sort(np.random.default_rng(seed).choice(len(ci), cfg["max_pairs"], replace=False))
        ci, cj = ci[keep], cj[keep]
        capped = True
    exact_counts = exact_duplicate_pair_counts(hashes, author_codes)
    df = jaccard_csr(flat, offsets, ci, cj)
    df["exact"] = (hashes[df["i"]] == hashes[df["j"]]) & (hashes[df["i"]] != "")
    lo, hi = cfg["jaccard_window"]
    counts = {
        "docs": int(n_docs), "docs_with_shingles": int(has.sum()), "lsh_band_pair_upper_bound": int(bound),
        "pair_generation_path": path, "sampling_rate": float(rate),
        "candidate_pairs_different_authors": int(n_diff), "capped_to_max_pairs": capped, "pairs_after_cap": int(len(ci)),
        "exact_duplicate_pairs_all_analytic": exact_counts["total_pairs"],
        "exact_duplicate_pairs_different_authors_analytic": exact_counts["different_known_author_pairs"],
        "exact_duplicate_pairs_in_sample_excluded": int(df["exact"].sum()),
        "non_exact_jaccard_gt_095": int(((~df["exact"]) & (df["jaccard"] > hi)).sum()),
        "non_exact_jaccard_lt_05": int(((~df["exact"]) & (df["jaccard"] < lo)).sum()),
    }
    kept = df[(~df["exact"]) & (df["jaccard"] >= lo) & (df["jaccard"] <= hi)].reset_index(drop=True)
    counts["pairs_in_window"] = int(len(kept))
    return kept, counts, {"lens": lens}


def pair_level(kept: pd.DataFrame, a_earlier: np.ndarray, public: pd.DataFrame, lens: np.ndarray,
               cfg: dict[str, Any]) -> dict[str, Any]:
    """E31 pair-level scoring for (a), (b), (c); edit cues (i), (ii) on a seeded subsample.

    Args:
        kept: Scored pairs (valid times only).
        a_earlier: Truth per pair.
        public: Public table.
        lens: Character length per document.
        cfg: Frozen config.

    Returns:
        Dict of method results.
    """
    seed, nb = cfg["seed"], cfg["n_boot"]
    pa = predict_random(len(kept), seed=seed)
    pb, tb = predict_length(lens[kept["i"]], lens[kept["j"]], seed=seed)
    pc, tc = predict_containment(kept["inter"].to_numpy(), kept["size_i"].to_numpy(), kept["size_j"].to_numpy(), seed=seed)
    out: dict[str, Any] = {}
    for name, pred, ties in (("a_random", pa, None), ("b_longer_is_later", pb, tb), ("c_containment", pc, tc)):
        m = pairwise_accuracy(pred, a_earlier, n_boot=nb, seed=seed)
        m["ties_broken_randomly"] = ties
        out[name] = m
    n_sub = min(cfg["edit_cue_pair_sample"], len(kept))
    sub = np.sort(np.random.default_rng(seed).choice(len(kept), n_sub, replace=False))
    texts = public["text"].to_numpy()
    ta = [tokens(texts[i]) for i in kept["i"].to_numpy()[sub]]
    tb_ = [tokens(texts[j]) for j in kept["j"].to_numpy()[sub]]
    for name, (pred, ties) in (("i_extension_subsample", predict_extension(ta, tb_, seed=seed)),
                               ("ii_insertion_vs_deletion_subsample", predict_insdel(ta, tb_, seed=seed))):
        m = pairwise_accuracy(pred, a_earlier[sub], n_boot=nb, seed=seed)
        m["ties_broken_randomly"] = ties
        out[name] = m
    return out


def component_level(pairs: pd.DataFrame, public: pd.DataFrame, truth: pd.Series, cfg: dict[str, Any]) -> dict[str, Any]:
    """E32 component pipeline on the scored pairs.

    Args:
        pairs: Frame with doc_a, doc_b (the E31 scored pairs, in order).
        public: Public table.
        truth: t indexed by doc_id (passed through to src/evaluate.py only).
        cfg: Frozen config.

    Returns:
        Dict with counts and method results.
    """
    seed, nb, cap = cfg["seed"], cfg["n_boot"], cfg["cap_per_component"]
    text_of = dict(zip(public["doc_id"], public["text"]))
    docs = pd.unique(np.concatenate([pairs["doc_a"].to_numpy(), pairs["doc_b"].to_numpy()]))
    code = {d: k for k, d in enumerate(docs)}
    a = pairs["doc_a"].map(code).to_numpy()
    b = pairs["doc_b"].map(code).to_numpy()
    pairs = pairs.copy()
    pairs["comp"] = union_find(a, b)
    ssize = np.array([len(shingles(text_of[d])) for d in tqdm(docs, desc="shingle sizes", unit="doc")])
    pairs["equal_size"] = ssize[a] == ssize[b]
    all_equal = pairs.groupby("comp")["equal_size"].all()
    dropped = all_equal[all_equal].index if cfg["template_filter"] else all_equal.index[:0]
    counts = {"input_pairs": int(len(pairs)), "input_docs": int(len(docs)), "components": int(all_equal.size),
              "components_dropped_all_equal_size": int(len(dropped)),
              "pairs_in_dropped_components": int(pairs["comp"].isin(dropped).sum())}
    kept = pairs[~pairs["comp"].isin(dropped)].copy()
    kept["r"] = np.random.default_rng(seed).random(len(kept))
    capped = kept.sort_values(["comp", "r"]).groupby("comp", sort=False).head(cap).reset_index(drop=True)
    counts["components_kept"] = int(capped["comp"].nunique())
    counts["pairs_after_cap"] = int(len(capped))
    a_earlier, valid = pairwise_order_truth(truth, capped["doc_a"].to_numpy(), capped["doc_b"].to_numpy())
    counts["pairs_equal_time_dropped"] = int((~valid).sum())
    capped = capped[valid].reset_index(drop=True)
    a_earlier = a_earlier[valid]
    counts["pairs_scored"] = int(len(capped))
    counts["components_scored"] = int(capped["comp"].nunique())
    ta = [text_of[d] for d in capped["doc_a"]]
    tb = [text_of[d] for d in capped["doc_b"]]
    toks_a, toks_b = [tokens(x) for x in ta], [tokens(x) for x in tb]
    sa = np.array([len(shingles(x)) for x in ta])
    sb = np.array([len(shingles(x)) for x in tb])
    inter = np.array([len(shingles(x) & shingles(y)) for x, y in zip(ta, tb)])
    preds = {
        "a_random": (predict_random(len(capped), seed=seed), None),
        "b_longer_is_later": predict_length(np.array([len(x) for x in ta]), np.array([len(x) for x in tb]), seed=seed),
        "c_containment": predict_containment(inter, sa, sb, seed=seed),
        "i_extension": predict_extension(toks_a, toks_b, seed=seed),
        "ii_insertion_vs_deletion": predict_insdel(toks_a, toks_b, seed=seed),
    }
    comp = capped["comp"].to_numpy()
    methods = {}
    for name, (pred, ties) in preds.items():
        m = component_accuracy((pred == a_earlier).astype(float), comp, n_boot=nb, seed=seed)
        m["ties_broken_randomly"] = ties
        methods[name] = m
    return {"counts": counts, "methods": methods}


def reproduction(res: dict[str, Any]) -> dict[str, Any]:
    """Compare with the saved E31 / E32 results (Moltbook only).

    Args:
        res: This run's results.

    Returns:
        Dict with per-item differences and an overall pass flag.
    """
    e31 = json.loads((RESULTS_DIR / "E31_copy_direction_pilot.json").read_text())["results"]
    e32 = json.loads((RESULTS_DIR / "E32_copy_direction_v2.json").read_text())["results"]
    diffs: dict[str, Any] = {}
    for k, v in e31["counts"].items():
        if k in res["pairs"]["counts"]:
            mine = res["pairs"]["counts"][k]
            diffs[f"E31.counts.{k}"] = 0.0 if mine == v else (abs(mine - v) if isinstance(v, (int, float)) and not isinstance(v, bool) else "mismatch")
    for m in ("a_random", "b_longer_is_later", "c_containment"):
        for f in ("n", "accuracy", "ci_low", "ci_high"):
            diffs[f"E31.{m}.{f}"] = abs(res["pair_level"][m][f] - e31["methods"][m][f])
    for k, v in e32["counts"].items():
        mine = res["component_level"]["counts"].get(k)
        if mine is not None and not isinstance(v, dict):
            diffs[f"E32.counts.{k}"] = abs(mine - v)
    for m in ("a_random", "b_longer_is_later", "i_extension", "ii_insertion_vs_deletion"):
        for f in ("n_components", "n_pairs", "macro", "ci_low", "ci_high", "micro"):
            diffs[f"E32.{m}.{f}"] = abs(res["component_level"]["methods"][m][f] - e32["methods"][m][f])
    numeric = [d for d in diffs.values() if not isinstance(d, str)]
    return {"max_abs_diff": float(max(numeric)), "non_numeric_mismatches": [k for k, d in diffs.items() if isinstance(d, str)],
            "items_compared": len(diffs),
            "passes_1e-9": all((not isinstance(d, str)) and d <= 1e-9 for d in diffs.values()),
            "items_over_1e-9": {k: d for k, d in diffs.items() if isinstance(d, str) or d > 1e-9}}


def main() -> None:
    """Run the frozen pipeline on one standard table."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--check", action="store_true", help="compare with saved E31/E32 results (Moltbook only)")
    args = ap.parse_args()
    cfg, cfg_hash = load_config()
    table = pd.read_parquet(args.table)
    if list(table.columns) != STANDARD_COLUMNS:
        raise ValueError(f"not a standard table: {list(table.columns)}")
    public, truth = split_truth(table)
    del table
    assert_public(public)

    kept, counts, arrays = find_pairs(public, cfg)
    doc_ids = public["doc_id"].to_numpy()
    a_ids, b_ids = doc_ids[kept["i"]], doc_ids[kept["j"]]
    a_earlier, valid = pairwise_order_truth(truth, a_ids, b_ids)
    counts["pairs_equal_or_missing_time_excluded"] = int((~valid).sum())
    kept = kept[valid].reset_index(drop=True)
    a_earlier = a_earlier[valid]
    counts["pairs_scored"] = int(len(kept))
    counts["distinct_docs_in_scored_pairs"] = int(pd.unique(np.concatenate([kept["i"], kept["j"]])).size)
    res: dict[str, Any] = {"table": args.name, "config_sha256": cfg_hash, "pairs": {"counts": counts}}
    res["pair_level"] = pair_level(kept, a_earlier, public, arrays["lens"], cfg)
    pairs = pd.DataFrame({"doc_a": a_ids[valid], "doc_b": b_ids[valid]})
    res["component_level"] = component_level(pairs, public, truth, cfg)
    if args.check:
        res["reproduction"] = reproduction(res)
    save_result(f"E36_replication_{args.name}", res, {"config": cfg, "config_sha256": cfg_hash, "table": args.table})
    summary = {"pairs_scored": counts["pairs_scored"],
               "pair_acc_length": res["pair_level"]["b_longer_is_later"]["accuracy"],
               "macro_length": res["component_level"]["methods"]["b_longer_is_later"]["macro"]}
    if args.check:
        summary["reproduces_E31_E32"] = res["reproduction"]["passes_1e-9"]
    append_summary(f"E36_{args.name}", summary)
    print(json.dumps(summary), json.dumps(res.get("reproduction", {}))[:1500])


if __name__ == "__main__":
    main()
