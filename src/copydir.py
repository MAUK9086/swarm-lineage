"""Content-only copy-direction methods. Takes the public table only (no t).

File structure:
    Constants           shingle size, MinHash parameters
    assert_public       guard: refuse tables that carry the hidden time column
    shingles            5-gram word shingles of a text, as a set of strings
    norm_text_hash      hash of normalised text (for exact-duplicate detection)
    candidate_pairs     MinHash LSH candidate pairs between documents
    jaccard_and_sizes   exact Jaccard and set sizes for candidate pairs
    predict_random      method (a): coin flip
    predict_length      method (b): the shorter post came first (longer is later)
    predict_containment method (c): the post more fully contained in the other came first
"""

from __future__ import annotations

import hashlib
import re
from typing import Iterable

import numpy as np
import pandas as pd
from datasketch import MinHash, MinHashLSH
from tqdm import tqdm

SHINGLE_K = 5
NUM_PERM = 128
LSH_THRESHOLD = 0.5
TOKEN_RE = re.compile(r"\w+", re.UNICODE)
WS_RE = re.compile(r"\s+")


def assert_public(table: pd.DataFrame) -> None:
    """Raise if the table carries the hidden time column.

    Args:
        table: Table passed to method code.

    Raises:
        ValueError: If a column named 't' is present.
    """
    if "t" in table.columns:
        raise ValueError("method code received the hidden column t")


def shingles(text: str, k: int = SHINGLE_K) -> set[str]:
    """Lower-cased k-word shingles; texts shorter than k words give one shingle.

    Args:
        text: Document text.
        k: Shingle size in words.

    Returns:
        Set of shingle strings (empty for texts without word tokens).
    """
    toks = TOKEN_RE.findall(text.lower())
    if not toks:
        return set()
    if len(toks) < k:
        return {" ".join(toks)}
    return {" ".join(toks[i:i + k]) for i in range(len(toks) - k + 1)}


def norm_text_hash(text: str) -> str:
    """Hash of whitespace-collapsed, lower-cased text.

    Args:
        text: Document text.

    Returns:
        Hex digest (16 chars); '' for empty normalised text.
    """
    n = WS_RE.sub(" ", text).strip().lower()
    return hashlib.blake2b(n.encode("utf-8"), digest_size=8).hexdigest() if n else ""


def candidate_pairs(sets: list[set[str]], seed: int = 42) -> set[tuple[int, int]]:
    """MinHash LSH candidate pairs (i < j) over non-empty shingle sets.

    Args:
        sets: Shingle set per document (row position = document index).
        seed: MinHash seed.

    Returns:
        Set of index pairs.
    """
    idx = [i for i, s in enumerate(sets) if s]
    mhs = MinHash.bulk((([x.encode("utf-8") for x in sets[i]]) for i in idx), num_perm=NUM_PERM, seed=seed)
    lsh = MinHashLSH(threshold=LSH_THRESHOLD, num_perm=NUM_PERM)
    for i, m in tqdm(zip(idx, mhs), total=len(idx), desc="LSH insert", unit="doc"):
        lsh.insert(i, m)
    pairs: set[tuple[int, int]] = set()
    for i, m in tqdm(zip(idx, mhs), total=len(idx), desc="LSH query", unit="doc"):
        for j in lsh.query(m):
            if j > i:
                pairs.add((i, j))
    return pairs


def jaccard_and_sizes(sets: list[set[str]], pairs: Iterable[tuple[int, int]]) -> pd.DataFrame:
    """Exact Jaccard, intersection and set sizes for pairs.

    Args:
        sets: Shingle sets.
        pairs: Index pairs.

    Returns:
        Frame with columns i, j, inter, size_i, size_j, jaccard.
    """
    rows = []
    for i, j in tqdm(pairs, desc="exact Jaccard", unit="pair"):
        a, b = sets[i], sets[j]
        inter = len(a & b)
        rows.append((i, j, inter, len(a), len(b), inter / (len(a) + len(b) - inter)))
    return pd.DataFrame(rows, columns=["i", "j", "inter", "size_i", "size_j", "jaccard"])


def predict_random(n: int, seed: int = 42) -> np.ndarray:
    """Method (a): random prediction that the first element came first.

    Args:
        n: Number of pairs.
        seed: Random seed.

    Returns:
        Boolean array.
    """
    return np.random.default_rng(seed).random(n) < 0.5


def predict_length(len_i: np.ndarray, len_j: np.ndarray, seed: int = 42) -> tuple[np.ndarray, int]:
    """Method (b): the longer post is later, so the shorter came first; ties are random.

    Args:
        len_i: Character length of the first element.
        len_j: Character length of the second element.
        seed: Seed for tie-breaking.

    Returns:
        (boolean 'i came first' array, number of ties)
    """
    pred = len_i < len_j
    ties = len_i == len_j
    pred[ties] = np.random.default_rng(seed).random(int(ties.sum())) < 0.5
    return pred, int(ties.sum())


def predict_containment(inter: np.ndarray, size_i: np.ndarray, size_j: np.ndarray,
                        seed: int = 42) -> tuple[np.ndarray, int]:
    """Method (c): the post whose shingles are more fully contained in the other came first.

    containment(i in j) = inter / size_i. Ties are broken at random.

    Args:
        inter: Shared shingle count.
        size_i: Shingle count of the first element.
        size_j: Shingle count of the second element.
        seed: Seed for tie-breaking.

    Returns:
        (boolean 'i came first' array, number of ties)
    """
    c_i = inter / size_i
    c_j = inter / size_j
    pred = c_i > c_j
    ties = c_i == c_j
    pred[ties] = np.random.default_rng(seed + 1).random(int(ties.sum())) < 0.5
    return pred, int(ties.sum())
