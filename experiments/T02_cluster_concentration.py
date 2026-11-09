"""T02 - How concentrated the Moltbook near-duplicate pairs are in a few clusters.

Descriptive, no hypothesis: reads E31's scored pairs (data/interim/E31_pairs.parquet),
builds connected components exactly as E34 / E35 do, and reports the cluster-size
distribution and the share of pairs held by the largest clusters. Saves aggregates only.

File structure:
    main   components, size distribution, cumulative concentration curve
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.clusters import doc_codes, union_find  # noqa: E402
from src.io_utils import INTERIM_DIR, save_result  # noqa: E402


def main() -> None:
    """Compute and save results/T02_cluster_concentration.json."""
    pairs = pd.read_parquet(INTERIM_DIR / "E31_pairs.parquet")
    a, b, docs = doc_codes(pairs["doc_a"].to_numpy(), pairs["doc_b"].to_numpy())
    comp = union_find(a, b)
    pairs_per = np.sort(pd.Series(comp).value_counts().to_numpy())[::-1]
    doc_comp = np.empty(len(docs), dtype=np.int64)
    doc_comp[a] = comp
    doc_comp[b] = comp
    docs_per = pd.Series(doc_comp).value_counts()
    total = pairs_per.sum()
    cum = np.cumsum(pairs_per) / total
    ks = [1, 2, 5, 10, 20, 50, 100]
    curve_k = np.unique(np.r_[np.arange(1, min(200, len(cum)) + 1), np.linspace(1, len(cum), 60).astype(int)])
    res = {
        "pairs": int(total), "clusters": int(len(pairs_per)), "posts_in_pairs": int(len(docs)),
        "share_of_pairs_in_largest": {str(k): float(cum[k - 1]) for k in ks if k <= len(cum)},
        "pairs_per_cluster": {"median": float(np.median(pairs_per)), "max": int(pairs_per[0]),
                              "clusters_with_1_pair": int((pairs_per == 1).sum()),
                              "clusters_with_ge_1000_pairs": int((pairs_per >= 1000).sum())},
        "posts_per_cluster": {"median": float(docs_per.median()), "max": int(docs_per.max())},
        "curve": {"k": curve_k.tolist(), "cum_share": [float(cum[k - 1]) for k in curve_k]},
    }
    save_result("T02_cluster_concentration", res, {"pairs": "E31_pairs.parquet", "components": "union-find as E34/E35"})
    print({k: v for k, v in res.items() if k != "curve"})


if __name__ == "__main__":
    main()
