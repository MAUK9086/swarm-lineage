"""Adapter for the Moltbook observatory archive (posts subset).

Mapping to the standard table:
    doc_id    <- id
    text      <- title + blank line + content (missing parts become "")
    group_id  <- submolt
    author_id <- agent_id (falls back to "name:" + agent_name when agent_id is missing)
    t         <- created_at (UTC)

fetched_at, dump_date, score, comment_count and is_pinned are dropped: the first two
are collection times and would leak order.

File structure:
    POSTS_COLUMNS   raw columns the adapter reads
    post_text       build the text field for one raw frame
    author_ids      build author_id for one raw frame
    to_standard     raw posts frame -> standard table
"""

from __future__ import annotations

import pandas as pd

from src.adapters import STANDARD_COLUMNS, validate_standard

POSTS_COLUMNS = ["id", "agent_id", "agent_name", "submolt", "title", "content", "created_at"]


def post_text(raw: pd.DataFrame) -> pd.Series:
    """Combine title and content into one text field.

    Args:
        raw: Raw posts frame with title and content columns.

    Returns:
        Series of strings.
    """
    title = raw["title"].fillna("").astype(str)
    content = raw["content"].fillna("").astype(str)
    both = (title != "") & (content != "")
    return (title + pd.Series("\n\n", index=raw.index).where(both, "") + content).astype(str)


def author_ids(raw: pd.DataFrame) -> pd.Series:
    """Return agent_id, falling back to the agent name when the id is missing.

    Args:
        raw: Raw posts frame with agent_id and agent_name columns.

    Returns:
        Series of author labels (may still be null when both are missing).
    """
    fallback = "name:" + raw["agent_name"].astype("string")
    return raw["agent_id"].astype("string").fillna(fallback)


def to_standard(raw: pd.DataFrame) -> pd.DataFrame:
    """Convert a raw posts frame (already deduplicated by id) to the standard table.

    Args:
        raw: Raw posts frame containing POSTS_COLUMNS.

    Returns:
        Standard table (doc_id, text, group_id, author_id, t).

    Raises:
        ValueError: If the result fails validation.
    """
    out = pd.DataFrame(
        {
            "doc_id": raw["id"].astype(str).to_numpy(),
            "text": post_text(raw).to_numpy(),
            "group_id": raw["submolt"].astype("string").to_numpy(),
            "author_id": author_ids(raw).to_numpy(),
            "t": pd.to_datetime(raw["created_at"], utc=True, errors="coerce").to_numpy(),
        }
    )
    out["t"] = pd.to_datetime(out["t"], utc=True)
    out = out[STANDARD_COLUMNS]
    validate_standard(out)
    return out
