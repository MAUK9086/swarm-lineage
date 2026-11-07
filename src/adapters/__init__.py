"""Corpus adapters. Each adapter outputs the standard table defined here.

Standard table columns:
    doc_id     str   opaque document id (method code must not read order from it)
    text       str   document text
    group_id   str   grouping unit (submolt, wiki page, ...)
    author_id  str   author label
    t          datetime64[ns, UTC]   true time; hidden, read only by src/evaluate.py

File structure:
    STANDARD_COLUMNS   column order of the standard table
    PUBLIC_COLUMNS     the columns method code may see (no t)
    validate_standard  check a frame has the standard columns and dtypes
"""

from __future__ import annotations

import pandas as pd

STANDARD_COLUMNS = ["doc_id", "text", "group_id", "author_id", "t"]
PUBLIC_COLUMNS = ["doc_id", "text", "group_id", "author_id"]


def validate_standard(df: pd.DataFrame) -> None:
    """Raise if a frame is not a valid standard table.

    Args:
        df: Candidate standard table.

    Raises:
        ValueError: If columns are missing, extra, or doc_id is not unique.
    """
    if list(df.columns) != STANDARD_COLUMNS:
        raise ValueError(f"expected columns {STANDARD_COLUMNS}, got {list(df.columns)}")
    if not df["doc_id"].is_unique:
        raise ValueError("doc_id is not unique")
    if not isinstance(df["t"].dtype, pd.DatetimeTZDtype):
        raise ValueError("t must be a timezone-aware datetime column")
