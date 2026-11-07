"""E32 - Copy direction v2: component-level scoring, template filter, edit-based cues.

Reuses the scored near-duplicate pairs from E31. Method code sees text only; t is
read only through src/evaluate.py. Also audits whether post ids are UUID v7.

File structure:
    Constants     cap, GO thresholds, paths
    union_find    connected-component id per pair
    uuid_audit    version / variant counts over all raw post ids; v7 time check if needed
    main          filter, cap, predict with (a)/(b)/(i)/(ii), score, save results
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.copydir import (  # noqa: E402
    assert_public,
    predict_extension,
    predict_insdel,
    predict_length,
    predict_random,
    shingles,
    tokens,
)
from src.evaluate import (  # noqa: E402
    component_accuracy,
    pairwise_order_truth,
    spearman_with_truth,
    split_truth,
)
from src.io_utils import INTERIM_DIR, REPO_ROOT, SEED, append_summary, save_result  # noqa: E402

CAP_PER_COMPONENT = 20
N_BOOT = 1000
GO_MARGIN = 0.05
GO_MIN_COMPONENTS = 200
V7_THRESHOLD = 0.5
POSTS_DIR = REPO_ROOT / "data" / "raw" / "moltbook" / "data" / "posts"


def union_find(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Connected-component id for each pair (a[k], b[k]).

    Args:
        a: Integer node ids.
        b: Integer node ids.

    Returns:
        Component root id per pair.
    """
    parent = np.arange(int(max(a.max(), b.max())) + 1)

    def find(x: int) -> int:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    for x, y in tqdm(zip(a.tolist(), b.tolist()), total=len(a), desc="union-find", unit="pair"):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry
    return np.array([find(x) for x in a.tolist()])


def uuid_audit(public_ids: np.ndarray, truth: pd.Series) -> dict[str, Any]:
    """Count UUID versions / variants over all raw post ids; check v7 time order if needed.

    Args:
        public_ids: Doc ids of the 300k sample (for the optional time check).
        truth: t indexed by doc_id (read only via src/evaluate.py).

    Returns:
        Dict of counts and, if v7 dominates, the Spearman check.
    """
    versions: Counter[str] = Counter()
    variants: Counter[str] = Counter()
    n = 0
    for p in tqdm(sorted(POSTS_DIR.glob("*.parquet")), desc="uuid audit", unit="file"):
        ids = pq.read_table(p, columns=["id"]).column("id").to_pylist()
        for s in ids:
            n += 1
            s = str(s)
            if len(s) == 36 and s[8] == "-":
                versions[s[14]] += 1
                variants[s[19].lower()] += 1
            else:
                versions["not_uuid"] += 1
    v7 = versions.get("7", 0) / n if n else 0.0
    out: dict[str, Any] = {"ids": n, "version_counts": dict(versions), "variant_char_counts": dict(variants),
                           "share_v7": v7, "v7_dominant": v7 > V7_THRESHOLD}
    if v7 > V7_THRESHOLD:
        ms = np.array([int(s.replace("-", "")[:12], 16) for s in public_ids], dtype=np.int64)
        out["v7_timestamp_vs_t"] = spearman_with_truth(ms, public_ids, truth)
    return out


def main() -> None:
    """Run E32 and write results/E32_copy_direction_v2.json."""
    table = pd.read_parquet(INTERIM_DIR / "moltbook_slim.parquet")
    public, truth = split_truth(table)
    del table
    assert_public(public)
    res: dict[str, Any] = {"uuid_audit": uuid_audit(public["doc_id"].to_numpy(), truth)}

    pairs = pd.read_parquet(INTERIM_DIR / "E31_pairs.parquet")
    text_of = dict(zip(public["doc_id"], public["text"]))
    docs = pd.unique(np.concatenate([pairs["doc_a"].to_numpy(), pairs["doc_b"].to_numpy()]))
    code = {d: k for k, d in enumerate(docs)}
    a = pairs["doc_a"].map(code).to_numpy()
    b = pairs["doc_b"].map(code).to_numpy()
    pairs["comp"] = union_find(a, b)

    ssize = np.array([len(shingles(text_of[d])) for d in tqdm(docs, desc="shingle sizes", unit="doc")])
    pairs["equal_size"] = ssize[a] == ssize[b]
    all_equal = pairs.groupby("comp")["equal_size"].all()
    dropped = all_equal[all_equal].index
    counts = {"input_pairs": int(len(pairs)), "input_docs": int(len(docs)),
              "components": int(all_equal.size),
              "components_dropped_all_equal_size": int(len(dropped)),
              "pairs_in_dropped_components": int(pairs["comp"].isin(dropped).sum())}
    kept = pairs[~pairs["comp"].isin(dropped)].copy()
    kept["r"] = np.random.default_rng(SEED).random(len(kept))
    capped = kept.sort_values(["comp", "r"]).groupby("comp", sort=False).head(CAP_PER_COMPONENT).reset_index(drop=True)
    counts["components_kept"] = int(capped["comp"].nunique())
    counts["pairs_after_cap"] = int(len(capped))

    a_earlier, valid = pairwise_order_truth(truth, capped["doc_a"].to_numpy(), capped["doc_b"].to_numpy())
    counts["pairs_equal_time_dropped"] = int((~valid).sum())
    capped = capped[valid].reset_index(drop=True)
    a_earlier = a_earlier[valid]
    counts["pairs_scored"] = int(len(capped))
    counts["components_scored"] = int(capped["comp"].nunique())
    sizes = capped.groupby("comp").size()
    counts["pairs_per_component"] = {"min": int(sizes.min()), "median": float(sizes.median()), "max": int(sizes.max())}

    ta = [text_of[d] for d in capped["doc_a"]]
    tb = [text_of[d] for d in capped["doc_b"]]
    toks_a = [tokens(t) for t in ta]
    toks_b = [tokens(t) for t in tb]
    preds = {
        "a_random": (predict_random(len(capped), seed=SEED), None),
        "b_longer_is_later": predict_length(np.array([len(t) for t in ta]), np.array([len(t) for t in tb]), seed=SEED),
        "i_extension": predict_extension(toks_a, toks_b, seed=SEED),
        "ii_insertion_vs_deletion": predict_insdel(toks_a, toks_b, seed=SEED),
    }
    comp = capped["comp"].to_numpy()
    methods: dict[str, Any] = {}
    for name, (pred, ties) in preds.items():
        m = component_accuracy((pred == a_earlier).astype(float), comp, n_boot=N_BOOT, seed=SEED)
        m["ties_broken_randomly"] = ties
        methods[name] = m
    tok_len_rule = np.array([len(x) < len(y) for x, y in zip(toks_a, toks_b)])
    tok_tie = np.array([len(x) == len(y) for x, y in zip(toks_a, toks_b)])
    res["diagnostics"] = {
        "agreement_ii_vs_token_count_rule_on_non_ties": float((preds["ii_insertion_vs_deletion"][0][~tok_tie]
                                                              == tok_len_rule[~tok_tie]).mean()) if (~tok_tie).any() else None,
        "token_count_ties": int(tok_tie.sum()),
        "agreement_i_vs_ii": float((preds["i_extension"][0] == preds["ii_insertion_vs_deletion"][0]).mean()),
        "agreement_b_vs_ii": float((preds["b_longer_is_later"][0] == preds["ii_insertion_vs_deletion"][0]).mean()),
    }

    base = methods["b_longer_is_later"]["macro"]
    go: dict[str, Any] = {"components_scored": counts["components_scored"],
                          "components_ge_200": counts["components_scored"] >= GO_MIN_COMPONENTS}
    for name in ("i_extension", "ii_insertion_vs_deletion"):
        m = methods[name]
        go[name] = {"margin_vs_b": m["macro"] - base, "margin_ge_5pp": m["macro"] - base >= GO_MARGIN,
                    "ci_low_above_b_point": m["ci_low"] > base}
        go[name]["passes"] = go[name]["margin_ge_5pp"] and go[name]["ci_low_above_b_point"] and go["components_ge_200"]
    go["go"] = go["i_extension"]["passes"] or go["ii_insertion_vs_deletion"]["passes"]

    res.update({"counts": counts, "methods": methods, "go_no_go": go})
    params = {"pairs_source": "data/interim/E31_pairs.parquet", "cap_per_component": CAP_PER_COMPONENT,
              "template_filter": "drop components where all pairs have equal shingle-set size (pre-cap)",
              "n_boot": N_BOOT, "go_margin": GO_MARGIN, "go_min_components": GO_MIN_COMPONENTS,
              "v7_threshold": V7_THRESHOLD, "tokens": "lower-cased \\w+", "diff": "difflib.SequenceMatcher autojunk=False"}
    save_result("E32_copy_direction_v2", res, params)
    append_summary("E32", {"components_scored": counts["components_scored"],
                           "macro_b": base, "macro_i": methods["i_extension"]["macro"],
                           "macro_ii": methods["ii_insertion_vs_deletion"]["macro"],
                           "share_v7": res["uuid_audit"]["share_v7"], "go": go["go"]})
    print(counts)
    print({k: {kk: v[kk] for kk in ("n_components", "macro", "ci_low", "ci_high", "micro", "ties_broken_randomly")}
           for k, v in methods.items()})
    print(res["diagnostics"], go, {k: res["uuid_audit"][k] for k in ("version_counts", "share_v7")})


if __name__ == "__main__":
    main()
