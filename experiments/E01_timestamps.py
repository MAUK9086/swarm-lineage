"""E01 - Coverage, source and span of time estimates in the corpus.

Reads the slim Parquet from E00. Works unchanged if a later corpus version fills
time_utc; with no parseable times it records the null result and skips the figure.

File structure:
    Constants   parameters
    main        count, parse, summarise, plot (if possible), save results
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.io_utils import FIGURES_DIR, INTERIM_DIR, append_summary, save_result  # noqa: E402

GO_MIN_ROWS = 100
HIST_BIN = "1h"
PARQUET = INTERIM_DIR / "corpus_slim.parquet"


def main() -> None:
    """Run E01 and write results/E01_timestamps.json."""
    all_cols = pq.read_schema(PARQUET).names
    df = pd.read_parquet(PARQUET, columns=["id", "kind", "time_utc"])
    raw = df["time_utc"]
    parsed = pd.to_datetime(raw, utc=True, errors="coerce")
    non_null = raw.notna()
    ok = parsed.notna()

    per_kind = {
        k: {"rows": int((df["kind"] == k).sum()),
            "non_null": int((non_null & (df["kind"] == k)).sum()),
            "parsed": int((ok & (df["kind"] == k)).sum())}
        for k in sorted(df["kind"].unique())
    }
    res = {
        "n_rows": int(len(df)),
        "time_columns": [c for c in all_cols if re.search(r"time|date", c, re.I)],
        "source_or_provenance_columns": [c for c in all_cols if re.search(r"source|provenance|method|origin", c, re.I)],
        "non_null": int(non_null.sum()),
        "parsed": int(ok.sum()),
        "unparseable": int((non_null & ~ok).sum()),
        "share_with_time": float(ok.mean()),
        "per_kind": per_kind,
        "span": None,
        "figure": None,
    }
    if ok.any():
        t = parsed[ok]
        res["span"] = {"min": t.min().isoformat(), "max": t.max().isoformat(),
                       "hours": (t.max() - t.min()).total_seconds() / 3600}
        counts = t.dt.floor(HIST_BIN).value_counts().sort_index()
        FIGURES_DIR.mkdir(parents=True, exist_ok=True)
        fig, ax = plt.subplots(figsize=(9, 3.5))
        ax.bar(counts.index, counts.values, width=1 / 24)
        ax.set_xlabel("time (UTC)")
        ax.set_ylabel("rows per hour")
        ax.set_title(f"E01: rows with a time estimate (n={int(ok.sum())})")
        fig.tight_layout()
        fig.savefig(FIGURES_DIR / "E01_time_hist.png", dpi=150)
        res["figure"] = "figures/E01_time_hist.png"
    res["go"] = res["parsed"] >= GO_MIN_ROWS

    save_result("E01_timestamps", res, {"go_min_rows": GO_MIN_ROWS, "hist_bin": HIST_BIN, "sampling": "none"})
    append_summary("E01", {"rows_with_time": res["parsed"], "share_with_time": res["share_with_time"],
                           "unparseable": res["unparseable"], "go": res["go"]})
    print({k: res[k] for k in ("non_null", "parsed", "unparseable", "time_columns",
                                "source_or_provenance_columns", "span", "go")})


if __name__ == "__main__":
    main()
