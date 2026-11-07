"""E30 - Profile the Moltbook observatory archive and write a 300k-post sample.

Steps: list the dataset files; download posts and comments; pass 1 over the posts
files keeps ids, metadata and a hash of the normalised text (no full text held in
memory); deduplicate by id (latest dump wins); compute statistics; pass 2 fetches the
text of 300,000 sampled posts and writes them through the adapter.

Usage:
    python -I experiments/E30_profile.py            # download (if needed) and profile
    python -I experiments/E30_profile.py --list     # only list files

File structure:
    Constants           dataset id, paths, thresholds
    list_files          file listing from the Hugging Face API
    download            fetch a subset's files (skips files already complete)
    norm_hash           64-bit hash of whitespace-collapsed, lower-cased text
    posts_pass1         per-file metadata, null counts, schema
    dedupe              keep the latest dump of each post id
    posts_stats         time, agents, submolts, duplicates, lengths, id formats
    comments_stats      comments row count, dedup and time span
    write_sample        pass 2: sampled posts through the adapter to Parquet
    main
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.adapters.moltbook import POSTS_COLUMNS, author_ids, post_text, to_standard  # noqa: E402
from src.evaluate import time_summary  # noqa: E402
from src.io_utils import INTERIM_DIR, REPO_ROOT, SEED, append_summary, save_result  # noqa: E402

DATASET = "SimulaMet/moltbook-observatory-archive"
API_TREE = f"https://huggingface.co/api/datasets/{DATASET}/tree/main?recursive=true"
RESOLVE = f"https://huggingface.co/datasets/{DATASET}/resolve/main/"
UA = {"User-Agent": "swarm-lineage-research"}
RAW_DIR = REPO_ROOT / "data" / "raw" / "moltbook"
COMMENTS_MAX_BYTES = 2 * 1024**3
SAMPLE_N = 300_000
GO_MIN_TIMED = 100_000
GO_MIN_AGENTS_20 = 1_000
GO_MIN_DUP_RATE = 0.01
PCTS = (1, 5, 25, 50, 75, 95, 99)
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
WS_RE = re.compile(r"\s+")


def list_files() -> list[dict[str, Any]]:
    """Return the dataset's file list with sizes.

    Returns:
        List of {'path', 'size'} dicts.
    """
    req = urllib.request.Request(API_TREE, headers=UA)
    items = json.load(urllib.request.urlopen(req, timeout=120))
    return [{"path": i["path"], "size": int(i.get("lfs", {}).get("size", i.get("size", 0)))}
            for i in items if i.get("type") == "file"]


def download(files: list[dict[str, Any]], subset: str) -> list[Path]:
    """Download every file of one subset into RAW_DIR, skipping complete files.

    Args:
        files: Output of list_files().
        subset: Subset directory name, e.g. 'posts'.

    Returns:
        Local paths of the subset's files, sorted.
    """
    todo = [f for f in files if f["path"].startswith(f"data/{subset}/")]
    paths = []
    for f in tqdm(todo, desc=f"download {subset}", unit="file"):
        dst = RAW_DIR / f["path"]
        paths.append(dst)
        if dst.exists() and dst.stat().st_size == f["size"]:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(5):
            try:
                req = urllib.request.Request(RESOLVE + f["path"], headers=UA)
                tmp = dst.with_suffix(".part")
                with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as out:
                    while chunk := r.read(1 << 20):
                        out.write(chunk)
                tmp.replace(dst)
                break
            except OSError:
                time.sleep(5 * (attempt + 1))
        else:
            raise RuntimeError(f"download failed: {f['path']}")
    return sorted(paths)


def norm_hash(s: str) -> int:
    """Hash of the normalised text (whitespace collapsed, lower-cased), or 0 if empty.

    Args:
        s: Text.

    Returns:
        Signed 64-bit integer hash; 0 marks an empty normalised text.
    """
    n = WS_RE.sub(" ", s).strip().lower()
    if not n:
        return 0
    return int.from_bytes(hashlib.blake2b(n.encode("utf-8"), digest_size=8).digest(), "little", signed=True) or 1


def posts_pass1(paths: list[Path]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Read every posts file and keep per-row metadata only.

    Args:
        paths: Local posts files.

    Returns:
        (metadata frame, schema / null-count info)
    """
    parts = []
    schema_types: dict[str, Counter[str]] = defaultdict(Counter)
    nulls: Counter[str] = Counter()
    rows_total = 0
    for i, p in enumerate(tqdm(paths, desc="posts pass 1", unit="file")):
        pf = pq.ParquetFile(p)
        for field in pf.schema_arrow:
            schema_types[field.name][str(field.type)] += 1
        cols = [c for c in POSTS_COLUMNS + ["dump_date"] if c in pf.schema_arrow.names]
        tbl = pf.read(columns=cols)
        for c in tbl.column_names:
            nulls[c] += tbl.column(c).null_count
        raw = tbl.to_pandas()
        rows_total += len(raw)
        text = post_text(raw)
        parts.append(pd.DataFrame({
            "id": raw["id"].astype(str).to_numpy(),
            "dump_date": raw["dump_date"].astype(str).to_numpy(),
            "created_at": pd.to_datetime(raw["created_at"], utc=True, errors="coerce").to_numpy(),
            "author_id": author_ids(raw).to_numpy(),
            "submolt": raw["submolt"].astype("string").to_numpy(),
            "text_len": text.str.len().to_numpy(),
            "h": np.fromiter((norm_hash(s) for s in text), dtype=np.int64, count=len(text)),
            "file_idx": i,
        }))
    meta = pd.concat(parts, ignore_index=True)
    meta["created_at"] = pd.to_datetime(meta["created_at"], utc=True)
    info = {"rows_across_files": rows_total,
            "schema": {k: dict(v) for k, v in schema_types.items()},
            "null_counts_across_files": dict(nulls)}
    return meta, info


def dedupe(meta: pd.DataFrame) -> pd.DataFrame:
    """Keep the latest dump of each post id.

    Args:
        meta: Pass-1 metadata.

    Returns:
        Deduplicated metadata.
    """
    return meta.sort_values(["dump_date", "file_idx"]).drop_duplicates("id", keep="last").reset_index(drop=True)


def _dist(counts: pd.Series) -> dict[str, float]:
    """Percentiles, mean and max of a count series.

    Args:
        counts: Integer counts.

    Returns:
        Summary dict.
    """
    a = counts.to_numpy()
    d = {f"p{p}": float(np.percentile(a, p)) for p in PCTS}
    d.update({"mean": float(a.mean()), "max": int(a.max())})
    return d


def posts_stats(d: pd.DataFrame) -> dict[str, Any]:
    """Statistics over deduplicated posts.

    Args:
        d: Deduplicated metadata.

    Returns:
        Dict of aggregates.
    """
    out: dict[str, Any] = {"posts": int(len(d))}
    out["created_at"] = time_summary(d["created_at"])
    out["posts_per_month"] = {str(k): int(v) for k, v in
                              d["created_at"].dt.strftime("%Y-%m").value_counts().sort_index().items()}

    per_agent = d["author_id"].dropna().value_counts()
    out["posts_per_agent"] = {"agents": int(per_agent.size), "posts_without_author": int(d["author_id"].isna().sum()),
                              **_dist(per_agent),
                              **{f"agents_ge_{k}": int((per_agent >= k).sum()) for k in (2, 5, 20, 100, 1000)},
                              "share_of_posts_by_top_10_agents": float(per_agent.head(10).sum() / per_agent.sum())}
    per_sub = d["submolt"].dropna().value_counts()
    out["posts_per_submolt"] = {"submolts": int(per_sub.size), "posts_without_submolt": int(d["submolt"].isna().sum()),
                                **_dist(per_sub),
                                **{f"submolts_ge_{k}": int((per_sub >= k).sum()) for k in (20, 100, 1000)},
                                "share_of_posts_in_top_10_submolts": float(per_sub.head(10).sum() / per_sub.sum())}

    nonempty = d[d["h"] != 0]
    hc = nonempty["h"].value_counts()
    in_dup = nonempty["h"].map(hc) > 1
    authors_per_hash = nonempty.groupby("h")["author_id"].nunique()
    out["exact_duplicates"] = {
        "normalisation": "whitespace collapsed, lower-cased, blake2b-64",
        "posts_with_empty_normalised_text": int((d["h"] == 0).sum()),
        "posts_non_empty": int(len(nonempty)),
        "distinct_texts": int(hc.size),
        "posts_in_duplicate_groups": int(in_dup.sum()),
        "exact_duplicate_rate": float(in_dup.mean()) if len(nonempty) else None,
        "duplicate_groups": int((hc > 1).sum()),
        "largest_group": int(hc.max()) if hc.size else 0,
        "groups_with_ge_2_authors": int((authors_per_hash > 1).sum()),
        "posts_in_multi_author_groups": int(nonempty["h"].map(authors_per_hash).gt(1).sum()),
    }
    out["text_length_chars"] = _dist(d["text_len"]) | {"empty": int((d["text_len"] == 0).sum())}
    ids = d["id"]
    out["id_format"] = {"uuid": int(ids.str.match(UUID_RE).sum()),
                        "numeric": int(ids.str.fullmatch(r"\d+").sum())}
    out["id_format"]["other"] = int(len(ids) - out["id_format"]["uuid"] - out["id_format"]["numeric"])
    return out


def comments_stats(paths: list[Path]) -> dict[str, Any]:
    """Row count, id dedup and created_at span for comments.

    Args:
        paths: Local comments files.

    Returns:
        Dict of aggregates.
    """
    parts = []
    for p in tqdm(paths, desc="comments", unit="file"):
        t = pq.read_table(p, columns=["id", "created_at", "dump_date"]).to_pandas()
        t["created_at"] = pd.to_datetime(t["created_at"], utc=True, errors="coerce")
        parts.append(t)
    c = pd.concat(parts, ignore_index=True)
    rows = len(c)
    c = c.sort_values("dump_date").drop_duplicates("id", keep="last")
    return {"rows_across_files": int(rows), "unique_ids": int(len(c)), "created_at": time_summary(c["created_at"])}


def write_sample(paths: list[Path], d: pd.DataFrame) -> dict[str, Any]:
    """Pass 2: fetch the text of SAMPLE_N sampled posts and write them via the adapter.

    Args:
        paths: Local posts files (same order as in pass 1).
        d: Deduplicated metadata.

    Returns:
        Dict with path, rows, eligible pool size and file size.
    """
    pool = d[d["created_at"].notna()]
    rng = np.random.default_rng(SEED)
    pick = pool.iloc[np.sort(rng.choice(len(pool), size=min(SAMPLE_N, len(pool)), replace=False))]
    want = defaultdict(set)
    for fi, pid in zip(pick["file_idx"], pick["id"]):
        want[fi].add(pid)
    raws = []
    for fi in tqdm(sorted(want), desc="posts pass 2", unit="file"):
        raw = pq.read_table(paths[fi], columns=POSTS_COLUMNS).to_pandas()
        raw = raw[raw["id"].astype(str).isin(want[fi])].drop_duplicates("id", keep="last")
        raws.append(raw)
    std = to_standard(pd.concat(raws, ignore_index=True))
    out = INTERIM_DIR / "moltbook_slim.parquet"
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    std.to_parquet(out, index=False, compression="zstd")
    return {"path": "data/interim/moltbook_slim.parquet", "rows": int(len(std)), "pool": int(len(pool)),
            "columns": list(std.columns), "size_bytes": out.stat().st_size}


def main() -> None:
    """Run E30."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    files = list_files()
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(files).to_csv(INTERIM_DIR / "E30_file_listing.csv", index=False)
    by_subset: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "bytes": 0})
    for f in files:
        sub = f["path"].split("/")[1] if f["path"].startswith("data/") else f["path"]
        by_subset[sub]["files"] += 1
        by_subset[sub]["bytes"] += f["size"]
    listing = {"total_files": len(files), "total_bytes": sum(f["size"] for f in files),
               "by_subset": dict(by_subset)}
    print(json.dumps(listing, indent=1))
    if args.list:
        return

    post_paths = download(files, "posts")
    comments_bytes = by_subset.get("comments", {}).get("bytes", 0)
    comment_paths = download(files, "comments") if comments_bytes < COMMENTS_MAX_BYTES else []

    meta, schema_info = posts_pass1(post_paths)
    d = dedupe(meta)
    res: dict[str, Any] = {"listing": listing, "posts_schema": schema_info,
                           "posts_dedup": {"rows_across_files": schema_info["rows_across_files"],
                                           "unique_ids": int(len(d)),
                                           "duplicate_rows_dropped": int(len(meta) - len(d))}}
    res["posts"] = posts_stats(d)
    res["comments"] = comments_stats(comment_paths) if comment_paths else {"downloaded": False}
    res["sample"] = write_sample(post_paths, d)

    timed = res["posts"]["created_at"]["parsed"]
    a20 = res["posts"]["posts_per_agent"]["agents_ge_20"]
    dup = res["posts"]["exact_duplicates"]["exact_duplicate_rate"] or 0.0
    res["go_no_go"] = {
        "timed_posts": timed, "timed_ge_100k": timed >= GO_MIN_TIMED,
        "agents_ge_20_posts": a20, "agents_ge_1000": a20 >= GO_MIN_AGENTS_20,
        "exact_duplicate_rate": dup,
        "dup_rate_ge_1pct": True if dup >= GO_MIN_DUP_RATE else "undecided_until_E31",
    }
    res["go_no_go"]["go"] = (res["go_no_go"]["timed_ge_100k"] and res["go_no_go"]["agents_ge_1000"]
                             and res["go_no_go"]["dup_rate_ge_1pct"] is True)
    params = {"sample_n": SAMPLE_N, "sample_pool": "deduplicated posts with parseable created_at",
              "text": "title + blank line + content", "dup_normalisation": "collapse whitespace, lower-case",
              "go_min_timed": GO_MIN_TIMED, "go_min_agents_20": GO_MIN_AGENTS_20,
              "go_min_dup_rate": GO_MIN_DUP_RATE, "comments_max_bytes": COMMENTS_MAX_BYTES}
    save_result("E30_profile", res, params)
    append_summary("E30", {"posts_unique": len(d), "timed_posts": timed, "agents_ge_20": a20,
                           "exact_dup_rate": dup, "sample_rows": res["sample"]["rows"],
                           "go": res["go_no_go"]["go"]})
    print(json.dumps(res["go_no_go"]))


if __name__ == "__main__":
    main()
