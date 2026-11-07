"""Evaluation code. The only module allowed to read the hidden time column t.

File structure:
    split_truth            standard table -> (public table without t, truth series)
    time_summary           parse rate and span of t (for profiling)
    pairwise_order_truth   for doc-id pairs, whether the first doc is truly earlier
    pairwise_accuracy      accuracy of 'first is earlier' predictions, bootstrap 95% CI
    component_accuracy     macro accuracy over components, component bootstrap 95% CI
    spearman_with_truth    Spearman rho between a per-document value and t
    recall_at_fpr          recall at a fixed FPR (threshold from negatives)
    detection_metrics      AUROC and recall at 1% FPR with group-bootstrap CIs
    recall_fixed_threshold recall above a fixed threshold with a group-bootstrap CI
    truth_codes            hidden times per document code (int64 ns)
    order_from_codes       pair order truth from coded times
    null_order_draws       pair order truth under within-group permutation nulls
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


def component_accuracy(correct: np.ndarray, comp: np.ndarray, n_boot: int = 1000, seed: int = 42) -> dict[str, Any]:
    """Macro accuracy over components with a component bootstrap 95% CI.

    Args:
        correct: 1.0 / 0.0 per pair.
        comp: Component id per pair.
        n_boot: Bootstrap resamples (over components).
        seed: Random seed.

    Returns:
        Dict with n_components, n_pairs, macro, ci_low, ci_high, micro.
    """
    per = pd.Series(correct).groupby(comp).mean().to_numpy()
    if per.size == 0:
        return {"n_components": 0, "n_pairs": 0, "macro": None, "ci_low": None, "ci_high": None, "micro": None}
    rng = np.random.default_rng(seed)
    boots = np.array([per[rng.integers(0, per.size, per.size)].mean() for _ in range(n_boot)])
    return {"n_components": int(per.size), "n_pairs": int(len(correct)), "macro": float(per.mean()),
            "ci_low": float(np.percentile(boots, 2.5)), "ci_high": float(np.percentile(boots, 97.5)),
            "micro": float(np.mean(correct))}


def spearman_with_truth(values: np.ndarray, doc_ids: np.ndarray, truth: pd.Series) -> dict[str, Any]:
    """Spearman rho between a per-document value and the hidden time.

    Args:
        values: Numeric value per document.
        doc_ids: Doc id per value.
        truth: t indexed by doc_id.

    Returns:
        Dict with n, rho, p.
    """
    from scipy.stats import spearmanr

    t = truth.reindex(doc_ids)
    ok = t.notna().to_numpy()
    if ok.sum() < 3:
        return {"n": int(ok.sum()), "rho": None, "p": None}
    ns = pd.to_datetime(t[ok], utc=True).dt.tz_convert(None).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    r = spearmanr(values[ok], ns)
    return {"n": int(ok.sum()), "rho": float(r.statistic), "p": float(r.pvalue)}


def recall_at_fpr(y: np.ndarray, score: np.ndarray, fpr: float = 0.01) -> tuple[float, float]:
    """Recall at a fixed false-positive rate; threshold = (1 - fpr) quantile of negative scores.

    Args:
        y: 1 for positives, 0 for negatives.
        score: Model scores (higher = more positive).
        fpr: Target false-positive rate.

    Returns:
        (recall, threshold)
    """
    thr = float(np.quantile(score[y == 0], 1 - fpr))
    return float((score[y == 1] > thr).mean()), thr


def detection_metrics(y: np.ndarray, score: np.ndarray, groups: np.ndarray, n_boot: int = 1000,
                      seed: int = 42, fpr: float = 0.01) -> dict[str, Any]:
    """AUROC and recall at fpr, with 95% CIs from a bootstrap over groups.

    Args:
        y: Labels.
        score: Scores.
        groups: Group id per row (resampling unit).
        n_boot: Bootstrap resamples.
        seed: Random seed.
        fpr: False-positive rate for the recall metric.

    Returns:
        Dict with auroc, recall, threshold and their CIs.
    """
    from sklearn.metrics import roc_auc_score

    auc = float(roc_auc_score(y, score))
    rec, thr = recall_at_fpr(y, score, fpr)
    ug, inv = np.unique(groups, return_inverse=True)
    idx_by_group = [np.flatnonzero(inv == k) for k in range(len(ug))]
    rng = np.random.default_rng(seed)
    aucs, recs = [], []
    for _ in range(n_boot):
        pick = rng.integers(0, len(ug), len(ug))
        idx = np.concatenate([idx_by_group[k] for k in pick])
        yy, ss = y[idx], score[idx]
        if yy.min() == yy.max():
            continue
        aucs.append(roc_auc_score(yy, ss))
        recs.append(recall_at_fpr(yy, ss, fpr)[0])
    return {"auroc": auc, "auroc_ci": [float(np.percentile(aucs, 2.5)), float(np.percentile(aucs, 97.5))],
            "recall_at_1pct_fpr": rec, "recall_ci": [float(np.percentile(recs, 2.5)), float(np.percentile(recs, 97.5))],
            "threshold": thr, "n": int(len(y)), "n_pos": int(y.sum()), "n_groups": int(len(ug)),
            "boot_used": len(aucs)}


def recall_fixed_threshold(y: np.ndarray, score: np.ndarray, groups: np.ndarray, thr: float,
                           n_boot: int = 1000, seed: int = 42) -> dict[str, Any]:
    """Recall of positives above a fixed threshold, with a group-bootstrap 95% CI.

    Args:
        y: Labels (only positives are used).
        score: Scores.
        groups: Group id per row.
        thr: Fixed threshold.
        n_boot: Bootstrap resamples.
        seed: Random seed.

    Returns:
        Dict with recall and CI.
    """
    pos = y == 1
    hit = (score[pos] > thr).astype(float)
    g = groups[pos]
    per = pd.DataFrame({"g": g, "h": hit}).groupby("g")["h"].agg(["sum", "count"])
    s, c = per["sum"].to_numpy(), per["count"].to_numpy()
    rng = np.random.default_rng(seed)
    boots = [s[k].sum() / c[k].sum() for k in (rng.integers(0, len(per), len(per)) for _ in range(n_boot))]
    return {"recall": float(hit.mean()), "ci": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]}


def truth_codes(truth: pd.Series, doc_ids: np.ndarray) -> np.ndarray:
    """Hidden times for a list of documents as int64 nanoseconds (NaT -> min int64).

    Kept inside the evaluation module; callers only receive comparisons.

    Args:
        truth: t indexed by doc_id.
        doc_ids: Doc ids in code order.

    Returns:
        int64 array.
    """
    t = pd.to_datetime(truth.reindex(doc_ids), utc=True).dt.tz_convert(None)
    out = t.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    return out


def order_from_codes(tc: np.ndarray, a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For coded pairs, whether a is earlier, and a validity mask (unequal, non-missing times).

    Args:
        tc: Times per document code (int64 ns; NaT encoded as min int64).
        a: Codes of the first element.
        b: Codes of the second element.

    Returns:
        (a_earlier, valid)
    """
    nat = np.iinfo(np.int64).min
    ta, tb = tc[a], tc[b]
    valid = (ta != tb) & (ta != nat) & (tb != nat)
    return ta < tb, valid


def null_order_draws(truth: pd.Series, doc_ids: np.ndarray, doc_group: np.ndarray, a: np.ndarray, b: np.ndarray,
                     n_draws: int, seed: int = 42):
    """Yield (a_earlier, valid) under a null that permutes times within each group.

    Draw r uses seed + r. The permutation keeps each group's set of times and the
    cluster structure, and removes any real order signal between documents.

    Args:
        truth: t indexed by doc_id.
        doc_ids: Doc ids in code order.
        doc_group: Group (component) id per document code.
        a: Codes of the first element of each pair.
        b: Codes of the second element of each pair.
        n_draws: Number of draws.
        seed: Base seed.

    Yields:
        (a_earlier, valid) boolean arrays per draw.
    """
    tc = truth_codes(truth, doc_ids)
    base = np.argsort(doc_group, kind="stable")
    t_by_group = tc[base]
    for r in range(n_draws):
        key = np.random.default_rng(seed + r).random(len(tc))
        order = np.lexsort((key, doc_group))
        perm = np.empty_like(tc)
        perm[order] = t_by_group
        yield order_from_codes(perm, a, b)
