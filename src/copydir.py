"""Content-only copy-direction methods. Takes the public table only (no t).

Shingles are stored as 32-bit hashes in one flat array with per-document offsets
(CSR layout) to keep memory low. MinHash uses datasketch's legacy scheme and its
seed-42 permutations; LSH banding uses datasketch's optimal (bands, rows) for the
threshold, so candidate generation matches datasketch's MinHashLSH settings.

File structure:
    Constants             shingle size, MinHash / LSH parameters
    assert_public         guard: refuse tables that carry the hidden time column
    shingles              5-gram word shingles of a text, as a set of strings
    norm_text_hash        hash of normalised text (for exact-duplicate detection)
    shingle_hashes_csr    all documents' shingle hashes (32- or 64-bit) as (flat, offsets)
    minhash_signatures    MinHash signature matrix from the CSR shingle hashes
    lsh_candidate_pairs   banded LSH candidate pairs (i < j) from signatures (small inputs)
    _splitmix64           deterministic 64-bit hash used for pair sampling
    band_pair_upper_bound sum over bands of C(bucket, 2)
    TooManyPairs          memory-guard exception
    lsh_pairs_sampled     different-author LSH pairs, Bernoulli-sampled while generated
    exact_duplicate_pair_counts  exact-duplicate pair counts from hash groups
    jaccard_csr          exact Jaccard and set sizes for pairs, from CSR hashes
    predict_random        method (a): coin flip
    predict_length        method (b): the shorter post came first (longer is later)
    predict_containment   method (c): the post more fully contained in the other came first
    tokens                lower-cased word tokens
    affix_overlap         common prefix + suffix length (tokens)
    predict_extension     method (i): extension cue
    predict_insdel        method (ii): insertion vs deletion cue
"""

from __future__ import annotations

import hashlib
import re
from typing import Iterable

import numpy as np
import pandas as pd
from datasketch import MinHash
from datasketch.lsh import _optimal_param
from tqdm import tqdm

SHINGLE_K = 5
NUM_PERM = 128
LSH_THRESHOLD = 0.5
MERSENNE_PRIME = np.uint64((1 << 61) - 1)
MAX_HASH = np.uint64((1 << 32) - 1)
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


def _h32(s: str) -> int:
    """32-bit hash of a shingle string.

    Args:
        s: Shingle.

    Returns:
        Unsigned 32-bit integer.
    """
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=4).digest(), "little")


def _h64(s: str) -> int:
    """64-bit hash of a shingle string (used for collision checks).

    Args:
        s: Shingle.

    Returns:
        Unsigned 64-bit integer.
    """
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "little")


def shingle_hashes_csr(texts: Iterable[str], n: int, bits: int = 32) -> tuple[np.ndarray, np.ndarray]:
    """Sorted unique shingle hashes for every document, in CSR layout.

    The frozen pipelines use bits=32; bits=64 is used by E47 to test collision effects.

    Args:
        texts: Document texts.
        n: Number of documents (for the progress bar and offsets array).
        bits: 32 or 64.

    Returns:
        (flat uint32 or uint64 array, offsets int64 array of length n + 1)
    """
    h, dt = (_h32, np.uint32) if bits == 32 else (_h64, np.uint64)
    chunks: list[np.ndarray] = []
    offsets = np.zeros(n + 1, dtype=np.int64)
    for d, text in enumerate(tqdm(texts, total=n, desc=f"shingle hashes ({bits}-bit)", unit="doc")):
        arr = np.unique(np.fromiter((h(s) for s in shingles(text)), dtype=dt))
        chunks.append(arr)
        offsets[d + 1] = offsets[d] + arr.size
    flat = np.concatenate(chunks) if chunks else np.zeros(0, dtype=dt)
    return flat, offsets


def minhash_signatures(flat: np.ndarray, offsets: np.ndarray, num_perm: int = NUM_PERM,
                       seed: int = 42) -> np.ndarray:
    """MinHash signatures (datasketch legacy scheme, same permutations as MinHash(seed)).

    Documents without shingles keep the all-MAX_HASH signature and must be skipped.

    Args:
        flat: CSR shingle hashes.
        offsets: CSR offsets.
        num_perm: Number of permutations.
        seed: Permutation seed.

    Returns:
        uint32 array of shape (n_docs, num_perm).
    """
    perms = MinHash(num_perm=num_perm, seed=seed).permutations.astype(np.uint64)
    a, b = perms[0], perms[1]
    n = len(offsets) - 1
    sig = np.full((n, num_perm), int(MAX_HASH), dtype=np.uint32)
    for d in tqdm(range(n), desc="minhash", unit="doc"):
        s, e = offsets[d], offsets[d + 1]
        if e > s:
            hv = flat[s:e].astype(np.uint64)[:, None]
            phv = np.bitwise_and((hv * a + b) % MERSENNE_PRIME, MAX_HASH)
            sig[d] = phv.min(axis=0)
    return sig


def lsh_candidate_pairs(sig: np.ndarray, use: np.ndarray, threshold: float = LSH_THRESHOLD) -> tuple[np.ndarray, np.ndarray]:
    """Banded LSH: documents sharing any band are candidates.

    Args:
        sig: Signature matrix (n_docs, num_perm).
        use: Boolean mask of documents to include (non-empty shingle sets).
        threshold: Jaccard threshold used to choose (bands, rows) as datasketch does.

    Returns:
        (i, j) int64 arrays of unique candidate pairs with i < j.
    """
    bands, rows = _optimal_param(threshold, sig.shape[1], 0.5, 0.5)
    docs = np.flatnonzero(use)
    codes = np.zeros(0, dtype=np.int64)
    n = sig.shape[0]
    for bnd in tqdm(range(bands), desc="LSH bands", unit="band"):
        block = np.ascontiguousarray(sig[docs, bnd * rows:(bnd + 1) * rows])
        keys = block.view(np.dtype((np.void, block.dtype.itemsize * rows))).ravel()
        _, inv = np.unique(keys, return_inverse=True)
        order = np.argsort(inv, kind="stable")
        inv_sorted = inv[order]
        starts = np.flatnonzero(np.r_[True, inv_sorted[1:] != inv_sorted[:-1]])
        ends = np.r_[starts[1:], len(inv_sorted)]
        band_codes = []
        for s, e in zip(starts, ends):
            if e - s < 2:
                continue
            members = np.sort(docs[order[s:e]])
            ii, jj = np.triu_indices(len(members), k=1)
            band_codes.append(members[ii].astype(np.int64) * n + members[jj])
        if band_codes:
            codes = np.unique(np.concatenate([codes] + band_codes))
    return codes // n, codes % n


def _splitmix64(x: np.ndarray) -> np.ndarray:
    """SplitMix64 finaliser on uint64 values (deterministic pseudo-random hash).

    Args:
        x: uint64 array.

    Returns:
        uint64 array.
    """
    with np.errstate(over="ignore"):
        z = x + np.uint64(0x9E3779B97F4A7C15)
        z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        return z ^ (z >> np.uint64(31))


def band_pair_upper_bound(sig: np.ndarray, use: np.ndarray, threshold: float = LSH_THRESHOLD) -> int:
    """Sum over bands of C(bucket size, 2): an upper bound on unique candidate pairs.

    Args:
        sig: Signature matrix.
        use: Documents to include.
        threshold: LSH threshold (selects bands and rows).

    Returns:
        The bound.
    """
    bands, rows = _optimal_param(threshold, sig.shape[1], 0.5, 0.5)
    docs = np.flatnonzero(use)
    total = 0
    for bnd in range(bands):
        block = np.ascontiguousarray(sig[docs, bnd * rows:(bnd + 1) * rows])
        _, c = np.unique(block.view(np.dtype((np.void, block.dtype.itemsize * rows))).ravel(), return_counts=True)
        total += int((c.astype(np.int64) * (c - 1) // 2).sum())
    return total


class TooManyPairs(RuntimeError):
    """Raised when kept pairs exceed the memory guard in lsh_pairs_sampled."""


def lsh_pairs_sampled(sig: np.ndarray, use: np.ndarray, author_codes: np.ndarray, rate: float,
                      seed: int = 42, threshold: float = LSH_THRESHOLD,
                      max_keep: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Banded LSH candidate pairs with different known authors, Bernoulli-sampled on the fly.

    A pair (i, j) is kept iff its authors differ (both known) and a seeded hash of the
    pair falls below `rate`. The decision depends only on the pair, so the same pair
    found in several bands gets the same decision and the result is a uniform Bernoulli
    sample of the unique qualifying candidate pairs.

    Args:
        sig: Signature matrix (n_docs, num_perm).
        use: Documents to include.
        author_codes: Integer author code per document (-1 = unknown).
        rate: Keep probability in (0, 1].
        seed: Seed mixed into the pair hash.
        threshold: LSH threshold (selects bands and rows).
        max_keep: Raise TooManyPairs once more unique pairs than this are held.

    Returns:
        (i, j) int64 arrays with i < j, unique.

    Raises:
        TooManyPairs: If max_keep is exceeded.
    """
    bands, rows = _optimal_param(threshold, sig.shape[1], 0.5, 0.5)
    docs = np.flatnonzero(use)
    n = np.uint64(sig.shape[0])
    cut = np.uint64(min(int(rate * 2**64), 2**64 - 1))
    salt = _splitmix64(np.array([seed], dtype=np.uint64))[0]
    kept: list[np.ndarray] = []

    def keep(ii: np.ndarray, jj: np.ndarray) -> None:
        ok = (author_codes[ii] >= 0) & (author_codes[jj] >= 0) & (author_codes[ii] != author_codes[jj])
        ii, jj = ii[ok], jj[ok]
        codes = ii.astype(np.uint64) * n + jj.astype(np.uint64)
        sel = _splitmix64(codes ^ salt) < cut
        if sel.any():
            kept.append(codes[sel])

    for bnd in tqdm(range(bands), desc="LSH bands (sampled)", unit="band"):
        block = np.ascontiguousarray(sig[docs, bnd * rows:(bnd + 1) * rows])
        keys = block.view(np.dtype((np.void, block.dtype.itemsize * rows))).ravel()
        _, inv = np.unique(keys, return_inverse=True)
        order = np.argsort(inv, kind="stable")
        inv_sorted = inv[order]
        starts = np.flatnonzero(np.r_[True, inv_sorted[1:] != inv_sorted[:-1]])
        ends = np.r_[starts[1:], len(inv_sorted)]
        for s, e in zip(starts, ends):
            m = e - s
            if m < 2:
                continue
            members = np.sort(docs[order[s:e]])
            if m <= 300:
                ii, jj = np.triu_indices(m, k=1)
                keep(members[ii], members[jj])
            else:
                for r in range(m - 1):
                    keep(np.full(m - r - 1, members[r]), members[r + 1:])
        if len(kept) > 1:
            kept = [np.unique(np.concatenate(kept))]
        if max_keep is not None and kept and len(kept[0]) > max_keep:
            raise TooManyPairs(f"more than {max_keep} pairs after band {bnd}")
    codes = np.unique(np.concatenate(kept)) if kept else np.zeros(0, dtype=np.uint64)
    return (codes // n).astype(np.int64), (codes % n).astype(np.int64)


def exact_duplicate_pair_counts(text_hashes: np.ndarray, author_codes: np.ndarray) -> dict[str, int]:
    """Count exact-duplicate pairs analytically (all pairs, and different-author pairs).

    Args:
        text_hashes: Normalised-text hash per document ('' = empty).
        author_codes: Integer author code per document (-1 = unknown).

    Returns:
        Dict with total_pairs and different_known_author_pairs.
    """
    df = pd.DataFrame({"h": text_hashes, "a": author_codes})
    df = df[df["h"] != ""]
    g = df.groupby("h").size()
    total = int((g * (g - 1) // 2).sum())
    known = df[df["a"] >= 0]
    gk = known.groupby("h").size()
    same = known.groupby(["h", "a"]).size()
    diff = int((gk * (gk - 1) // 2).sum() - (same * (same - 1) // 2).sum())
    return {"total_pairs": total, "different_known_author_pairs": diff}


def jaccard_csr(flat: np.ndarray, offsets: np.ndarray, i: np.ndarray, j: np.ndarray) -> pd.DataFrame:
    """Exact Jaccard over 32-bit shingle hashes, plus intersection and set sizes.

    Args:
        flat: CSR shingle hashes.
        offsets: CSR offsets.
        i: First document index per pair.
        j: Second document index per pair.

    Returns:
        Frame with columns i, j, inter, size_i, size_j, jaccard.
    """
    inter = np.zeros(len(i), dtype=np.int64)
    for k in tqdm(range(len(i)), desc="exact Jaccard", unit="pair"):
        a = flat[offsets[i[k]]:offsets[i[k] + 1]]
        b = flat[offsets[j[k]]:offsets[j[k] + 1]]
        inter[k] = np.intersect1d(a, b, assume_unique=True).size
    size_i = offsets[i + 1] - offsets[i]
    size_j = offsets[j + 1] - offsets[j]
    jac = inter / (size_i + size_j - inter)
    return pd.DataFrame({"i": i, "j": j, "inter": inter, "size_i": size_i, "size_j": size_j, "jaccard": jac})


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


def tokens(text: str) -> list[str]:
    """Lower-cased word tokens.

    Args:
        text: Document text.

    Returns:
        Token list.
    """
    return TOKEN_RE.findall(text.lower())


def affix_overlap(a: list[str], b: list[str]) -> int:
    """Longest common prefix plus longest common suffix, without overlap in the shorter list.

    Args:
        a: Tokens of the first post.
        b: Tokens of the second post.

    Returns:
        Number of tokens covered by the common prefix and suffix.
    """
    n = min(len(a), len(b))
    p = 0
    while p < n and a[p] == b[p]:
        p += 1
    s = 0
    while s < n - p and a[-1 - s] == b[-1 - s]:
        s += 1
    return p + s


def predict_extension(toks_i: list[list[str]], toks_j: list[list[str]], seed: int = 42) -> tuple[np.ndarray, int]:
    """Method (i): the post whose tokens are more fully kept as prefix + suffix of the other came first.

    kept(i in j) = L / |i|, with L = affix_overlap(i, j). Ties (including L = 0 and empty
    posts) are broken at random.

    Args:
        toks_i: Token lists of the first element of each pair.
        toks_j: Token lists of the second element of each pair.
        seed: Seed for tie-breaking.

    Returns:
        (boolean 'i came first' array, number of ties)
    """
    ki = np.empty(len(toks_i))
    kj = np.empty(len(toks_i))
    for k, (a, b) in enumerate(zip(toks_i, toks_j)):
        L = affix_overlap(a, b)
        ki[k] = L / len(a) if a else 0.0
        kj[k] = L / len(b) if b else 0.0
    pred = ki > kj
    ties = ki == kj
    pred[ties] = np.random.default_rng(seed + 2).random(int(ties.sum())) < 0.5
    return pred, int(ties.sum())


def predict_insdel(toks_i: list[list[str]], toks_j: list[list[str]], seed: int = 42) -> tuple[np.ndarray, int]:
    """Method (ii): from a word diff i -> j, more inserted than deleted tokens means j is later.

    Args:
        toks_i: Token lists of the first element of each pair.
        toks_j: Token lists of the second element of each pair.
        seed: Seed for tie-breaking.

    Returns:
        (boolean 'i came first' array, number of ties)
    """
    import difflib

    ins = np.zeros(len(toks_i), dtype=np.int64)
    dele = np.zeros(len(toks_i), dtype=np.int64)
    for k, (a, b) in enumerate(tqdm(list(zip(toks_i, toks_j)), desc="word diff", unit="pair")):
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if op in ("insert", "replace"):
                ins[k] += j2 - j1
            if op in ("delete", "replace"):
                dele[k] += i2 - i1
    pred = ins > dele
    ties = ins == dele
    pred[ties] = np.random.default_rng(seed + 3).random(int(ties.sum())) < 0.5
    return pred, int(ties.sum())
