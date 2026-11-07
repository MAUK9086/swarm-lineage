"""E33 - Profile the Moltbook agents subset; owner linkage as counts only.

Privacy rule: example values only for an allow-list of non-personal fields. All other
fields (owner handle, claim flag, name, description, avatar URL, unknown fields) get
counts only. Raw handles are never written or printed; a salted keyed hash per agent is
kept in an untracked file for later experiments.

File structure:
    Constants        allow-list, thresholds, paths
    normalise_handle strip, lower-case, drop leading '@'
    load_agents      read every agents file; per-file schema and null counts
    field_stats      per-field stats over deduplicated agents (examples only if allowed)
    owner_stats      agents with an owner, distinct owners, agents-per-owner distribution
    write_owner_keys HMAC owner keys to data/interim (untracked)
    leak_check       ensure no example / value-count string equals a raw handle or name
    main
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.hf_download import download, list_files  # noqa: E402
from src.io_utils import INTERIM_DIR, append_summary, save_result  # noqa: E402

EXAMPLE_FIELDS = {"id", "karma", "follower_count", "following_count", "first_seen_at",
                  "last_seen_at", "created_at", "dump_date"}
OWNER_FIELD = "owner_x_handle"
CLAIM_FIELD = "is_claimed"
EXAMPLE_TRUNC = 80
N_EXAMPLES = 3
PCTS = (1, 5, 25, 50, 75, 95, 99)
GO_MIN_OWNER_SHARE = 0.10
GO_MIN_MULTI_OWNERS = 100


def normalise_handle(h: Any) -> str | None:
    """Normalise an owner handle for counting.

    Args:
        h: Raw value.

    Returns:
        Normalised handle, or None when missing / empty / the string 'None'.
    """
    if h is None or (isinstance(h, float) and np.isnan(h)):
        return None
    s = str(h).strip().lower().lstrip("@")
    return s if s and s != "none" else None


def load_agents(paths: list[Path]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Read every agents file.

    Args:
        paths: Local agents files.

    Returns:
        (all rows with a file index column, per-field schema / null info over rows)
    """
    parts = []
    types: dict[str, Counter[str]] = defaultdict(Counter)
    files_with: Counter[str] = Counter()
    nulls: Counter[str] = Counter()
    for k, p in enumerate(tqdm(paths, desc="read agents", unit="file")):
        tbl = pq.read_table(p)
        for f in tbl.schema:
            types[f.name][str(f.type)] += 1
            files_with[f.name] += 1
            nulls[f.name] += tbl.column(f.name).null_count
        df = tbl.to_pandas()
        df["_file"] = k
        parts.append(df)
    rows = pd.concat(parts, ignore_index=True)
    info = {"files": len(paths), "rows": int(len(rows)),
            "fields": {c: {"files_with_field": files_with[c], "arrow_types": dict(types[c]),
                           "null_rows": int(nulls[c]),
                           "present_rate_rows": float(rows[c].notna().mean())} for c in types}}
    return rows, info


def _example(v: Any) -> str:
    """Render one example value, truncated.

    Args:
        v: Value.

    Returns:
        String of at most EXAMPLE_TRUNC characters (+ '...').
    """
    s = v.isoformat() if hasattr(v, "isoformat") else str(v)
    return s if len(s) <= EXAMPLE_TRUNC else s[:EXAMPLE_TRUNC] + "..."


def field_stats(d: pd.DataFrame, fields: list[str]) -> dict[str, Any]:
    """Per-field stats over deduplicated agents.

    Args:
        d: Deduplicated agents.
        fields: Field names in order.

    Returns:
        Dict keyed by field.
    """
    out: dict[str, Any] = {}
    n = len(d)
    for c in fields:
        col = d[c]
        nn = col.notna()
        s: dict[str, Any] = {"non_null": int(nn.sum()), "present_rate": float(nn.mean()),
                             "python_types": dict(Counter(type(v).__name__ for v in col[nn]))}
        is_str = col.dtype == object or str(col.dtype).startswith("string")
        if is_str:
            vals = col[nn].astype(str)
            nonempty = vals[(vals.str.strip() != "") & (vals.str.lower() != "none")]
            s["non_empty"] = int(len(nonempty))
            s["non_empty_rate"] = float(len(nonempty) / n) if n else None
            s["distinct_non_empty"] = int(nonempty.nunique())
            if c not in EXAMPLE_FIELDS and len(nonempty):
                lens = nonempty.str.len().to_numpy()
                s["length_chars"] = {f"p{p}": float(np.percentile(lens, p)) for p in (5, 50, 95)}
        elif pd.api.types.is_numeric_dtype(col) and nn.any():
            a = col[nn].to_numpy(dtype=float)
            s["distinct"] = int(col[nn].nunique())
            if c in EXAMPLE_FIELDS:
                s["percentiles"] = {f"p{p}": float(np.percentile(a, p)) for p in PCTS}
                s["min"], s["max"] = float(a.min()), float(a.max())
            elif s["distinct"] <= 10:
                s["value_counts"] = {str(k): int(v) for k, v in col[nn].value_counts().items()}
        elif pd.api.types.is_datetime64_any_dtype(col) and nn.any():
            s["distinct"] = int(col[nn].nunique())
            if c in EXAMPLE_FIELDS:
                s["min"], s["max"] = col[nn].min().isoformat(), col[nn].max().isoformat()
        if c in EXAMPLE_FIELDS:
            ex = []
            for v in col[nn]:
                e = _example(v)
                if e not in ex:
                    ex.append(e)
                if len(ex) == N_EXAMPLES:
                    break
            s["examples"] = ex
        else:
            s["examples"] = "withheld (counts only)"
        out[c] = s
    return out


def owner_stats(d: pd.DataFrame) -> tuple[dict[str, Any], pd.Series]:
    """Owner linkage statistics, counts only.

    Args:
        d: Deduplicated agents.

    Returns:
        (stats dict, normalised handle per agent; kept in memory only)
    """
    norm = d[OWNER_FIELD].map(normalise_handle) if OWNER_FIELD in d else pd.Series(None, index=d.index)
    has = norm.notna()
    per_owner = norm[has].value_counts()
    out: dict[str, Any] = {
        "agents": int(len(d)),
        "agents_with_owner": int(has.sum()),
        "share_with_owner": float(has.mean()),
        "distinct_owners": int(per_owner.size),
        "normalisation": "strip, lower-case, leading @ removed; empty and 'none' treated as missing",
    }
    if per_owner.size:
        a = per_owner.to_numpy()
        out["agents_per_owner"] = {**{f"p{p}": float(np.percentile(a, p)) for p in PCTS},
                                   "mean": float(a.mean()), "max": int(a.max()),
                                   **{f"owners_ge_{k}": int((a >= k).sum()) for k in (2, 5, 10, 100)},
                                   "agents_under_owners_ge_2": int(a[a >= 2].sum())}
        hist = Counter(np.minimum(a, 11).tolist())
        out["owners_by_agent_count"] = {("11+" if k == 11 else str(k)): int(v) for k, v in sorted(hist.items())}
    if CLAIM_FIELD in d:
        claimed = d[CLAIM_FIELD].fillna(-1).astype(int).astype(str)
        out["claim_crosstab"] = {f"is_claimed={k}": {"with_owner": int((has & (claimed == k)).sum()),
                                                     "without_owner": int((~has & (claimed == k)).sum())}
                                 for k in sorted(claimed.unique())}
    return out, norm


def write_owner_keys(d: pd.DataFrame, norm: pd.Series) -> dict[str, Any]:
    """Write agent_id -> salted HMAC owner key to an untracked file.

    Args:
        d: Deduplicated agents.
        norm: Normalised handle per agent.

    Returns:
        Dict with path and row count (no keys).
    """
    salt_path = INTERIM_DIR / "owner_salt.bin"
    if not salt_path.exists():
        salt_path.write_bytes(os.urandom(32))
    salt = salt_path.read_bytes()
    keys = [hmac.new(salt, h.encode("utf-8"), hashlib.sha256).hexdigest()[:16] if isinstance(h, str) else None for h in norm]
    out = pd.DataFrame({"agent_id": d["id"].astype(str).to_numpy(), "owner_key": keys})
    path = INTERIM_DIR / "moltbook_agent_owner.parquet"
    out.to_parquet(path, index=False)
    return {"path": "data/interim/moltbook_agent_owner.parquet", "rows": int(len(out)),
            "rows_with_key": int(out["owner_key"].notna().sum()), "key": "HMAC-SHA256(salt, handle)[:16]"}


def leak_check(fields: dict[str, Any], d: pd.DataFrame, norm: pd.Series) -> int:
    """Count example / value-count strings that equal a raw handle or agent name.

    Args:
        fields: field_stats output.
        d: Deduplicated agents.
        norm: Normalised handles.

    Returns:
        Number of hits (0 required before saving).
    """
    sensitive = set(norm.dropna()) | set(d[OWNER_FIELD].dropna().astype(str)) if OWNER_FIELD in d else set(norm.dropna())
    if "name" in d:
        sensitive |= set(d["name"].dropna().astype(str))
    sensitive = {s for s in sensitive if s.strip()}
    emitted = []
    for s in fields.values():
        if isinstance(s.get("examples"), list):
            emitted += s["examples"]
        emitted += list(s.get("value_counts", {}).keys())
    return sum(1 for e in emitted if e in sensitive or e.lower() in sensitive)


def main() -> None:
    """Run E33 and write results/E33_agents_fields.json."""
    paths = download(list_files(), "agents")
    rows, row_info = load_agents(paths)
    fields_order = [c for c in rows.columns if c != "_file"]
    d = rows.sort_values(["dump_date", "_file"]).drop_duplicates("id", keep="last").reset_index(drop=True)
    fields = field_stats(d, fields_order)
    owners, norm = owner_stats(d)
    hits = leak_check(fields, d, norm)
    if hits:
        raise RuntimeError(f"leak check failed: {hits} emitted strings match a handle or name")
    res: dict[str, Any] = {
        "rows": row_info,
        "dedup": {"rows": int(len(rows)), "unique_agents": int(len(d)), "rows_dropped": int(len(rows) - len(d))},
        "fields_deduplicated": fields,
        "owner_linkage": owners,
        "owner_keys_file": write_owner_keys(d, norm),
        "leak_check_hits": hits,
        "fields_not_in_inspected_schema": [c for c in fields_order if c not in {
            "id", "name", "description", "karma", "follower_count", "following_count", "is_claimed",
            "owner_x_handle", "first_seen_at", "last_seen_at", "created_at", "avatar_url", "dump_date"}],
    }
    multi = owners.get("agents_per_owner", {}).get("owners_ge_2", 0)
    res["go_no_go"] = {"share_with_owner": owners["share_with_owner"],
                       "share_ge_10pct": owners["share_with_owner"] >= GO_MIN_OWNER_SHARE,
                       "owners_with_ge_2_agents": multi, "multi_owners_ge_100": multi >= GO_MIN_MULTI_OWNERS}
    res["go_no_go"]["go"] = res["go_no_go"]["share_ge_10pct"] and res["go_no_go"]["multi_owners_ge_100"]
    params = {"example_allow_list": sorted(EXAMPLE_FIELDS), "example_trunc": EXAMPLE_TRUNC,
              "go_min_owner_share": GO_MIN_OWNER_SHARE, "go_min_multi_owners": GO_MIN_MULTI_OWNERS,
              "dedup": "latest dump_date per id", "salt": "32 random bytes, untracked, not seeded"}
    save_result("E33_agents_fields", res, params)
    append_summary("E33", {"unique_agents": len(d), "agents_with_owner": owners["agents_with_owner"],
                           "distinct_owners": owners["distinct_owners"], "owners_ge_2": multi,
                           "go": res["go_no_go"]["go"]})
    print(res["dedup"], res["go_no_go"], "leak_check_hits", hits)


if __name__ == "__main__":
    main()
