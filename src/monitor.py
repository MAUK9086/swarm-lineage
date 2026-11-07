"""Metadata-only monitor features. Never receives text or text-derived values.

Inputs are post times and integer author codes for the whole timeline, plus agent
metadata (created_at, karma, follower / following counts).

File structure:
    Constants              synchrony window
    timeline_features      synchrony, interval, burstiness and hour-entropy features
    created_at_clustering  other agents created within +/-60 s and +/-1 h
    account_features       karma and follower / following counts
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from tqdm import tqdm

SYNC_S = 60.0


def timeline_features(t: np.ndarray, author: np.ndarray, authors: np.ndarray, sync_s: float = SYNC_S) -> pd.DataFrame:
    """Per-author timing features from the full timeline.

    Args:
        t: Post time in seconds for every post.
        author: Integer author code for every post.
        authors: Author codes to compute features for.
        sync_s: Half-width of the synchrony window in seconds.

    Returns:
        Frame indexed by author code.
    """
    g = np.sort(t)
    hour = np.floor(g / 3600).astype(np.int64)
    hours, hour_counts = np.unique(hour, return_counts=True)
    order = np.argsort(author, kind="stable")
    a_sorted = author[order]
    rows = []
    for a in tqdm(authors, desc="timeline features", unit="author"):
        lo, hi = np.searchsorted(a_sorted, a, "left"), np.searchsorted(a_sorted, a, "right")
        ta = np.sort(t[order[lo:hi]])
        n = len(ta)
        tot = np.searchsorted(g, ta + sync_s, "right") - np.searchsorted(g, ta - sync_s, "left")
        own = np.searchsorted(ta, ta + sync_s, "right") - np.searchsorted(ta, ta - sync_s, "left")
        other = tot - own
        hb = np.floor(ta / 3600).astype(np.int64)
        rate = hour_counts[np.searchsorted(hours, hb)] / 3600.0
        expected = rate * 2 * sync_s
        r: dict[str, float] = {
            "author": a,
            "sync_share_any": float((other > 0).mean()),
            "sync_mean_log1p": float(np.log1p(other).mean()),
            "sync_ratio_to_expected": float((other / np.maximum(expected, 1e-9)).mean()),
        }
        if n >= 2:
            iv = np.diff(ta)
            r["iv_median_log"] = float(np.median(np.log1p(iv)))
            r["iv_mean_log"] = float(np.log1p(iv).mean())
            r["iv_share_lt_60s"] = float((iv < 60).mean())
            r["iv_min_log"] = float(np.log1p(iv.min()))
        else:
            r.update({"iv_median_log": np.nan, "iv_mean_log": np.nan, "iv_share_lt_60s": np.nan, "iv_min_log": np.nan})
        if n >= 3:
            iv = np.diff(ta)
            mu, sd = iv.mean(), iv.std()
            r["iv_cv"] = float(sd / mu) if mu > 0 else np.nan
            r["burstiness"] = float((sd - mu) / (sd + mu)) if (sd + mu) > 0 else np.nan
        else:
            r.update({"iv_cv": np.nan, "burstiness": np.nan})
        hc = np.bincount(((ta // 3600) % 24).astype(np.int64), minlength=24)
        p = hc[hc > 0] / n
        r["hour_entropy"] = float(-(p * np.log(p)).sum() / np.log(24))
        r["n_posts"] = n
        rows.append(r)
    return pd.DataFrame(rows).set_index("author")


def created_at_clustering(created_s: pd.Series) -> pd.DataFrame:
    """Count other agents created within +/-60 s and +/-1 h of each agent.

    Args:
        created_s: Agent created_at in seconds (NaN if missing), indexed by agent id.

    Returns:
        Frame indexed by agent id with log1p counts and a missing flag.
    """
    ok = created_s.dropna()
    g = np.sort(ok.to_numpy())
    out = pd.DataFrame(index=created_s.index)
    out["created_missing"] = created_s.isna().astype(float)
    for name, w in (("created_within_60s_log1p", 60.0), ("created_within_1h_log1p", 3600.0)):
        c = np.searchsorted(g, ok.to_numpy() + w, "right") - np.searchsorted(g, ok.to_numpy() - w, "left") - 1
        out[name] = np.nan
        out.loc[ok.index, name] = np.log1p(c)
    return out


def account_features(agents: pd.DataFrame) -> pd.DataFrame:
    """Karma (signed log1p) and follower / following counts (log1p).

    Args:
        agents: Frame indexed by agent id with karma, follower_count, following_count.

    Returns:
        Frame indexed by agent id.
    """
    k = agents["karma"].astype(float)
    return pd.DataFrame({
        "karma_slog1p": np.sign(k) * np.log1p(np.abs(k)),
        "followers_log1p": np.log1p(agents["follower_count"].astype(float).clip(lower=0)),
        "following_log1p": np.log1p(agents["following_count"].astype(float).clip(lower=0)),
    }, index=agents.index)
