"""E02 - Spearman correlation between row id number and time estimate.

Reads the slim Parquet from E00. If fewer than MIN_N rows have both an id number and
a parseable time, the result is recorded as not computable.

File structure:
    Constants   parameters
    spearman    rho and p-value for one subset, or a not-computable marker
    main        overall and per-kind correlation, save results
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.io_utils import INTERIM_DIR, append_summary, save_result  # noqa: E402

MIN_N = 30
RHO_THRESHOLD = 0.5
P_THRESHOLD = 0.01
PARQUET = INTERIM_DIR / "corpus_slim.parquet"


def spearman(sub: pd.DataFrame) -> dict[str, Any]:
    """Compute Spearman rho between id_num and time for one subset.

    Args:
        sub: Frame with columns id_num and t (parsed UTC times, no nulls).

    Returns:
        Dict with n, rho, p and computable flag.
    """
    n = int(len(sub))
    if n < MIN_N:
        return {"n": n, "computable": False, "rho": None, "p": None}
    r = spearmanr(sub["id_num"], sub["t"].astype("int64"))
    return {"n": n, "computable": True, "rho": float(r.statistic), "p": float(r.pvalue)}


def main() -> None:
    """Run E02 and write results/E02_leakage.json."""
    df = pd.read_parquet(PARQUET, columns=["id_num", "kind", "time_utc"])
    df["t"] = pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
    both = df.dropna(subset=["id_num", "t"])
    overall = spearman(both)
    per_kind = {k: spearman(g) for k, g in both.groupby("kind")}
    leak = None
    if overall["computable"]:
        leak = abs(overall["rho"]) >= RHO_THRESHOLD and overall["p"] < P_THRESHOLD
    res = {"rows_with_id_and_time": int(len(both)), "overall": overall,
           "per_kind": per_kind, "id_order_leaks_time": leak}
    save_result("E02_leakage", res, {"min_n": MIN_N, "rho_threshold": RHO_THRESHOLD,
                                     "p_threshold": P_THRESHOLD, "sampling": "none"})
    append_summary("E02", {"n": overall["n"], "computable": overall["computable"],
                           "rho": overall["rho"], "p": overall["p"], "leak": leak})
    print(res)


if __name__ == "__main__":
    main()
