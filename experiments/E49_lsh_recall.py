"""E49 - Recall of the banded LSH candidate stage on a Moltbook subsample.

A seeded sample of 20,000 posts. Exact Jaccard for every pair that shares a shingle comes
from a sparse binary doc x shingle matrix product (64-bit shingle ids). True eligible pairs:
different authors, not exact duplicates (normalised text), Jaccard in [0.5, 0.95]. LSH
candidates: pairs sharing any band bucket (128 permutations, 25 x 5, seed 42, 32-bit input
hashes as in the pipeline). Reads text and author only.

File structure:
    Constants   sample size, bins
    main
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, triu

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.copydir import assert_public, lsh_candidate_pairs, minhash_signatures, norm_text_hash, shingle_hashes_csr  # noqa: E402
from src.evaluate import split_truth  # noqa: E402
from src.io_utils import INTERIM_DIR, SEED, append_summary, save_result  # noqa: E402

N_SAMPLE = 20_000
BINS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)


def main() -> None:
    """Run E49 and write results/E49_lsh_recall.json."""
    public, _ = split_truth(pd.read_parquet(INTERIM_DIR / "moltbook_slim.parquet"))
    assert_public(public)
    s = public.sample(n=N_SAMPLE, random_state=SEED).reset_index(drop=True)
    texts = s["text"].tolist()
    n = len(texts)
    f64, o64 = shingle_hashes_csr(texts, n, bits=64)
    cols = np.unique(f64, return_inverse=True)[1]
    rows = np.repeat(np.arange(n), np.diff(o64))
    x = csr_matrix((np.ones(len(cols), dtype=np.int32), (rows, cols)), shape=(n, int(cols.max()) + 1))
    inter = triu(x @ x.T, k=1).tocoo()
    size = np.diff(o64)
    i, j, k = inter.row, inter.col, inter.data
    jac = k / (size[i] + size[j] - k)
    auth = pd.factorize(s["author_id"])[0]
    nh = np.array([norm_text_hash(t) for t in texts], dtype=object)
    diff_author = auth[i] != auth[j]
    not_dup = nh[i] != nh[j]
    elig = diff_author & not_dup & (jac >= 0.5) & (jac <= 0.95)
    f32, o32 = shingle_hashes_csr(texts, n)
    sig = minhash_signatures(f32, o32, seed=SEED)
    ci, cj = lsh_candidate_pairs(sig, np.diff(o32) > 0)
    cand = set((ci.astype(np.int64) * n + cj).tolist())
    code = i.astype(np.int64) * n + j
    found = np.fromiter((c in cand for c in code), dtype=bool, count=len(code))
    res: dict[str, Any] = {"sample_posts": n, "pairs_sharing_a_shingle": int(len(code)), "eligible_pairs": int(elig.sum()),
                           "lsh_candidate_pairs": int(len(cand)),
                           "recall_0.5_0.95": float(found[elig].mean()) if elig.any() else None, "bins": {}}
    for lo, hi in zip(BINS[:-1], BINS[1:]):
        sel = elig & (jac >= lo) & ((jac < hi) if hi < 0.95 else (jac <= hi))
        res["bins"][f"{lo}-{hi}"] = {"pairs": int(sel.sum()), "recall": float(found[sel].mean()) if sel.any() else None}
    cand_da = np.fromiter(((c // n, c % n) for c in cand), dtype=np.dtype((np.int64, 2)), count=len(cand))
    in_window = {int(c) for c in code[elig]}
    da = auth[cand_da[:, 0]] != auth[cand_da[:, 1]]
    res["candidate_precision_different_author"] = float(np.mean([int(a * n + b) in in_window for a, b in cand_da[da]])) if da.any() else None
    pairs_in_comp = pd.Series(np.r_[i[elig], j[elig]]).nunique()
    res["posts_in_eligible_pairs"] = int(pairs_in_comp)
    res["recall_ge_0.8"] = bool(res["recall_0.5_0.95"] is not None and res["recall_0.5_0.95"] >= 0.8)
    save_result("E49_lsh_recall", res, {"sample": N_SAMPLE, "seed": SEED, "bands_rows": "25 x 5", "num_perm": 128,
                                        "truth": "different author, not exact duplicate, 0.5 <= J <= 0.95 (64-bit shingle ids)"})
    append_summary("E49", {"eligible_pairs": res["eligible_pairs"], "recall": res["recall_0.5_0.95"]})
    print(res)


if __name__ == "__main__":
    main()
