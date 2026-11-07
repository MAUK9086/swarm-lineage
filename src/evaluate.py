"""Evaluation code. The only module allowed to read the hidden time column t.

File structure:
    split_truth            standard table -> (public table without t, truth series)
    time_summary           parse rate and span of t (for profiling)
    pairwise_order_truth   for doc-id pairs, whether the first doc is truly earlier
    pairwise_accuracy      accuracy of 'first is earlier' predictions, bootstrap 95% CI
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.adapters import PUBLIC_COLUMNS, STANDARD_COLUMNS


def split_truth(table: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Separate the hidden time column from a standard table.

    Args:
        table: Standard table.

    Returns:
        (public table with PUBLIC_COLUMNS only, t indexed by doc_id)
    """
    if list(table.columns) != STANDARD_COLUMNS:
        raise ValueError("not a standard table")
    truth = pd.Series(table["t"].to_numpy(), index=table["doc_id"].to_numpy(), name="t")
    return table[PUBLIC_COLUMNS].copy(), truth


def time_summary(t: pd.Series) -> dict[str, Any]:
    """Summarise a time column: parse rate and span.

    Args:
        t: Timezone-aware datetime series (NaT for unparseable values).

    Returns:
        Dict with n, parsed, parse_rate, min, max, span_days.
    """
    ok = t.notna()
    out: dict[str, Any] = {"n": int(len(t)), "parsed": int(ok.sum()),
                           "parse_rate": float(ok.mean()) if len(t) else None}
    if ok.any():
        lo, hi = t[ok].min(), t[ok].max()
        out.update({"min": lo.isoformat(), "max": hi.isoformat(),
                    "span_days": (hi - lo).total_seconds() / 86400})
    return out


def pairwise_order_truth(truth: pd.Series, a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For pairs (a[i], b[i]), return whether a is truly earlier, and a validity mask.

    Pairs with equal or missing times are marked invalid.

    Args:
        truth: t indexed by doc_id.
        a: Doc ids of the first element of each pair.
        b: Doc ids of the second element of each pair.

    Returns:
        (a_earlier boolean array, valid boolean array)
    """
    ta = truth.reindex(a).to_numpy()
    tb = truth.reindex(b).to_numpy()
    valid = ~(pd.isna(ta) | pd.isna(tb))
    valid[valid] = ta[valid] != tb[valid]
    a_earlier = np.zeros(len(a), dtype=bool)
    a_earlier[valid] = ta[valid] < tb[valid]
    return a_earlier, valid


def pairwise_accuracy(pred_a_first: np.ndarray, a_earlier: np.ndarray, n_boot: int = 1000,
                      seed: int = 42) -> dict[str, Any]:
    """Accuracy of 'a came first' predictions with a percentile bootstrap 95% CI.

    Args:
        pred_a_first: Predicted booleans (True = a came first).
        a_earlier: True booleans for the same pairs.
        n_boot: Bootstrap resamples.
        seed: Random seed.

    Returns:
        Dict with n, accuracy, ci_low, ci_high.
    """
    correct = (pred_a_first == a_earlier).astype(float)
    n = len(correct)
    if n == 0:
        return {"n": 0, "accuracy": None, "ci_low": None, "ci_high": None}
    rng = np.random.default_rng(seed)
    boots = np.array([correct[rng.integers(0, n, n)].mean() for _ in range(n_boot)])
    return {"n": int(n), "accuracy": float(correct.mean()),
            "ci_low": float(np.percentile(boots, 2.5)), "ci_high": float(np.percentile(boots, 97.5))}
