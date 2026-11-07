"""Adapter stub for the collusion.wiki export (revisions.jsonl). Not run in this repo.

The user runs the frozen pipeline on this corpus themselves.

Mapping to the standard table:
    doc_id    <- rev_id (contains "@seq", which leaks order; method code must treat it
                 as opaque; the runner may replace it with a random key)
    text      <- body
    group_id  <- page_id
    author_id <- label
    t         <- time (UTC)

File structure:
    to_standard   raw revisions frame -> standard table
"""

from __future__ import annotations

import pandas as pd

from src.adapters import STANDARD_COLUMNS, validate_standard


def to_standard(raw: pd.DataFrame) -> pd.DataFrame:
    """Convert a raw revisions frame to the standard table.

    Args:
        raw: Frame read from revisions.jsonl (rev_id, body, page_id, label, time).

    Returns:
        Standard table (doc_id, text, group_id, author_id, t).
    """
    out = pd.DataFrame(
        {
            "doc_id": raw["rev_id"].astype(str),
            "text": raw["body"].fillna("").astype(str),
            "group_id": raw["page_id"].astype(str),
            "author_id": raw["label"].fillna("").astype(str),
            "t": pd.to_datetime(raw["time"], utc=True, errors="coerce"),
        }
    )[STANDARD_COLUMNS]
    validate_standard(out)
    return out
