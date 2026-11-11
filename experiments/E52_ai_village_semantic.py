"""E52 - AI Village feasibility, part 2: do agents restate each other's content (paraphrase)?

Agent chat messages with at least 10 words are embedded with all-MiniLM-L6-v2. A message m by
agent A at time t is a restatement event at threshold c if a message s by a different agent B
in the same room, with 60 s <= t - t_s <= 24 h, has cosine(m, s) >= c, and A has no message
(any room) in [t - 24 h, t_s) with cosine >= c to m. Each message counts once; clusters are
connected components of all qualifying (m, s) edges. Only aggregates are saved to results/;
the 30-event reading sample (with text) goes to data/derived/, which is gitignored.

Usage:
    python experiments/E52_ai_village_semantic.py          # run and draw the sample
    python experiments/E52_ai_village_semantic.py --tally  # count the sample labels

File structure:
    Constants       villages, thresholds, windows
    load_village    agent messages with >= 10 words
    embed           cached sentence embeddings
    profile         one village: events, clusters, lags, lag-bin rates
    tally           count labels of the reading sample
    main
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.clusters import union_find  # noqa: E402
from src.copydir import shingles  # noqa: E402
from src.io_utils import REPO_ROOT, SEED, append_summary, save_result  # noqa: E402

BASE = REPO_ROOT / "data" / "raw" / "ai_village"
DERIVED = REPO_ROOT / "data" / "derived"
VILLAGES = ("main-village", "open-chat-village", "swarm-village", "saboteur-rpg-village", "game-jam-village")
MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MAIN_C = 0.80
THRESHOLDS = (0.70, 0.80, 0.90)
MIN_WORDS = 10
MIN_LAG_NS = 60 * 10**9
MAX_LAG_NS = 24 * 3600 * 10**9
LAG_BINS_S = (60, 600, 3600, 6 * 3600, 24 * 3600)
LAG_LABELS = ("1-10 min", "10-60 min", "1-6 h", "6-24 h")
SAMPLE_N, SPECIFIC_MIN = 30, 15
GO_EVENTS, GO_CLUSTERS = 200, 30
SAMPLE_PATH = DERIVED / "E52_sample.jsonl"
LABELS_PATH = REPO_ROOT / "results" / "E52_sample_labels.json"


def load_village(v: str) -> pd.DataFrame:
    """Agent chat messages with at least MIN_WORDS words, sorted by time then id.

    Args:
        v: Village folder.

    Returns:
        Frame with id, text, speaker, room, t_ns.
    """
    rows = []
    with gzip.open(BASE / v / "chat_messages.jsonl.gz", "rt", encoding="utf-8") as f:
        for line in tqdm(f, desc=f"read {v}", unit="msg"):
            r = json.loads(line)
            text = r.get("content") or ""
            if r.get("speaker_type") == "agent" and r.get("agent_speaker_id") and len(text.split()) >= MIN_WORDS:
                rows.append((str(r["id"]), text, r["agent_speaker_id"], str(r.get("room_id")), r["created_at"]))
    df = pd.DataFrame(rows, columns=["id", "text", "speaker", "room", "t"])
    df["t_ns"] = pd.to_datetime(df["t"], utc=True, format="mixed").dt.as_unit("ns").astype("int64")
    return df.drop(columns="t").sort_values(["t_ns", "id"], kind="stable").reset_index(drop=True)


def embed(v: str, texts: list[str]) -> np.ndarray:
    """Normalised embeddings, cached under data/derived/.

    Args:
        v: Village folder (cache key).
        texts: Messages in frame order.

    Returns:
        (n, 384) float32 array.
    """
    path = DERIVED / f"E52_emb_{v}.npy"
    if path.exists():
        e = np.load(path)
        if len(e) == len(texts):
            return e
    from sentence_transformers import SentenceTransformer
    import torch

    torch.manual_seed(SEED)
    model = SentenceTransformer(MODEL, device="cpu")
    e = model.encode(texts, batch_size=64, show_progress_bar=True, normalize_embeddings=True,
                     convert_to_numpy=True).astype(np.float32)
    DERIVED.mkdir(parents=True, exist_ok=True)
    np.save(path, e)
    return e


def profile(v: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Restatement events, clusters, lags and lag-bin rates for one village.

    Args:
        v: Village folder.

    Returns:
        (aggregates, event records at MAIN_C for sampling)
    """
    df = load_village(v)
    out: dict[str, Any] = {"messages_ge_10_words": len(df), "agents": int(df["speaker"].nunique()),
                           "rooms": int(df["room"].nunique())}
    if len(df) == 0:
        return out, []
    emb = embed(v, df["text"].tolist())
    t = df["t_ns"].to_numpy()
    spk = pd.factorize(df["speaker"])[0]

    # earliest own message (any room) in [t - 24 h, t) with cosine >= c, per message and threshold
    first_own = np.full((len(df), len(THRESHOLDS)), np.iinfo(np.int64).max, dtype=np.int64)
    for a in tqdm(np.unique(spk), desc=f"own {v}", unit="agent"):
        idx = np.flatnonzero(spk == a)
        ta = t[idx]
        for k, m in enumerate(idx):
            lo = np.searchsorted(ta, t[m] - MAX_LAG_NS, "left")
            hi = np.searchsorted(ta, t[m], "left")
            if hi <= lo:
                continue
            sims = emb[idx[lo:hi]] @ emb[m]
            for c_i, c in enumerate(THRESHOLDS):
                hit = np.flatnonzero(sims >= c)
                if len(hit):
                    first_own[m, c_i] = ta[lo + hit[0]]

    edges = {c: [] for c in THRESHOLDS}
    best: dict[int, tuple[float, int]] = {}
    pair_tot = np.zeros(len(LAG_LABELS), dtype=np.int64)
    pair_hit = np.zeros(len(LAG_LABELS), dtype=np.int64)
    edges_ns = np.array(LAG_BINS_S, dtype=np.int64) * 10**9
    for room, grp in df.groupby("room", sort=False):
        idx = grp.index.to_numpy()
        tr = t[idx]
        for k, m in enumerate(tqdm(idx, desc=f"pairs {v}/{room[:8]}", unit="msg", leave=False)):
            lo = np.searchsorted(tr, t[m] - MAX_LAG_NS, "left")
            hi = np.searchsorted(tr, t[m] - MIN_LAG_NS, "right")
            if hi <= lo:
                continue
            w = idx[lo:hi]
            other = spk[w] != spk[m]
            if not other.any():
                continue
            w = w[other]
            sims = emb[w] @ emb[m]
            b = np.clip(np.searchsorted(edges_ns, t[m] - t[w], "right") - 1, 0, len(LAG_LABELS) - 1)
            pair_tot += np.bincount(b, minlength=len(LAG_LABELS))
            pair_hit += np.bincount(b[sims >= MAIN_C], minlength=len(LAG_LABELS))
            for c_i, c in enumerate(THRESHOLDS):
                ok = (sims >= c) & (t[w] < first_own[m, c_i])
                for s in w[ok]:
                    edges[c].append((int(m), int(s)))
                if c == MAIN_C and ok.any():
                    j = int(np.argmax(np.where(ok, sims, -1.0)))
                    best[int(m)] = (float(sims[j]), int(w[j]))

    for c in THRESHOLDS:
        e = np.array(edges[c], dtype=np.int64).reshape(-1, 2)
        key = f"c{c:.2f}"
        ev = np.unique(e[:, 0]) if len(e) else np.array([], dtype=np.int64)
        out[f"events_{key}"] = int(len(ev))
        out[f"edges_{key}"] = int(len(e))
        if len(e):
            comp = union_find(e[:, 0], e[:, 1])
            comp_of = dict(zip(e[:, 0], comp)) | dict(zip(e[:, 1], comp))
            sizes = pd.Series([comp_of[m] for m in ev]).value_counts()
            out[f"clusters_{key}"] = int(sizes.size)
            out[f"largest_cluster_event_share_{key}"] = float(sizes.iloc[0] / len(ev))
            out[f"clusters_ge_5_events_{key}"] = int((sizes >= 5).sum())
        else:
            out[f"clusters_{key}"] = 0

    recs = []
    if best:
        ms = np.array(sorted(best))
        ss = np.array([best[m][1] for m in ms])
        lag_min = (t[ms] - t[ss]) / 6e10
        lex = np.array([_jacc(df.at[m, "text"], df.at[s, "text"]) >= 0.5 for m, s in zip(ms, ss)])
        out["best_source_lag_minutes"] = {q: float(np.percentile(lag_min, p)) for q, p in
                                          (("p25", 25), ("median", 50), ("p75", 75))}
        out["share_events_lexical_jaccard_ge_0.5"] = float(lex.mean())
        out["distinct_agent_pairs"] = int(len({(spk[s], spk[m]) for m, s in zip(ms, ss)}))
        out["events_per_later_agent_top_share"] = float(pd.Series(spk[ms]).value_counts().iloc[0] / len(ms))
        for m, s in zip(ms, ss):
            recs.append({"village": v, "later_id": df.at[m, "id"], "source_id": df.at[s, "id"],
                         "cosine": round(best[m][0], 3), "lag_min": round((t[m] - t[s]) / 6e10, 1),
                         "later_text": df.at[m, "text"][:700], "source_text": df.at[s, "text"][:700]})
    out["lag_bin_rate_c0.80"] = {lab: {"pairs": int(n), "hits": int(h), "rate": float(h / n) if n else None}
                                 for lab, n, h in zip(LAG_LABELS, pair_tot, pair_hit)}
    return out, recs


def _jacc(a: str, b: str) -> float:
    """5-word-shingle Jaccard of two texts."""
    sa, sb = shingles(a), shingles(b)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def tally() -> None:
    """Count labels in results/E52_sample_labels.json and add them to the E52 result."""
    lab = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    n_spec = sum(1 for r in lab["labels"] if r["label"] == "specific")
    path = REPO_ROOT / "results" / "E52_ai_village_semantic.json"
    res = json.loads(path.read_text(encoding="utf-8"))
    res["results"]["sample"] = {"n": len(lab["labels"]), "specific": n_spec, "generic": len(lab["labels"]) - n_spec}
    res["results"]["go_b"] = bool(n_spec >= SPECIFIC_MIN)
    res["results"]["go"] = bool(res["results"]["go_a"] and res["results"]["go_b"])
    path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    append_summary("E52b", {"specific": n_spec, "n": len(lab["labels"]), "go": res["results"]["go"]})
    print(json.dumps(res["results"]["sample"]), "GO" if res["results"]["go"] else "NO-GO")


def main() -> None:
    """Run E52 and write results/E52_ai_village_semantic.json plus the reading sample."""
    if "--tally" in sys.argv:
        tally()
        return
    res: dict[str, Any] = {"villages": {}}
    recs: list[dict[str, Any]] = []
    for v in VILLAGES:
        res["villages"][v], r = profile(v)
        recs += r
    pooled = {}
    for c in THRESHOLDS:
        key = f"c{c:.2f}"
        pooled[f"events_{key}"] = sum(r.get(f"events_{key}", 0) for r in res["villages"].values())
        pooled[f"clusters_{key}"] = sum(r.get(f"clusters_{key}", 0) for r in res["villages"].values())
    res["pooled"] = pooled
    res["go_a"] = bool(pooled["events_c0.80"] >= GO_EVENTS and pooled["clusters_c0.80"] >= GO_CLUSTERS)
    rng = np.random.default_rng(SEED)
    pick = sorted(rng.choice(len(recs), size=min(SAMPLE_N, len(recs)), replace=False).tolist()) if recs else []
    DERIVED.mkdir(parents=True, exist_ok=True)
    with open(SAMPLE_PATH, "w", encoding="utf-8") as f:
        for k in pick:
            f.write(json.dumps({"k": k, **recs[k]}, ensure_ascii=False) + "\n")
    res["sample_event_ids"] = [{"village": recs[k]["village"], "later_id": recs[k]["later_id"],
                                "source_id": recs[k]["source_id"]} for k in pick]
    save_result("E52_ai_village_semantic", res, {"villages": list(VILLAGES), "model": MODEL, "main_cosine": MAIN_C,
                                                "thresholds": list(THRESHOLDS), "min_words": MIN_WORDS,
                                                "lag_window_s": [60, 86400], "sample_n": SAMPLE_N,
                                                "specific_min": SPECIFIC_MIN, "go_events": GO_EVENTS,
                                                "go_clusters": GO_CLUSTERS,
                                                "data": "aidigestorg/ai-village chat_messages"})
    append_summary("E52", {"events": pooled["events_c0.80"], "clusters": pooled["clusters_c0.80"], "go_a": res["go_a"]})
    print(json.dumps({"pooled": pooled, "go_a": res["go_a"]}, indent=1))


if __name__ == "__main__":
    main()
