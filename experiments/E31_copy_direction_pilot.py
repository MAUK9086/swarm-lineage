"""E31 - Copy-direction pilot on near-duplicate Moltbook post pairs.

Method code (src/copydir.py) sees only the public table (doc_id, text, group_id,
author_id). The hidden time t is read only through src/evaluate.py, for scoring.

File structure:
    Constants   Jaccard window, cap, GO thresholds
    components  connected-component id per pair (for the secondary cluster bootstrap)
    cluster_ci  secondary: bootstrap over components instead of pairs
    main        build pairs, predict with (a)/(b)/(c), score, save results
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.copydir import (  # noqa: E402
    LSH_THRESHOLD,
    NUM_PERM,
    SHINGLE_K,
    assert_public,
    band_pair_upper_bound,
    exact_duplicate_pair_counts,
    jaccard_csr,
    TooManyPairs,
    lsh_pairs_sampled,
    minhash_signatures,
    norm_text_hash,
    predict_containment,
    predict_length,
    predict_random,
    shingle_hashes_csr,
)
from src.evaluate import pairwise_accuracy, pairwise_order_truth, split_truth  # noqa: E402
from src.io_utils import INTERIM_DIR, SEED, append_summary, save_result  # noqa: E402

J_LO, J_HI = 0.5, 0.95
MAX_PAIRS = 20_000_000
MEMORY_GUARD_PAIRS = 60_000_000
N_BOOT = 1000
GO_MIN_PAIRS = 500
GO_MIN_MARGIN = 0.05


def components(i: np.ndarray, j: np.ndarray) -> np.ndarray:
    """Union-find component id for each pair.

    Args:
        i: First document index per pair.
        j: Second document index per pair.

    Returns:
        Component id per pair.
    """
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in zip(i.tolist(), j.tolist()):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return np.array([find(a) for a in i.tolist()])


def cluster_ci(correct: np.ndarray, comp: np.ndarray, seed: int = SEED) -> dict[str, float]:
    """Secondary CI: resample components with replacement, pool their pairs.

    Args:
        correct: 1.0 / 0.0 per pair.
        comp: Component id per pair.
        seed: Random seed.

    Returns:
        Dict with n_components, ci_low, ci_high.
    """
    df = pd.DataFrame({"c": comp, "ok": correct})
    g = df.groupby("c")["ok"].agg(["sum", "count"])
    s, n = g["sum"].to_numpy(), g["count"].to_numpy()
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(N_BOOT):
        k = rng.integers(0, len(g), len(g))
        boots.append(s[k].sum() / n[k].sum())
    return {"n_components": int(len(g)), "ci_low": float(np.percentile(boots, 2.5)),
            "ci_high": float(np.percentile(boots, 97.5))}


def main() -> None:
    """Run E31 and write results/E31_copy_direction_pilot.json."""
    table = pd.read_parquet(INTERIM_DIR / "moltbook_slim.parquet")
    public, truth = split_truth(table)
    del table
    assert_public(public)

    n_docs = len(public)
    hashes = np.array([norm_text_hash(t) for t in tqdm(public["text"], desc="text hashes", unit="doc")],
                      dtype=object)
    lens = public["text"].str.len().to_numpy()
    flat, offsets = shingle_hashes_csr(public["text"], n_docs)
    doc_ids = public["doc_id"].to_numpy()
    author_codes, _ = pd.factorize(public["author_id"], use_na_sentinel=True)
    del public

    sig = minhash_signatures(flat, offsets, seed=SEED)
    has_shingles = np.diff(offsets) > 0
    bound = band_pair_upper_bound(sig, has_shingles)
    # Exact path first: all different-author pairs, then the pre-registered uniform cap.
    # Fallback only if the memory guard trips: Bernoulli sampling at MAX_PAIRS / bound.
    path, rate = "exact", 1.0
    try:
        ci, cj = lsh_pairs_sampled(sig, has_shingles, author_codes, 1.0, seed=SEED, max_keep=MEMORY_GUARD_PAIRS)
    except TooManyPairs:
        path, rate = "bernoulli_fallback", min(1.0, MAX_PAIRS / bound)
        ci, cj = lsh_pairs_sampled(sig, has_shingles, author_codes, rate, seed=SEED)
    del sig
    n_diff_author = len(ci)
    capped = False
    if len(ci) > MAX_PAIRS:
        keep = np.sort(np.random.default_rng(SEED).choice(len(ci), MAX_PAIRS, replace=False))
        ci, cj = ci[keep], cj[keep]
        capped = True
    exact_counts = exact_duplicate_pair_counts(hashes, author_codes)

    df = jaccard_csr(flat, offsets, ci, cj)
    df["exact"] = (hashes[df["i"]] == hashes[df["j"]]) & (hashes[df["i"]] != "")
    counts = {
        "docs": int(n_docs),
        "docs_with_shingles": int(has_shingles.sum()),
        "lsh_band_pair_upper_bound": int(bound),
        "pair_generation_path": path,
        "sampling_rate": float(rate),
        "candidate_pairs_different_authors": int(n_diff_author),
        "capped_to_max_pairs": capped,
        "pairs_after_cap": int(len(ci)),
        "exact_duplicate_pairs_all_analytic": exact_counts["total_pairs"],
        "exact_duplicate_pairs_different_authors_analytic": exact_counts["different_known_author_pairs"],
        "exact_duplicate_pairs_in_sample_excluded": int(df["exact"].sum()),
        "non_exact_jaccard_gt_095": int(((~df["exact"]) & (df["jaccard"] > J_HI)).sum()),
        "non_exact_jaccard_lt_05": int(((~df["exact"]) & (df["jaccard"] < J_LO)).sum()),
    }
    kept = df[(~df["exact"]) & (df["jaccard"] >= J_LO) & (df["jaccard"] <= J_HI)].reset_index(drop=True)
    counts["pairs_in_window"] = int(len(kept))

    a_ids, b_ids = doc_ids[kept["i"]], doc_ids[kept["j"]]
    a_earlier, valid = pairwise_order_truth(truth, a_ids, b_ids)
    counts["pairs_equal_or_missing_time_excluded"] = int((~valid).sum())
    kept = kept[valid].reset_index(drop=True)
    a_earlier = a_earlier[valid]
    counts["pairs_scored"] = int(len(kept))
    counts["distinct_docs_in_scored_pairs"] = int(pd.unique(np.concatenate([kept["i"], kept["j"]])).size)

    len_i, len_j = lens[kept["i"]], lens[kept["j"]]
    pred_a = predict_random(len(kept), seed=SEED)
    pred_b, ties_b = predict_length(len_i, len_j, seed=SEED)
    pred_c, ties_c = predict_containment(kept["inter"].to_numpy(), kept["size_i"].to_numpy(),
                                         kept["size_j"].to_numpy(), seed=SEED)
    comp = components(kept["i"].to_numpy(), kept["j"].to_numpy())
    methods: dict[str, Any] = {}
    for name, pred, ties in (("a_random", pred_a, None), ("b_longer_is_later", pred_b, ties_b),
                             ("c_containment", pred_c, ties_c)):
        m = pairwise_accuracy(pred, a_earlier, n_boot=N_BOOT, seed=SEED)
        m["ties_broken_randomly"] = ties
        m["secondary_component_bootstrap"] = cluster_ci((pred == a_earlier).astype(float), comp)
        methods[name] = m
    methods["agreement_b_vs_c"] = float((pred_b == pred_c).mean()) if len(kept) else None

    b, c = methods["b_longer_is_later"], methods["c_containment"]
    go = None
    if c["n"]:
        go = {"pairs": c["n"], "pairs_ge_500": c["n"] >= GO_MIN_PAIRS,
              "margin_c_minus_b": c["accuracy"] - b["accuracy"],
              "margin_ge_5pp": c["accuracy"] - b["accuracy"] >= GO_MIN_MARGIN,
              "cis_non_overlapping": c["ci_low"] > b["ci_high"]}
        go["go"] = go["pairs_ge_500"] and go["margin_ge_5pp"] and go["cis_non_overlapping"]

    pd.DataFrame({"doc_a": a_ids[valid], "doc_b": b_ids[valid], "jaccard": kept["jaccard"]}).to_parquet(
        INTERIM_DIR / "E31_pairs.parquet", index=False)
    jac = kept["jaccard"].to_numpy()
    res = {"counts": counts, "methods": methods, "go_no_go": go,
           "scored_pair_jaccard": {f"p{p}": float(np.percentile(jac, p)) for p in (5, 25, 50, 75, 95)} if len(jac) else None}
    params = {"shingle_k_words": SHINGLE_K, "num_perm": NUM_PERM, "lsh_threshold": LSH_THRESHOLD,
              "jaccard_window": [J_LO, J_HI], "max_pairs": MAX_PAIRS, "memory_guard_pairs": MEMORY_GUARD_PAIRS, "n_boot": N_BOOT,
              "go_min_pairs": GO_MIN_PAIRS, "go_min_margin": GO_MIN_MARGIN, "corpus": "moltbook_slim (300k sample)"}
    save_result("E31_copy_direction_pilot", res, params)
    append_summary("E31", {"pairs_scored": counts["pairs_scored"],
                           "acc_random": methods["a_random"]["accuracy"],
                           "acc_length": b["accuracy"], "acc_containment": c["accuracy"],
                           "go": go["go"] if go else None})
    print(res["counts"])
    print({k: (v if not isinstance(v, dict) else {kk: v[kk] for kk in ("n", "accuracy", "ci_low", "ci_high")})
           for k, v in methods.items()})
    print(go)


if __name__ == "__main__":
    main()
