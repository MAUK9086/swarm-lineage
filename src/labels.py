"""Content-derived labels for the coordination monitor. The only E37 code that sees text.

File structure:
    Constants             label window and author threshold
    norm_hash             64-bit hash of normalised text (same rule as E30)
    marked_posts          posts inside a 24 h window holding >= 3 distinct authors of one text
    duplicate_components  author components linked by any shared exact-duplicate text
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter

import numpy as np
import pandas as pd
from tqdm import tqdm

WINDOW_S = 24 * 3600
MIN_AUTHORS = 3
WS_RE = re.compile(r"\s+")


def norm_hash(s: str) -> int:
    """Hash of whitespace-collapsed, lower-cased text; 0 marks an empty text.

    Args:
        s: Text.

    Returns:
        Signed 64-bit integer.
    """
    n = WS_RE.sub(" ", s).strip().lower()
    if not n:
        return 0
    return int.from_bytes(hashlib.blake2b(n.encode("utf-8"), digest_size=8).digest(), "little", signed=True) or 1


def marked_posts(h: np.ndarray, t: np.ndarray, author: np.ndarray,
                 window_s: float = WINDOW_S, min_authors: int = MIN_AUTHORS) -> np.ndarray:
    """Mark posts that fall in a window of length window_s holding >= min_authors authors of one text.

    Args:
        h: Text hash per post (0 = empty, ignored).
        t: Post time in seconds.
        author: Integer author code per post.
        window_s: Window length in seconds.
        min_authors: Distinct authors required in the window.

    Returns:
        Boolean mask over posts.
    """
    df = pd.DataFrame({"h": h, "a": author, "pos": np.arange(len(h))})
    df = df[df["h"] != 0]
    n_auth = df.groupby("h")["a"].nunique()
    cand = n_auth[n_auth >= min_authors].index
    df = df[df["h"].isin(cand)].copy()
    df["t"] = t[df["pos"].to_numpy()]
    df = df.sort_values(["h", "t"])
    mark = np.zeros(len(h), dtype=bool)
    for _, g in tqdm(df.groupby("h", sort=False), total=len(cand), desc="label windows", unit="text"):
        tt, aa, pp = g["t"].to_numpy(), g["a"].to_numpy(), g["pos"].to_numpy()
        n = len(tt)
        cover = np.zeros(n + 1, dtype=np.int64)
        cnt: Counter[int] = Counter()
        j = 0
        for i in range(n):
            while j < n and tt[j] - tt[i] <= window_s:
                cnt[aa[j]] += 1
                j += 1
            if len(cnt) >= min_authors:
                cover[i] += 1
                cover[j] -= 1
            cnt[aa[i]] -= 1
            if cnt[aa[i]] == 0:
                del cnt[aa[i]]
        covered = np.cumsum(cover[:-1]) > 0
        mark[pp[covered]] = True
    return mark


def duplicate_components(h: np.ndarray, author: np.ndarray, n_authors: int) -> np.ndarray:
    """Connected components of authors linked by any exact-duplicate text with >= 2 authors.

    Args:
        h: Text hash per post (0 = empty, ignored).
        author: Integer author code per post (0..n_authors-1).
        n_authors: Number of authors.

    Returns:
        Component id per author.
    """
    parent = np.arange(n_authors)

    def find(x: int) -> int:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    df = pd.DataFrame({"h": h, "a": author})
    df = df[df["h"] != 0].drop_duplicates()
    multi = df.groupby("h")["a"].nunique()
    df = df[df["h"].isin(multi[multi >= 2].index)]
    for _, g in tqdm(df.groupby("h", sort=False), total=int((multi >= 2).sum()), desc="author components", unit="text"):
        a = g["a"].to_numpy()
        r0 = find(int(a[0]))
        for x in a[1:]:
            rx = find(int(x))
            if rx != r0:
                parent[rx] = r0
    return np.array([find(x) for x in range(n_authors)])
