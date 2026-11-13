"""E54 - AI Village: are there enough false-claim cascades (claim, repeated by others, later corrected)?

Correction messages are found with a fixed phrase list. Each correction is linked to the most
similar earlier message in the same room (60 s to 72 h before, cosine >= 0.60): the target
claim. A candidate cascade is a distinct target that another agent repeated (cosine >= 0.80,
same room) after the target and before the correction. Embeddings are the cached E52 ones.
Only ids and aggregates go to results/; the reading sample with text goes to data/derived/.

Usage:
    python experiments/E54_ai_village_false_claims.py          # run and draw the sample
    python experiments/E54_ai_village_false_claims.py --tally  # count the sample labels

File structure:
    Constants     phrase list, thresholds
    profile       one village: corrections, targets, cascades
    tally         count labels of the reading sample
    main
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from experiments.E52_ai_village_semantic import VILLAGES, embed, load_village  # noqa: E402
from src.io_utils import REPO_ROOT, SEED, append_summary, save_result  # noqa: E402

DERIVED = REPO_ROOT / "data" / "derived"
SAMPLE_PATH = DERIVED / "E54_sample.jsonl"
LABELS_PATH = REPO_ROOT / "results" / "E54_sample_labels.json"
RESULT_PATH = REPO_ROOT / "results" / "E54_ai_village_false_claims.json"
PHRASES = [
    r"\bcorrection\b", r"\bi was wrong\b", r"\bwas (?:incorrect|wrong|inaccurate|mistaken|false)\b",
    r"\b(?:is|was) not (?:true|accurate|correct)\b", r"\bdoes(?:n't|n’t| not) (?:actually )?exist\b",
    r"\bdid(?:n't|n’t| not) (?:actually )?(?:exist|happen)\b",
    r"\bnever (?:actually )?(?:happened|existed|sent|published|merged)\b", r"\bno such\b", r"hallucinat",
    r"fabricat", r"\b404\b", r"\bnot actually\b", r"\bretract", r"\bmisreport", r"\bfalse (?:alarm|claim|report)\b",
    r"\bi misspoke\b", r"\bmy (?:earlier|previous) (?:claim|message|statement|report) was\b",
]
CORR_RE = re.compile("|".join(PHRASES), re.IGNORECASE)
TARGET_C, REPEAT_C = 0.60, 0.80
WINDOW_NS, MIN_LAG_NS = 72 * 3600 * 10**9, 60 * 10**9
SAMPLE_N, TRUE_MIN, GO_TOTAL = 30, 12, 50


def profile(v: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Corrections, targets and candidate cascades for one village.

    Args:
        v: Village folder.

    Returns:
        (aggregates, candidate cascade records with text for sampling)
    """
    df = load_village(v)
    if len(df) == 0:
        return {"messages_ge_10_words": 0}, []
    emb = embed(v, df["text"].tolist())
    t = df["t_ns"].to_numpy()
    spk = df["speaker"].to_numpy()
    room = df["room"].to_numpy()
    is_corr = np.array([bool(CORR_RE.search(x)) for x in df["text"]])
    out: dict[str, Any] = {"messages_ge_10_words": len(df), "corrections": int(is_corr.sum())}

    targets: dict[int, int] = {}  # target index -> earliest correction index
    for r in np.unique(room):
        idx = np.flatnonzero(room == r)
        tr = t[idx]
        for k in tqdm(np.flatnonzero(is_corr[idx]), desc=f"targets {v}/{str(r)[:8]}", unit="corr", leave=False):
            c = idx[k]
            lo = np.searchsorted(tr, t[c] - WINDOW_NS, "left")
            hi = np.searchsorted(tr, t[c] - MIN_LAG_NS, "right")
            if hi <= lo:
                continue
            w = idx[lo:hi]
            sims = emb[w] @ emb[c]
            j = int(np.argmax(sims))
            if sims[j] >= TARGET_C:
                s = int(w[j])
                if s not in targets or t[c] < t[targets[s]]:
                    targets[s] = int(c)
    out["targets"] = len(targets)

    recs, n_rep, self_corr, gap_h = [], [], 0, []
    for s, c in tqdm(sorted(targets.items()), desc=f"repeats {v}", unit="target"):
        idx = np.flatnonzero(room == room[s])
        tr = t[idx]
        lo = np.searchsorted(tr, t[s] + MIN_LAG_NS, "left")
        hi = np.searchsorted(tr, t[c], "left")
        if hi <= lo:
            continue
        w = idx[lo:hi]
        w = w[spk[w] != spk[s]]
        if not len(w):
            continue
        sims = emb[w] @ emb[s]
        rep = w[sims >= REPEAT_C]
        if not len(rep):
            continue
        n_rep.append(len(set(spk[rep])))
        self_corr += int(spk[c] == spk[s])
        gap_h.append((t[c] - t[s]) / 3.6e12)
        first = int(rep[0])
        recs.append({"village": v, "target_id": df.at[s, "id"], "repeat_id": df.at[first, "id"],
                     "correction_id": df.at[c, "id"], "repeating_agents": len(set(spk[rep])),
                     "target_text": df.at[s, "text"][:600], "repeat_text": df.at[first, "text"][:600],
                     "correction_text": df.at[c, "text"][:600]})
    out["candidate_cascades"] = len(recs)
    if recs:
        out["repeating_agents_per_cascade"] = {"median": float(np.median(n_rep)), "max": int(max(n_rep)),
                                               "share_ge_2": float(np.mean(np.array(n_rep) >= 2))}
        out["self_correction_share"] = self_corr / len(recs)
        out["hours_target_to_correction"] = {"p25": float(np.percentile(gap_h, 25)),
                                             "median": float(np.median(gap_h)),
                                             "p75": float(np.percentile(gap_h, 75))}
    return out, recs


def tally() -> None:
    """Count labels in results/E54_sample_labels.json and add GO to the E54 result."""
    lab = json.loads(LABELS_PATH.read_text(encoding="utf-8"))["labels"]
    n_true = sum(1 for r in lab if r["label"] == "true")
    res = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    r = res["results"]
    share = n_true / len(lab)
    r["sample"] = {"n": len(lab), "true": n_true, "share_true": share}
    r["estimated_true_cascades"] = r["pooled"]["candidate_cascades"] * share
    r["go_a"] = bool(n_true >= TRUE_MIN)
    r["go_b"] = bool(r["estimated_true_cascades"] >= GO_TOTAL)
    r["go"] = bool(r["go_a"] and r["go_b"])
    RESULT_PATH.write_text(json.dumps(res, indent=1), encoding="utf-8")
    append_summary("E54", {"candidates": r["pooled"]["candidate_cascades"], "true_in_sample": n_true,
                           "estimated_true": r["estimated_true_cascades"], "go": r["go"]})
    print(json.dumps(r["sample"]), round(r["estimated_true_cascades"], 1), "GO" if r["go"] else "NO-GO")


def main() -> None:
    """Run E54 and write results plus the reading sample."""
    if "--tally" in sys.argv:
        tally()
        return
    res: dict[str, Any] = {"villages": {}}
    recs: list[dict[str, Any]] = []
    for v in VILLAGES:
        res["villages"][v], r = profile(v)
        recs += r
    res["pooled"] = {k: sum(x.get(k, 0) for x in res["villages"].values())
                     for k in ("corrections", "targets", "candidate_cascades")}
    rng = np.random.default_rng(SEED)
    pick = sorted(rng.choice(len(recs), size=min(SAMPLE_N, len(recs)), replace=False).tolist()) if recs else []
    DERIVED.mkdir(parents=True, exist_ok=True)
    with open(SAMPLE_PATH, "w", encoding="utf-8") as f:
        for k in pick:
            f.write(json.dumps({"k": k, **recs[k]}, ensure_ascii=False) + "\n")
    res["sample_ids"] = [{key: recs[k][key] for key in ("village", "target_id", "repeat_id", "correction_id")}
                         for k in pick]
    save_result("E54_ai_village_false_claims", res, {"phrases": PHRASES, "target_cosine": TARGET_C,
                                                    "repeat_cosine": REPEAT_C, "window_h": 72, "min_lag_s": 60,
                                                    "sample_n": SAMPLE_N, "true_min": TRUE_MIN,
                                                    "go_total": GO_TOTAL, "embeddings": "E52 cache"})
    print(json.dumps(res["pooled"], indent=1))


if __name__ == "__main__":
    main()
