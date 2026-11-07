"""E00 - Profile the corpus fields and write a slim Parquet copy.

Pass 1 collects per-field statistics and a few structural checks. Pass 2 writes
data/interim/corpus_slim.parquet. Examples of the text field go only to
data/interim/E00_text_examples.json (not tracked); the results file keeps their
row ids and lengths.

File structure:
    Constants       parameters
    FieldStats      per-field accumulator
    profile_pass    pass 1: field stats, id / parent / cite checks, text storage
    write_parquet   pass 2: slim Parquet
    main            run both passes, save results and summary rows
"""

from __future__ import annotations

import gzip
import hashlib
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import orjson
import pyarrow as pa
import pyarrow.parquet as pq
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.io_utils import INTERIM_DIR, RAW_PATH, append_summary, iter_rows, save_result  # noqa: E402

EXAMPLE_TRUNC = 150
N_EXAMPLES = 3
LOW_CARD_MAX = 200
DISTINCT_CAP = 5000
BATCH = 5000
TEXT_FIELD = "text"

ID_RE = re.compile(r"^R(\d+)$")
B64_CHARSET_RE = re.compile(r"^[A-Za-z0-9+/=_\-\s]+$")


def type_name(v: Any) -> str:
    """Return a JSON-style type name.

    Args:
        v: A parsed JSON value.

    Returns:
        One of null, bool, int, float, str, list, dict.
    """
    if v is None:
        return "null"
    return {bool: "bool", int: "int", float: "float", str: "str", list: "list", dict: "dict"}[type(v)]


def trunc(v: Any) -> str:
    """Render a value as a string of at most EXAMPLE_TRUNC characters.

    Args:
        v: A parsed JSON value.

    Returns:
        The (possibly truncated) string.
    """
    s = v if isinstance(v, str) else orjson.dumps(v).decode()
    return s if len(s) <= EXAMPLE_TRUNC else s[:EXAMPLE_TRUNC] + "..."


class FieldStats:
    """Presence, type, length and value statistics for one field."""

    def __init__(self) -> None:
        """Initialise empty counters."""
        self.present = 0
        self.non_null = 0
        self.non_empty = 0
        self.types: Counter[str] = Counter()
        self.lengths: list[int] = []
        self.examples: list[tuple[str, Any]] = []
        self.values: Counter[str] | None = Counter()

    def add(self, row_id: str, v: Any) -> None:
        """Update the counters with one value.

        Args:
            row_id: Id of the row the value came from.
            v: The value.
        """
        self.present += 1
        self.types[type_name(v)] += 1
        if v is None:
            return
        self.non_null += 1
        if v not in ("", [], {}):
            self.non_empty += 1
        if isinstance(v, (str, list, dict)):
            self.lengths.append(len(v))
        if v not in ("", [], {}) and len(self.examples) < N_EXAMPLES:
            if all(e[1] != v for e in self.examples):
                self.examples.append((row_id, v))
        if self.values is not None:
            key = v if isinstance(v, str) else orjson.dumps(v).decode()
            self.values[key] += 1
            if len(self.values) > DISTINCT_CAP:
                self.values = None

    def summary(self, n_rows: int, hide_values: bool) -> dict[str, Any]:
        """Return the field summary as a dict.

        Args:
            n_rows: Total row count, for presence rates.
            hide_values: If True, report example row ids and lengths only.

        Returns:
            Summary dict.
        """
        out: dict[str, Any] = {
            "present": self.present,
            "present_rate": self.present / n_rows,
            "non_null": self.non_null,
            "non_null_rate": self.non_null / n_rows,
            "non_empty": self.non_empty,
            "non_empty_rate": self.non_empty / n_rows,
            "types": dict(self.types),
        }
        if self.lengths:
            a = np.asarray(self.lengths)
            out["length"] = {
                "min": int(a.min()),
                "p50": float(np.percentile(a, 50)),
                "mean": float(a.mean()),
                "p99": float(np.percentile(a, 99)),
                "max": int(a.max()),
            }
        if hide_values:
            out["examples"] = [{"id": i, "length": len(v)} for i, v in self.examples]
        else:
            out["examples"] = [{"id": i, "value": trunc(v)} for i, v in self.examples]
        if self.values is None:
            out["distinct_values"] = f">{DISTINCT_CAP}"
        else:
            out["distinct_values"] = len(self.values)
            if not hide_values and len(self.values) <= LOW_CARD_MAX:
                out["value_counts"] = {trunc(k): c for k, c in self.values.most_common()}
        return out


def profile_pass() -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Pass 1 over the corpus.

    Returns:
        (results dict, text examples for the untracked file, ordered field list)
    """
    fields: dict[str, FieldStats] = {}
    key_sets: Counter[tuple[str, ...]] = Counter()
    n_rows = 0
    parse_errors = 0
    ids: list[str] = []
    bad_id_format = 0
    parents: list[str] = []
    cite_checks = Counter()
    text = Counter()
    text_lens: list[int] = []
    kind_by_field: dict[str, Counter[str]] = {}

    def tolerant_rows():
        """Yield parsed rows, counting (not raising on) unparseable lines."""
        nonlocal parse_errors
        with gzip.open(RAW_PATH, "rb") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    yield orjson.loads(line)
                except orjson.JSONDecodeError:
                    parse_errors += 1

    if True:
        for row in tqdm(tolerant_rows(), desc="E00 pass 1", unit="rows"):
            n_rows += 1
            key_sets[tuple(sorted(row.keys()))] += 1
            rid = row.get("id")
            rid_s = rid if isinstance(rid, str) else str(rid)
            for k, v in row.items():
                fields.setdefault(k, FieldStats()).add(rid_s, v)
                if v not in (None, "", [], {}):
                    kind_by_field.setdefault(k, Counter())[str(row.get("kind"))] += 1
            ids.append(rid_s)
            if not (isinstance(rid, str) and ID_RE.match(rid)):
                bad_id_format += 1
            if row.get("parent_id") is not None:
                parents.append(str(row["parent_id"]))

            t = row.get(TEXT_FIELD)
            if isinstance(t, str):
                b = t.encode("utf-8")
                text_lens.append(len(t))
                text["str"] += 1
                text["empty"] += t == ""
                text["has_newline"] += "\n" in t
                text["has_crlf"] += "\r\n" in t
                text["non_ascii"] += len(b) != len(t)
                text["base64_charset_only_len_ge_40"] += len(t) >= 40 and bool(B64_CHARSET_RE.match(t))
                text["leading_or_trailing_ws"] += t != t.strip()
                cite = row.get("cite")
                if isinstance(cite, str) and ":" in cite:
                    suf = cite.split(":", 1)[1]
                    cite_checks["with_suffix"] += 1
                    cite_checks["suffix_len_" + str(len(suf))] += 1
                    cite_checks["cite_prefix_equals_id"] += cite.split(":", 1)[0] == rid_s
                    for algo in ("md5", "sha1", "sha256"):
                        cite_checks[algo + "_prefix_match"] += hashlib.new(algo, b).hexdigest().startswith(suf)
            else:
                text["missing_or_not_str"] += 1

    id_set = set(ids)
    nums = [int(m.group(1)) for m in (ID_RE.match(i) for i in ids) if m]
    nums_arr = np.asarray(nums)
    diffs = np.diff(nums_arr) if len(nums_arr) > 1 else np.asarray([])
    parent_set = Counter(parents)
    tl = np.asarray(text_lens)

    ordered = list(fields.keys())
    examples_private = {
        "text_examples": [{"id": i, "value": trunc(v)} for i, v in fields[TEXT_FIELD].examples]
        if TEXT_FIELD in fields
        else []
    }
    res = {
        "file": {"path": "data/raw/redacted.jsonl.gz", "size_bytes": os.path.getsize(RAW_PATH)},
        "n_rows": n_rows,
        "parse_errors": parse_errors,
        "key_sets": {"|".join(k): c for k, c in key_sets.most_common()},
        "fields": {k: fields[k].summary(n_rows, hide_values=(k == TEXT_FIELD)) for k in ordered},
        "non_empty_by_kind": {k: dict(c) for k, c in kind_by_field.items()},
        "ids": {
            "n": len(ids),
            "unique": len(id_set),
            "bad_format": bad_id_format,
            "numeric_min": int(nums_arr.min()) if len(nums_arr) else None,
            "numeric_max": int(nums_arr.max()) if len(nums_arr) else None,
            "strictly_increasing_in_file": bool((diffs > 0).all()) if len(diffs) else None,
            "n_gaps": int((diffs > 1).sum()) if len(diffs) else None,
            "missing_numbers_in_range": int(nums_arr.max() - nums_arr.min() + 1 - len(set(nums)))
            if len(nums_arr)
            else None,
        },
        "parent_id": {
            "rows_with_parent": len(parents),
            "distinct_parents": len(parent_set),
            "parents_resolving_to_ids": sum(1 for p in parent_set if p in id_set),
            "max_children_per_parent": max(parent_set.values()) if parent_set else 0,
        },
        "cite": dict(cite_checks),
        "text_storage": {
            "field": TEXT_FIELD,
            **{k: int(v) for k, v in text.items()},
            "chars_total": int(tl.sum()) if len(tl) else 0,
            "length_percentiles": {
                str(p): float(np.percentile(tl, p)) for p in (1, 5, 25, 50, 75, 95, 99)
            }
            if len(tl)
            else {},
        },
    }
    return res, examples_private, ordered


def write_parquet(field_order: list[str]) -> dict[str, Any]:
    """Pass 2: write the slim Parquet.

    Columns: id, id_num, kind, parent_id, text, text_len, tags, plus every field whose
    name contains 'time', 'date' or 'agent'. Nested values are stored as JSON strings.

    Args:
        field_order: Field names in first-seen order from pass 1.

    Returns:
        Dict with the output path, column list and row count.
    """
    extra = [f for f in field_order if re.search(r"time|date|agent", f, re.I)]
    base = [f for f in ("id", "kind", "parent_id", TEXT_FIELD, "tags") if f in field_order]
    cols = base + [f for f in extra if f not in base]
    out = INTERIM_DIR / "corpus_slim.parquet"
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    buf: dict[str, list[Any]] = {}
    n = 0

    def flush() -> None:
        nonlocal writer, buf
        if not buf.get("id"):
            return
        table = pa.table({k: pa.array(v, type=pa.int64() if k in ("id_num", "text_len") else pa.string()) for k, v in buf.items()})
        if writer is None:
            writer = pq.ParquetWriter(out, table.schema, compression="zstd")
        writer.write_table(table)
        buf = {}

    for row in tqdm(iter_rows(), desc="E00 pass 2", unit="rows"):
        rec: dict[str, Any] = {}
        for c in cols:
            v = row.get(c)
            rec[c] = v if (v is None or isinstance(v, str)) else orjson.dumps(v).decode()
        m = ID_RE.match(str(row.get("id")))
        rec["id_num"] = int(m.group(1)) if m else None
        t = row.get(TEXT_FIELD)
        rec["text_len"] = len(t) if isinstance(t, str) else None
        for k, v in rec.items():
            buf.setdefault(k, []).append(v)
        n += 1
        if n % BATCH == 0:
            flush()
    flush()
    if writer is not None:
        writer.close()
    return {
        "path": "data/interim/corpus_slim.parquet",
        "columns": cols + ["id_num", "text_len"],
        "rows": n,
        "size_bytes": out.stat().st_size,
        "agent_field_found": any(re.search("agent", c, re.I) for c in cols),
    }


def main() -> None:
    """Run both passes and save results/E00_profile.json."""
    res, private, order = profile_pass()
    res["parquet"] = write_parquet(order)
    (INTERIM_DIR / "E00_text_examples.json").write_bytes(orjson.dumps(private, option=orjson.OPT_INDENT_2))
    f = res["fields"]
    time_fields = [k for k in order if re.search(r"time|date", k, re.I)]
    res["go_no_go"] = {
        "a_all_lines_parse": res["parse_errors"] == 0,
        "b_id_and_text_on_every_row": f.get("id", {}).get("non_empty") == res["n_rows"]
        and f.get(TEXT_FIELD, {}).get("present") == res["n_rows"],
        "c_ids_unique": res["ids"]["unique"] == res["ids"]["n"],
        "d_some_time_non_null": any(f[k]["non_null"] > 0 for k in time_fields),
    }
    params = {
        "example_trunc": EXAMPLE_TRUNC,
        "n_examples": N_EXAMPLES,
        "low_card_max": LOW_CARD_MAX,
        "distinct_cap": DISTINCT_CAP,
        "sampling": "none",
    }
    p = save_result("E00_profile", res, params)
    append_summary(
        "E00",
        {
            "n_rows": res["n_rows"],
            "file_size_bytes": res["file"]["size_bytes"],
            "n_fields": len(order),
            "parse_errors": res["parse_errors"],
            "ids_unique": res["ids"]["unique"],
            **{f"go_{k}": v for k, v in res["go_no_go"].items()},
        },
    )
    print("saved", p)
    print(orjson.dumps(res["go_no_go"]).decode())


if __name__ == "__main__":
    main()
