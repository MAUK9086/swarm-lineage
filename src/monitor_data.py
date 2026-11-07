"""Data loading and label building shared by the monitor experiments (E38 onward).

The loaders and feature builder are copied unchanged from E37 so later experiments do
not import from an experiment script.

File structure:
    Constants       raw data path, label thresholds
    load_posts      author, time and text hash for every post (text dropped per file)
    load_agents     deduplicated agent metadata
    build_features  timeline + created_at + account features for a set of authors
    build_labels    coordinated flag, post counts and duplicate components for all authors
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from tqdm import tqdm

from src.adapters.moltbook import author_ids, post_text
from src.io_utils import REPO_ROOT
from src.labels import duplicate_components, marked_posts, norm_hash
from src.monitor import timeline_features

RAW = REPO_ROOT / "data" / "raw" / "moltbook" / "data"


def load_posts() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Author, time (s) and normalised-text hash for every post; text is not kept.

    Returns:
        (author string array, time float64 seconds, hash int64)
    """
    authors, times, hashes = [], [], []
    for p in tqdm(sorted((RAW / "posts").glob("*.parquet")), desc="posts", unit="file"):
        raw = pq.read_table(p, columns=["id", "agent_id", "agent_name", "title", "content", "created_at"]).to_pandas()
        raw = raw.drop_duplicates("id")
        text = post_text(raw)
        hashes.append(np.fromiter((norm_hash(s) for s in text), dtype=np.int64, count=len(text)))
        del text
        authors.append(author_ids(raw).to_numpy(dtype=object))
        t = pd.to_datetime(raw["created_at"], utc=True).dt.tz_convert(None).to_numpy(dtype="datetime64[ns]")
        times.append(t.astype(np.int64) / 1e9)
    a, t, h = np.concatenate(authors), np.concatenate(times), np.concatenate(hashes)
    ok = pd.notna(a) & np.isfinite(t)
    return a[ok], t[ok], h[ok]


def load_agents() -> pd.DataFrame:
    """Latest snapshot of every agent: created_at (s), karma, follower / following counts.

    Returns:
        Frame indexed by agent id.
    """
    parts = []
    for k, p in enumerate(sorted((RAW / "agents").glob("*.parquet"))):
        df = pq.read_table(p, columns=["id", "karma", "follower_count", "following_count", "created_at",
                                       "dump_date"]).to_pandas()
        df["_f"] = k
        parts.append(df)
    d = pd.concat(parts).sort_values(["dump_date", "_f"]).drop_duplicates("id", keep="last").set_index("id")
    c = pd.to_datetime(d["created_at"], utc=True).dt.tz_convert(None)
    d["created_s"] = c.to_numpy(dtype="datetime64[ns]").astype(np.int64) / 1e9
    d.loc[c.isna().to_numpy(), "created_s"] = np.nan
    return d


def build_features(t: np.ndarray, codes: np.ndarray, sample: np.ndarray, uniques: np.ndarray,
                   agent_static: pd.DataFrame) -> pd.DataFrame:
    """Feature frame for the sampled authors.

    Args:
        t: Post times (s), whole timeline.
        codes: Author code per post.
        sample: Author codes to featurise.
        uniques: Author string per code.
        agent_static: created_at clustering + account features indexed by agent id.

    Returns:
        Frame indexed by author code with FEATURES and n_posts.
    """
    tl = timeline_features(t, codes, sample)
    ids = pd.Index(uniques[tl.index.to_numpy()])
    static = agent_static.reindex(ids)
    static.index = tl.index
    static["created_missing"] = static["created_missing"].fillna(1.0)
    return tl.join(static)


def build_labels() -> dict[str, Any]:
    """Labels and components for every author (content used here only, then dropped).

    Returns:
        Dict with codes (per post), t (per post, s), uniques (author id per code),
        coord (bool per author), n_posts (per author), comp (component per author),
        marked_posts (count).
    """
    a_str, t, h = load_posts()
    codes, uniques = pd.factorize(a_str)
    uniques = np.asarray(uniques, dtype=object)
    n_auth = len(uniques)
    mark = marked_posts(h, t, codes)
    coord = np.zeros(n_auth, dtype=bool)
    coord[np.unique(codes[mark])] = True
    n_posts = np.bincount(codes, minlength=n_auth)
    comp = duplicate_components(h, codes, n_auth)
    del h
    return {"codes": codes, "t": t, "uniques": uniques, "coord": coord, "n_posts": n_posts, "comp": comp,
            "marked_posts": int(mark.sum())}
