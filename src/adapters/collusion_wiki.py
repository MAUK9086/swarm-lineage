"""Adapter for the collusion.wiki export (collusion_slim.parquet).

Mapping to the standard table:
    doc_id    <- rev_id
    text      <- body
    group_id  <- page_id
    author_id <- label (falls back to "blank_" + rev_id when label is blank)
    t         <- t_utc (UTC, ns precision)
"""

from __future__ import annotations

import pandas as pd

from src.adapters import STANDARD_COLUMNS, validate_standard


def to_standard(raw: pd.DataFrame) -> pd.DataFrame:
    """Convert a raw revisions frame to the standard table."""
    label = raw["label"].fillna("").astype(str).str.strip()
    author = label.where(label != "", "blank_" + raw["rev_id"].astype(str))
    t_col = "t_utc" if "t_utc" in raw.columns else "time"
    out = pd.DataFrame(
        {
            "doc_id": raw["rev_id"].astype(str),
            "text": raw["body"].fillna("").astype(str),
            "group_id": raw["page_id"].astype(str),
            "author_id": author,
            "t": pd.to_datetime(raw[t_col], utc=True, errors="coerce").dt.as_unit("ns"),
        }
    )[STANDARD_COLUMNS]
    validate_standard(out)
    return out


def build(
    src: str = "data/interim/collusion_slim.parquet",
    out: str = "data/interim/collusion_standard.parquet",
) -> pd.DataFrame:
    """Read collusion_slim.parquet, validate standard schema, and write Parquet."""
    df = pd.read_parquet(src, columns=["rev_id", "body", "page_id", "label", "t_utc"])
    std = to_standard(df)
    std.to_parquet(out, index=False)
    return std


if __name__ == "__main__":
    build()