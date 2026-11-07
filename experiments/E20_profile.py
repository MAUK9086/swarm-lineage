"""E20 - Profile the collusion.wiki export and write a slim revision Parquet.

Reads manifest.json first (date cut, counts, self-checks), verifies SHA256SUMS, then
profiles each data file and analyses the revision histories. Committed results hold
aggregates and ids only; per-field example values (truncated) go to an untracked file
under data/interim.

File structure:
    Constants         paths, thresholds, plot colours
    find_file         locate a data file (.jsonl or .jsonl.gz) under the corpus dir
    read_jsonl        read a JSONL file into a list of dicts, with a progress bar
    profile_fields    per-field presence / type / distinct stats and examples
    manifest_summary  cut, counts and self-checks from manifest.json, plus SHA256SUMS
    revision_stats    timestamps, revisions per page / label, prev links, lengths, hashes
    deletion_stats    share of held pages deleted after their first revision
    plot_daily        daily revision histogram to figures/
    write_parquet     slim revision table to data/interim/collusion_slim.parquet
    main              run everything, apply the GO rule, save results
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from tqdm import tqdm  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.io_utils import (  # noqa: E402
    FIGURES_DIR,
    INTERIM_DIR,
    REPO_ROOT,
    append_summary,
    save_result,
)

CORPUS_DIR = REPO_ROOT / "data" / "raw" / "collusion"
DATA_FILES = ("pages", "revisions", "events", "labels")
EXAMPLE_TRUNC = 80
N_EXAMPLES = 3
LOW_CARD_MAX = 30
# Fields never given value counts in committed results (names, labels, IPs, free text).
NO_VALUE_COUNTS = ("ip", "label", "name", "body", "summary", "note", "source", "path", "sha")
GO_MIN_TIMED_REVISIONS = 5000
GO_MIN_PAGES_5PLUS = 200
ISO_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
PCTS = (1, 5, 25, 50, 75, 95, 99)

COLOR_BAR = "#2a78d6"
COLOR_SURFACE = "#fcfcfb"
COLOR_TEXT = "#0b0b0b"
COLOR_TEXT_2 = "#52514e"
COLOR_GRID = "#e4e3df"


def find_file(stem: str) -> Path:
    """Locate <stem>.jsonl or <stem>.jsonl.gz anywhere under CORPUS_DIR.

    Args:
        stem: File stem, e.g. 'revisions'.

    Returns:
        Path to the file.

    Raises:
        FileNotFoundError: If neither variant exists.
    """
    for pattern in (f"{stem}.jsonl", f"{stem}.jsonl.gz"):
        hits = sorted(CORPUS_DIR.rglob(pattern))
        if hits:
            return hits[0]
    raise FileNotFoundError(f"{stem}.jsonl(.gz) not found under {CORPUS_DIR}")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL (optionally gzipped) file line by line.

    Args:
        path: File path.

    Returns:
        List of parsed rows.
    """
    opener = gzip.open if path.suffix == ".gz" else open
    rows = []
    with opener(path, "rt", encoding="utf-8") as fh:
        for line in tqdm(fh, desc=f"read {path.name}", unit="rows"):
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _type_name(v: Any) -> str:
    """Return a JSON-style type name.

    Args:
        v: Parsed JSON value.

    Returns:
        Type name string.
    """
    if v is None:
        return "null"
    return {bool: "bool", int: "int", float: "float", str: "str", list: "list", dict: "dict"}[type(v)]


def _trunc(v: Any) -> str:
    """Render a value truncated to EXAMPLE_TRUNC characters.

    Args:
        v: Parsed JSON value.

    Returns:
        Truncated string.
    """
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return s if len(s) <= EXAMPLE_TRUNC else s[:EXAMPLE_TRUNC] + "..."


def profile_fields(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Per-field stats for one file.

    Args:
        rows: Parsed rows of the file.

    Returns:
        (committed stats per field, untracked examples per field)
    """
    n = len(rows)
    order: list[str] = []
    for r in rows:
        for k in r:
            if k not in order:
                order.append(k)
    stats: dict[str, Any] = {}
    examples: dict[str, list[str]] = {}
    for k in order:
        present = non_null = 0
        types: Counter[str] = Counter()
        distinct: set[str] = set()
        ex: list[str] = []
        scalar_values: Counter[str] = Counter()
        for r in rows:
            if k not in r:
                continue
            present += 1
            v = r[k]
            types[_type_name(v)] += 1
            if v is None:
                continue
            non_null += 1
            key = v if isinstance(v, str) else json.dumps(v, sort_keys=True)
            distinct.add(key)
            if isinstance(v, (str, bool, int)):
                scalar_values[str(v)] += 1
            if len(ex) < N_EXAMPLES and v not in ("", [], {}) and _trunc(v) not in ex:
                ex.append(_trunc(v))
        s = {
            "present": present,
            "present_rate": present / n,
            "non_null": non_null,
            "non_null_rate": non_null / n,
            "types": dict(types),
            "distinct": len(distinct),
        }
        if len(distinct) <= LOW_CARD_MAX and not any(t in k.lower() for t in NO_VALUE_COUNTS):
            s["value_counts"] = dict(scalar_values.most_common())
        stats[k] = s
        examples[k] = ex
    return {"rows": n, "fields": stats}, examples


def manifest_summary(manifest_path: Path) -> dict[str, Any]:
    """Summarise manifest.json and verify SHA256SUMS next to it.

    Args:
        manifest_path: Path to manifest.json.

    Returns:
        Dict with generated_at, cut, counts, checks and checksum verification.
    """
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    checks = m.get("checks", [])
    out = {
        "top_level_keys": list(m.keys()),
        "generated_at": m.get("generated_at"),
        "cut": m.get("cut"),
        "counts": {k: v.get("value") for k, v in m.get("counts", {}).items()},
        "per_wiki": {w: {k: v.get("value") for k, v in d.items()} for w, d in m.get("per_wiki", {}).items()},
        "population_counts": {
            k: v.get("value") for k, v in m.get("population_counts", {}).items() if isinstance(v, dict)
        },
        "n_checks": len(checks),
        "n_checks_ok": sum(1 for c in checks if c.get("ok") is True),
        "checks": [
            {"name": c.get("name"), "expected": c.get("expected"), "actual": c.get("actual"), "ok": c.get("ok")}
            for c in checks
        ],
    }
    sums = manifest_path.parent / "SHA256SUMS"
    verify = {}
    if sums.exists():
        for line in sums.read_text().splitlines():
            if not line.strip():
                continue
            digest, name = line.split(maxsplit=1)
            f = manifest_path.parent / name.strip().lstrip("*")
            verify[name.strip()] = (
                hashlib.sha256(f.read_bytes()).hexdigest() == digest if f.exists() else "missing"
            )
    out["sha256sums_verified"] = verify
    return out


def _pcts(a: np.ndarray) -> dict[str, float]:
    """Percentiles plus min/mean/max of an array.

    Args:
        a: Numeric array (non-empty).

    Returns:
        Dict of summary statistics.
    """
    d = {f"p{p}": float(np.percentile(a, p)) for p in PCTS}
    d.update({"min": float(a.min()), "mean": float(a.mean()), "max": float(a.max())})
    return d


def revision_stats(rev: pd.DataFrame, pages: pd.DataFrame) -> dict[str, Any]:
    """Analyse revisions: timestamps, histories, prev links, lengths and hashes.

    Args:
        rev: Revisions frame (with a parsed 't' column).
        pages: Pages frame.

    Returns:
        Dict of aggregate statistics.
    """
    out: dict[str, Any] = {}
    times = rev["time"]
    ok = rev["t"].notna()
    out["timestamp"] = {
        "field": "time",
        "non_null": int(times.notna().sum()),
        "format_iso8601_utc_z": int(times.dropna().map(lambda s: bool(ISO_Z_RE.match(str(s)))).sum()),
        "parsed": int(ok.sum()),
        "parse_rate": float(ok.mean()),
        "min": rev.loc[ok, "t"].min().isoformat() if ok.any() else None,
        "max": rev.loc[ok, "t"].max().isoformat() if ok.any() else None,
        "span_days": float((rev.loc[ok, "t"].max() - rev.loc[ok, "t"].min()).total_seconds() / 86400)
        if ok.any()
        else None,
        "time_grade_counts": rev["time_grade"].value_counts(dropna=False).to_dict()
        if "time_grade" in rev
        else None,
        "n_days_with_revisions": int(rev.loc[ok, "t"].dt.floor("D").nunique()),
    }

    per_page = rev.groupby("page_id").size()
    out["revisions_per_page"] = {
        "pages": int(per_page.size),
        **_pcts(per_page.to_numpy()),
        **{f"pages_ge_{k}": int((per_page >= k).sum()) for k in (2, 3, 5, 10, 20, 50)},
        "revisions_on_pages_ge_5": int(per_page[per_page >= 5].sum()),
    }
    if "n_revs" in pages and "page_id" in pages:
        merged = pages.set_index("page_id")["n_revs"].reindex(per_page.index)
        out["revisions_per_page"]["agrees_with_pages_n_revs"] = int((merged == per_page).sum())

    lab = rev["label"].fillna("")
    per_label = lab[lab != ""].value_counts()
    out["revisions_per_label"] = {
        "distinct_non_blank_labels": int(per_label.size),
        "blank_label_revisions": int((lab == "").sum()),
        **(_pcts(per_label.to_numpy()) if per_label.size else {}),
        **{f"labels_ge_{k}": int((per_label >= k).sum()) for k in (2, 5, 10, 50)},
        "share_of_labelled_revisions_by_top_10_labels": float(per_label.head(10).sum() / per_label.sum())
        if per_label.size
        else None,
    }

    # Previous-revision links.
    expected_prev = rev["page_key"] + "@" + (rev["seq"] - 1).astype(str)
    later = rev["seq"] > 1
    same_page_ids = set(rev["rev_id"])
    db = rev["diff_base"]
    page_of = dict(zip(rev["rev_id"], rev["page_id"]))
    out["prev_link"] = {
        "field": "diff_base",
        "revisions_seq_gt_1": int(later.sum()),
        "seq_gt_1_diff_base_null": int((later & db.isna()).sum()),
        "seq_gt_1_diff_base_eq_prev_seq": int((later & (db == expected_prev)).sum()),
        "seq_gt_1_diff_base_other_rev_same_page": int(
            sum(
                1
                for d, e, p, l in zip(db, expected_prev, rev["page_id"], later)
                if l and d is not None and d != e and page_of.get(d) == p
            )
        ),
        "seq_gt_1_diff_base_not_in_export": int(
            sum(1 for d, l in zip(db, later) if l and d is not None and d not in same_page_ids)
        ),
        "seq_1_diff_base_non_null": int(((~later) & db.notna()).sum()),
        "diff_base_reason_counts": rev["diff_base_reason"].value_counts(dropna=False).to_dict(),
    }
    # Is seq contiguous and does it agree with time order? (seq is a time proxy too.)
    s = rev.sort_values(["page_id", "seq"])
    gaps = s.groupby("page_id")["seq"].apply(lambda x: bool((np.diff(x.to_numpy()) == 1).all()))
    dt_ = s.groupby("page_id")["t"].diff().dropna()
    out["seq_order"] = {
        "pages_with_contiguous_seq": int(gaps.sum()),
        "pages_starting_at_seq_1": int((s.groupby("page_id")["seq"].min() == 1).sum()),
        "consecutive_pairs": int(dt_.size),
        "pairs_time_increasing": int((dt_ > pd.Timedelta(0)).sum()),
        "pairs_time_equal": int((dt_ == pd.Timedelta(0)).sum()),
        "pairs_time_decreasing": int((dt_ < pd.Timedelta(0)).sum()),
    }

    clen = rev["body"].fillna("").str.len().to_numpy()
    out["text_length"] = {
        "chars": _pcts(clen),
        "body_len_field": _pcts(rev["body_len"].to_numpy()) if "body_len" in rev else None,
        "empty_bodies": int((clen == 0).sum()),
    }

    def sha(b: Any) -> str:
        return hashlib.sha256((b or "").encode("utf-8")).hexdigest()

    recomputed = rev["body"].map(sha)
    by_hash_pages = rev.groupby("body_sha256")["page_id"].nunique()
    out["exact_texts"] = {
        "revisions": int(len(rev)),
        "distinct_body_sha256": int(rev["body_sha256"].nunique()),
        "body_sha256_matches_utf8_recompute": int((recomputed == rev["body_sha256"]).sum()),
        "hashes_on_more_than_one_page": int((by_hash_pages > 1).sum()),
        "revisions_whose_text_appears_on_another_page": int(
            rev["body_sha256"].map(by_hash_pages).gt(1).sum()
        ),
        "within_page_repeats": int(len(rev) - rev.groupby(["page_id", "body_sha256"]).ngroups),
    }
    return out


def deletion_stats(events: pd.DataFrame, pages: pd.DataFrame) -> dict[str, Any]:
    """Share of held pages with a delete event after their first revision.

    Args:
        events: Events frame.
        pages: Pages frame.

    Returns:
        Dict of counts and shares.
    """
    out: dict[str, Any] = {"event_type_counts": events["event_type"].value_counts().to_dict()}
    dels = events[events["event_type"] == "delete"].copy()
    dels["t"] = pd.to_datetime(dels["time"], utc=True, errors="coerce", format="ISO8601")
    first = pages.set_index("page_key")["first_write"]
    first_t = pd.to_datetime(first, utc=True, errors="coerce", format="ISO8601")
    dels["first_write_t"] = dels["page_key"].map(first_t)
    held = dels["page_key"].isin(first_t.index)
    later = held & (dels["t"] > dels["first_write_t"])
    n_pages = int(len(pages))
    pages_later = int(dels.loc[later, "page_key"].nunique())
    out.update(
        {
            "delete_events": int(len(dels)),
            "delete_events_parsed_time": int(dels["t"].notna().sum()),
            "delete_events_on_held_pages": int(held.sum()),
            "delete_events_page_held_flag_true": int((dels.get("page_held") == True).sum())  # noqa: E712
            if "page_held" in dels
            else None,
            "held_pages": n_pages,
            "held_pages_with_any_delete_event": int(dels.loc[held, "page_key"].nunique()),
            "held_pages_deleted_after_first_write": pages_later,
            "share_held_pages_deleted_after_first_write": pages_later / n_pages if n_pages else None,
            "pages_n_deletions_gt_0": int((pages["n_deletions"] > 0).sum()) if "n_deletions" in pages else None,
            "pages_deleted_live_true": int((pages["deleted_live"] == True).sum())  # noqa: E712
            if "deleted_live" in pages
            else None,
        }
    )
    return out


def plot_daily(rev: pd.DataFrame) -> str:
    """Write the daily revision histogram.

    Args:
        rev: Revisions frame with parsed 't'.

    Returns:
        Repo-relative path of the figure.
    """
    t = rev["t"].dropna()
    counts = t.dt.floor("D").value_counts().sort_index()
    idx = pd.date_range(counts.index.min(), counts.index.max(), freq="D")
    counts = counts.reindex(idx, fill_value=0)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 3.6), facecolor=COLOR_SURFACE)
    ax.set_facecolor(COLOR_SURFACE)
    ax.bar(counts.index, counts.values, width=0.8, color=COLOR_BAR, linewidth=0)
    ax.set_title(f"Revisions per day (UTC), n = {len(t):,}", color=COLOR_TEXT, loc="left", fontsize=11)
    ax.set_ylabel("revisions", color=COLOR_TEXT_2)
    ax.tick_params(colors=COLOR_TEXT_2, labelsize=8)
    ax.grid(axis="y", color=COLOR_GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(COLOR_GRID)
    fig.autofmt_xdate()
    fig.tight_layout()
    out = FIGURES_DIR / "E20_daily_revisions.png"
    fig.savefig(out, dpi=150, facecolor=COLOR_SURFACE)
    plt.close(fig)
    return "figures/E20_daily_revisions.png"


def write_parquet(rev: pd.DataFrame) -> dict[str, Any]:
    """Write the slim revision table.

    Args:
        rev: Revisions frame with parsed 't'.

    Returns:
        Dict with path, columns, rows and size.
    """
    cols = [c for c in ("rev_id", "page_id", "page_key", "wiki", "name", "seq", "label", "time",
                        "time_grade", "write_date", "diff_base", "diff_base_reason", "body",
                        "body_len", "body_sha256", "lines") if c in rev]
    slim = rev[cols].copy()
    slim["t_utc"] = rev["t"]
    slim["text_len"] = rev["body"].fillna("").str.len()
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    out = INTERIM_DIR / "collusion_slim.parquet"
    slim.to_parquet(out, index=False, compression="zstd")
    return {"path": "data/interim/collusion_slim.parquet", "columns": list(slim.columns),
            "rows": int(len(slim)), "size_bytes": out.stat().st_size}


def main() -> None:
    """Run E20 and write results/E20_profile.json."""
    manifest_path = sorted(CORPUS_DIR.rglob("manifest.json"))[0]
    res: dict[str, Any] = {"manifest": manifest_summary(manifest_path)}

    frames: dict[str, list[dict[str, Any]]] = {}
    files: dict[str, Any] = {}
    examples: dict[str, Any] = {}
    for stem in DATA_FILES:
        p = find_file(stem)
        frames[stem] = read_jsonl(p)
        prof, ex = profile_fields(frames[stem])
        files[stem] = {"path": str(p.relative_to(REPO_ROOT)).replace("\\", "/"),
                       "size_bytes": p.stat().st_size, **prof}
        examples[stem] = ex
    res["files"] = files

    rev = pd.DataFrame(frames["revisions"])
    pages = pd.DataFrame(frames["pages"])
    events = pd.DataFrame(frames["events"])
    rev["t"] = pd.to_datetime(rev["time"], utc=True, errors="coerce", format="ISO8601")

    res["revisions"] = revision_stats(rev, pages)
    res["deletions"] = deletion_stats(events, pages)
    res["figure"] = plot_daily(rev)
    res["parquet"] = write_parquet(rev)

    timed = res["revisions"]["timestamp"]["parsed"]
    p5 = res["revisions"]["revisions_per_page"]["pages_ge_5"]
    res["go_no_go"] = {
        "timed_revisions": timed,
        "timed_revisions_ge_5000": timed >= GO_MIN_TIMED_REVISIONS,
        "pages_with_ge_5_revisions": p5,
        "pages_ge_5_ge_200": p5 >= GO_MIN_PAGES_5PLUS,
        "go": timed >= GO_MIN_TIMED_REVISIONS and p5 >= GO_MIN_PAGES_5PLUS,
    }

    (INTERIM_DIR / "E20_examples.json").write_text(
        json.dumps(examples, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    params = {"example_trunc": EXAMPLE_TRUNC, "n_examples": N_EXAMPLES, "low_card_max": LOW_CARD_MAX,
              "go_min_timed_revisions": GO_MIN_TIMED_REVISIONS, "go_min_pages_5plus": GO_MIN_PAGES_5PLUS,
              "sampling": "none"}
    save_result("E20_profile", res, params)
    append_summary("E20", {
        "revisions": len(rev),
        "pages": len(pages),
        "timed_revisions": timed,
        "pages_ge_5_revisions": p5,
        "manifest_checks_ok": f"{res['manifest']['n_checks_ok']}/{res['manifest']['n_checks']}",
        "go": res["go_no_go"]["go"],
    })
    print(json.dumps(res["go_no_go"]))


if __name__ == "__main__":
    main()
