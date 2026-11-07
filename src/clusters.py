"""Cluster utilities for pair-based evaluation. No access to the hidden time column.

File structure:
    union_find        connected-component id per pair (same algorithm as E32)
    doc_codes         integer code per document, in first-seen order over (a, b)
    cap_pairs         at most k pairs per component, chosen by a seeded random key
    wald_ci           normal-approximation 95% CI for a proportion
    wilson_ci         Wilson 95% CI for a proportion
    macro_bootstrap   macro accuracy over components with a vectorised component bootstrap
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from tqdm import tqdm


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


def doc_codes(doc_a: np.ndarray, doc_b: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Integer codes for documents, in first-seen order over concat(a, b) (as in E32).

    Args:
        doc_a: Doc ids of the first element.
        doc_b: Doc ids of the second element.

    Returns:
        (code of a, code of b, doc id per code)
    """
    docs = pd.unique(np.concatenate([doc_a, doc_b]))
    code = {d: k for k, d in enumerate(docs)}
    return (np.fromiter((code[d] for d in doc_a), dtype=np.int64, count=len(doc_a)),
            np.fromiter((code[d] for d in doc_b), dtype=np.int64, count=len(doc_b)), docs)


def cap_pairs(comp: np.ndarray, k: int | None, seed: int = 42) -> np.ndarray:
    """Indices of at most k pairs per component (all pairs if k is None), sorted.

    Args:
        comp: Component id per pair.
        k: Cap per component, or None for no cap.
        seed: Seed for the random selection key.

    Returns:
        Sorted integer indices into the pair arrays.
    """
    if k is None:
        return np.arange(len(comp))
    df = pd.DataFrame({"c": comp, "r": np.random.default_rng(seed).random(len(comp))})
    idx = df.sort_values(["c", "r"]).groupby("c", sort=False).head(k).index.to_numpy()
    return np.sort(idx)


def wald_ci(p: float, n: int) -> list[float]:
    """Normal-approximation 95% CI for a proportion.

    Args:
        p: Proportion.
        n: Sample size.

    Returns:
        [low, high].
    """
    h = 1.959964 * np.sqrt(p * (1 - p) / n) if n else float("nan")
    return [float(p - h), float(p + h)]


def wilson_ci(k: int, n: int) -> list[float]:
    """Wilson 95% CI for k successes out of n.

    Args:
        k: Successes.
        n: Trials.

    Returns:
        [low, high].
    """
    if n == 0:
        return [float("nan"), float("nan")]
    z = 1.959964
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [float(c - h), float(c + h)]


def macro_bootstrap(correct: np.ndarray, comp: np.ndarray, n_boot: int = 1000, seed: int = 42) -> dict[str, float]:
    """Macro accuracy (mean of per-component accuracy) with a component-bootstrap 95% CI.

    Args:
        correct: 1.0 / 0.0 per pair.
        comp: Component id per pair.
        n_boot: Bootstrap resamples.
        seed: Random seed.

    Returns:
        Dict with macro, ci_low, ci_high, n_components.
    """
    per = pd.Series(correct).groupby(comp).mean().to_numpy()
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    step = max(1, 2_000_000 // max(1, per.size))
    for s in range(0, n_boot, step):
        e = min(n_boot, s + step)
        boots[s:e] = per[rng.integers(0, per.size, (e - s, per.size))].mean(axis=1)
    return {"macro": float(per.mean()), "ci_low": float(np.percentile(boots, 2.5)),
            "ci_high": float(np.percentile(boots, 97.5)), "n_components": int(per.size)}
