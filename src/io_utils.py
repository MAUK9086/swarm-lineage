"""Streaming reader and result-writing helpers shared by all experiments.

File structure:
    Constants       REPO_ROOT, RAW_PATH, INTERIM_DIR, RESULTS_DIR, FIGURES_DIR, SEED
    iter_rows       stream the corpus one JSON object at a time
    git_short_hash  short hash of HEAD, with a dirty flag
    now_ist         current time as an IST string
    save_result     write results/<name>.json with standard metadata
    append_summary  replace an experiment's rows in results/summary.csv
"""

from __future__ import annotations

import csv
import datetime as dt
import gzip
import subprocess
from pathlib import Path
from typing import Any, Iterator

import orjson

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = REPO_ROOT / "data" / "raw" / "redacted.jsonl.gz"
INTERIM_DIR = REPO_ROOT / "data" / "interim"
RESULTS_DIR = REPO_ROOT / "results"
FIGURES_DIR = REPO_ROOT / "figures"
SEED = 42

IST = dt.timezone(dt.timedelta(hours=5, minutes=30), name="IST")


def iter_rows(path: Path = RAW_PATH) -> Iterator[dict[str, Any]]:
    """Yield one parsed row at a time from the gzipped JSONL corpus.

    Args:
        path: Path to the .jsonl.gz file.

    Yields:
        The parsed JSON object for each non-empty line.

    Raises:
        orjson.JSONDecodeError: If a line is not valid JSON.
    """
    with gzip.open(path, "rb") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield orjson.loads(line)


def git_short_hash() -> str:
    """Return the short hash of HEAD, suffixed with '-dirty' if code has uncommitted changes.

    Only src/ and experiments/ count; results and the log change during normal runs.

    Returns:
        For example 'a1b2c3d' or 'a1b2c3d-dirty'; 'nogit' if git is unavailable.
    """
    try:
        h = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no", "--", "src", "experiments"],
            cwd=REPO_ROOT,
            text=True,
        ).strip()
        return h + ("-dirty" if dirty else "")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "nogit"


def now_ist() -> str:
    """Return the current time as 'YYYY-MM-DD HH:MM IST'.

    Returns:
        The formatted timestamp.
    """
    return dt.datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")


def save_result(name: str, payload: dict[str, Any], params: dict[str, Any]) -> Path:
    """Write a result file with run time, git hash, seed and parameters.

    Args:
        name: File stem, e.g. 'E00_profile'.
        payload: The experiment's numbers.
        params: Parameters used for the run.

    Returns:
        Path to the written JSON file.
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "experiment": name,
        "run_at": now_ist(),
        "git_hash": git_short_hash(),
        "seed": SEED,
        "params": params,
        "results": payload,
    }
    path = RESULTS_DIR / f"{name}.json"
    path.write_bytes(
        orjson.dumps(
            out,
            option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY,
        )
    )
    return path


def append_summary(experiment: str, metrics: dict[str, Any]) -> None:
    """Replace this experiment's rows in results/summary.csv.

    Args:
        experiment: Experiment id, e.g. 'E00'.
        metrics: Mapping of metric name to scalar value.
    """
    path = RESULTS_DIR / "summary.csv"
    rows: list[list[str]] = []
    if path.exists():
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))[1:]
    rows = [r for r in rows if r and r[0] != experiment]
    stamp, ghash = now_ist(), git_short_hash()
    rows += [[experiment, k, str(v), ghash, stamp] for k, v in metrics.items()]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["experiment", "metric", "value", "git_hash", "run_at"])
        w.writerows(rows)
