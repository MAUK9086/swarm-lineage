"""E51 - AI Village feasibility: how much agent-to-agent copying is there?

For each village, agent chat messages are collapsed to unique normalised texts. Candidate
similar pairs come from MinHash/LSH; exact 5-word-shingle Jaccard is then computed. A message is
a candidate copy event if an EARLIER message by a DIFFERENT agent, in the same village, has
Jaccard in [0.5, 0.95] with it (edited reuse). Exact reuse (same normalised text) and near-exact
reuse (Jaccard > 0.95) are counted separately. Clusters are connected components of the
edited-reuse graph over unique texts. Only aggregates are saved; no message text.

File structure:
    Constants       villages, window, pair budget
    load_village    agent messages as (text, speaker, time)
    profile         one village: pairs, events, clusters, time gaps
    main
"""

from __future__ import annotations

import bisect
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
from src.copydir import (  # noqa: E402
    band_pair_upper_bound,
    jaccard_csr,
    lsh_candidate_pairs,
    lsh_pairs_sampled,
    minhash_signatures,
    norm_text_hash,
    shingle_hashes_csr,
)
from src.io_utils import REPO_ROOT, SEED, append_summary, save_result  # noqa: E402

BASE = REPO_ROOT / "data" / "raw" / "ai_village"
VILLAGES = ("main-village", "open-chat-village", "swarm-village", "saboteur-rpg-village", "game-jam-village")
LO, HI = 0.5, 0.95
MAX_PAIRS = 20_000_000
GO_EVENTS, GO_CLUSTERS = 200, 30


def load_village(v: str) -> tuple[pd.DataFrame, dict[str, int]]:
    """Agent chat messages of one village.

    Args:
        v: Village folder.

    Returns:
        (frame with text, speaker, t_ns; counts)
    """
    rows, counts = [], {"messages": 0, "agent_messages": 0, "human_messages": 0}
    with gzip.open(BASE / v / "chat_messages.jsonl.gz", "rt", encoding="utf-8") as f:
        for line in tqdm(f, desc=f"read {v}", unit="msg"):
            r = json.loads(line)
            counts["messages"] += 1
            if r.get("speaker_type") == "agent" and r.get("agent_speaker_id"):
                counts["agent_messages"] += 1
                rows.append((r.get("content") or "", r["agent_speaker_id"], r["created_at"]))
            else:
                counts["human_messages"] += 1
    df = pd.DataFrame(rows, columns=["text", "speaker", "t"])
    df["t_ns"] = pd.to_datetime(df["t"], utc=True, errors="coerce", format="mixed").astype("int64")
    df = df.drop(columns="t")
    counts["agents"] = int(df["speaker"].nunique())
    return df, counts


def profile(v: str) -> dict[str, Any]:
    """Pairs, copy events, clusters and time gaps for one village.

    Args:
        v: Village folder.

    Returns:
        Aggregate results.
    """
    df, out = load_village(v)
    df["h"] = [norm_text_hash(t) for t in df["text"]]
    df = df[df["h"] != ""]
    g = df.groupby("h", sort=False)
    first = g.head(1)
    texts = first["text"].tolist()
    hashes = first["h"].to_numpy()
    node_of = {h: k for k, h in enumerate(hashes)}
    n = len(texts)
    msgs = [[] for _ in range(n)]
    for h, sp, t in zip(df["h"], df["speaker"], df["t_ns"]):
        msgs[node_of[h]].append((t, sp))
    for m in msgs:
        m.sort()
    flat, off = shingle_hashes_csr(texts, n)
    use = np.diff(off) > 0
    out.update({"unique_texts": n, "unique_texts_with_shingles": int(use.sum()),
                "agent_messages_with_shingles": int(sum(len(msgs[k]) for k in np.flatnonzero(use)))})

    # exact reuse: same normalised text, earlier message by another agent
    exact = 0
    for m in msgs:
        for k in range(1, len(m)):
            if any(sp != m[k][1] for _, sp in m[:k]):
                exact += 1
    out["exact_reuse_events"] = exact

    sig = minhash_signatures(flat, off, seed=SEED)
    bound = band_pair_upper_bound(sig, use)
    out["band_pair_upper_bound"] = int(bound)
    if bound <= MAX_PAIRS:
        i, j = lsh_candidate_pairs(sig, use)
        out["pair_sampling_rate"] = 1.0
    else:
        rate = MAX_PAIRS / bound
        i, j = lsh_pairs_sampled(sig, use, np.arange(n), rate, seed=SEED)
        out["pair_sampling_rate"] = rate
    del sig
    jac = jaccard_csr(flat, off, i, j)
    near = jac[(jac["jaccard"] >= LO) & (jac["jaccard"] <= HI)]
    out["candidate_pairs"] = int(len(jac))
    out["edited_pairs_0.5_0.95"] = int(len(near))
    out["near_exact_pairs_gt_0.95"] = int((jac["jaccard"] > HI).sum())

    # message-level edited-reuse events: earlier message by another agent in a linked text
    gap: dict[tuple[int, int], int] = {}
    times = [np.array([t for t, _ in m]) for m in msgs]
    for a, b in tqdm(zip(near["i"].to_numpy(), near["j"].to_numpy()), total=len(near), desc=f"events {v}", unit="pair"):
        for x, y in ((a, b), (b, a)):
            for k, (t, sp) in enumerate(msgs[y]):
                pos = bisect.bisect_left(times[x], t)
                for q in range(pos - 1, -1, -1):
                    if msgs[x][q][1] != sp:
                        key = (int(y), k)
                        d = int(t - msgs[x][q][0])
                        if key not in gap or d < gap[key]:
                            gap[key] = d
                        break
    out["edited_reuse_events"] = len(gap)
    if len(near) and len(gap):
        comp = union_find(near["i"].to_numpy(), near["j"].to_numpy())
        comp_of = dict(zip(near["i"].to_numpy(), comp)) | dict(zip(near["j"].to_numpy(), comp))
        ev_comp = pd.Series([comp_of[y] for y, _ in gap])
        sizes = ev_comp.value_counts()
        out["clusters_with_events"] = int(sizes.size)
        out["largest_cluster_event_share"] = float(sizes.iloc[0] / len(gap)) if len(gap) else None
        out["clusters_with_ge_5_events"] = int((sizes >= 5).sum())
        gaps_h = np.array(list(gap.values())) / 3.6e12
        out["gap_hours"] = {"median": float(np.median(gaps_h)), "p25": float(np.percentile(gaps_h, 25)),
                            "p75": float(np.percentile(gaps_h, 75)),
                            "share_le_1h": float((gaps_h <= 1).mean()), "share_le_24h": float((gaps_h <= 24).mean())}
    else:
        out.update({"clusters_with_events": 0, "largest_cluster_event_share": None, "clusters_with_ge_5_events": 0})
    return out


def main() -> None:
    """Run E51 and write results/E51_ai_village_feasibility.json."""
    res: dict[str, Any] = {"villages": {v: profile(v) for v in VILLAGES}}
    tot_ev = sum(r["edited_reuse_events"] for r in res["villages"].values())
    tot_cl = sum(r["clusters_with_events"] for r in res["villages"].values())
    res["pooled"] = {"edited_reuse_events": tot_ev, "clusters_with_events": tot_cl,
                     "exact_reuse_events": sum(r["exact_reuse_events"] for r in res["villages"].values()),
                     "agent_messages": sum(r["agent_messages"] for r in res["villages"].values())}
    res["go"] = bool(tot_ev >= GO_EVENTS and tot_cl >= GO_CLUSTERS)
    save_result("E51_ai_village_feasibility", res, {"villages": list(VILLAGES), "jaccard_window": [LO, HI],
                                                    "shingle_k": 5, "max_pairs": MAX_PAIRS, "go_events": GO_EVENTS,
                                                    "go_clusters": GO_CLUSTERS, "data": "aidigestorg/ai-village chat_messages"})
    append_summary("E51", {"events": tot_ev, "clusters": tot_cl, "go": res["go"]})
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
