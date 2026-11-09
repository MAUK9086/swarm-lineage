"""E45 - Count 32-bit shingle-hash collisions on the Moltbook 300k sample.

The pipeline stores each 5-word shingle as a 32-bit blake2b hash (src/copydir.py). Here
every shingle is also hashed to 64 bits; distinct 64-bit values are taken as distinct
shingles, and the number of distinct 32-bit values among them gives the collision count.
Reads text only.

File structure:
    Constants     paths
    main          hash all shingles, count distinct values, save results
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.copydir import SHINGLE_K, _h32, assert_public, shingles  # noqa: E402
from src.evaluate import split_truth  # noqa: E402
from src.io_utils import INTERIM_DIR, append_summary, save_result  # noqa: E402


def _h64(s: str) -> int:
    """64-bit blake2b hash of a shingle string.

    Args:
        s: Shingle.

    Returns:
        Unsigned 64-bit integer.
    """
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "little")


def main() -> None:
    """Run E45 and write results/E45_hash_collisions.json."""
    public, _ = split_truth(pd.read_parquet(INTERIM_DIR / "moltbook_slim.parquet"))
    assert_public(public)
    h64_parts, h32_parts = [], []
    for text in tqdm(public["text"], desc="shingle hashes 32/64", unit="doc"):
        sh = shingles(text)
        if not sh:
            continue
        h64_parts.append(np.fromiter((_h64(s) for s in sh), dtype=np.uint64, count=len(sh)))
        h32_parts.append(np.fromiter((_h32(s) for s in sh), dtype=np.uint32, count=len(sh)))
    h64 = np.concatenate(h64_parts)
    h32 = np.concatenate(h32_parts)
    del h64_parts, h32_parts
    u64, first = np.unique(h64, return_index=True)
    h32_of_distinct = h32[first]
    n = int(u64.size)
    u32, counts = np.unique(h32_of_distinct, return_counts=True)
    colliding_values = int((counts > 1).sum())
    shingles_in_collisions = int(counts[counts > 1].sum())
    res = {"posts": int(len(public)), "shingle_occurrences_per_doc_sets": int(h64.size),
           "distinct_shingles_64bit": n, "distinct_32bit_values": int(u32.size),
           "lost_to_collisions": n - int(u32.size), "32bit_values_with_collision": colliding_values,
           "distinct_shingles_in_a_collision": shingles_in_collisions,
           "share_of_distinct_shingles_in_a_collision": shingles_in_collisions / n,
           "expected_lost_n2_over_2pow33": n * n / 2 ** 33}
    res["negligible_lt_0.1pct"] = res["share_of_distinct_shingles_in_a_collision"] < 0.001
    save_result("E45_hash_collisions", res, {"shingle_k_words": SHINGLE_K, "hash32": "blake2b digest_size=4",
                                             "hash64": "blake2b digest_size=8", "table": "moltbook_slim.parquet"})
    append_summary("E45", {"distinct_shingles": n, "lost_to_collisions": res["lost_to_collisions"],
                           "share_in_collision": res["share_of_distinct_shingles_in_a_collision"]})
    print(res)


if __name__ == "__main__":
    main()
