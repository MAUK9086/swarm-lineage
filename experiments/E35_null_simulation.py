"""E35 - Null simulation: how often pair-level vs component-level analysis declares significance.

Times are permuted within each component (inside src/evaluate.py), which keeps the
cluster structure and removes any real order signal. Length-rule predictions are fixed.

File structure:
    Constants   draws, cap, bootstrap resamples
    main        run the draws, count significant results, save results
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.clusters import cap_pairs, doc_codes, macro_bootstrap, union_find, wald_ci, wilson_ci  # noqa: E402
from src.copydir import assert_public, predict_length  # noqa: E402
from src.evaluate import null_order_draws, split_truth  # noqa: E402
from src.io_utils import INTERIM_DIR, SEED, append_summary, save_result  # noqa: E402

N_DRAWS = 1000
CAP = 20
N_BOOT = 1000


def main() -> None:
    """Run E35 and write results/E35_null_simulation.json."""
    table = pd.read_parquet(INTERIM_DIR / "moltbook_slim.parquet")
    public, truth = split_truth(table)
    del table
    assert_public(public)
    pairs = pd.read_parquet(INTERIM_DIR / "E31_pairs.parquet")
    text_of = dict(zip(public["doc_id"], public["text"]))
    a, b, docs = doc_codes(pairs["doc_a"].to_numpy(), pairs["doc_b"].to_numpy())
    lens = np.array([len(text_of[d]) for d in docs])
    pred, _ = predict_length(lens[a], lens[b], seed=SEED)
    comp = union_find(a, b)
    doc_group = np.empty(len(docs), dtype=np.int64)
    doc_group[a] = comp
    doc_group[b] = comp
    cap_idx = cap_pairs(comp, CAP, seed=SEED)

    pair_acc, comp_acc, pair_sig, comp_sig, dropped = [], [], 0, 0, []
    for r, (a_earlier, valid) in enumerate(tqdm(null_order_draws(truth, docs, doc_group, a, b, N_DRAWS, seed=SEED),
                                                total=N_DRAWS, desc="null draws")):
        ok = (pred == a_earlier)
        p = float(ok[valid].mean())
        ci = wald_ci(p, int(valid.sum()))
        pair_acc.append(p)
        pair_sig += int(ci[0] > 0.5 or ci[1] < 0.5)
        v = valid[cap_idx]
        m = macro_bootstrap(ok[cap_idx][v].astype(float), comp[cap_idx][v], n_boot=N_BOOT, seed=SEED + r)
        comp_acc.append(m["macro"])
        comp_sig += int(m["ci_low"] > 0.5 or m["ci_high"] < 0.5)
        dropped.append(int((~valid).sum()))

    pa, ca = np.array(pair_acc), np.array(comp_acc)
    res: dict[str, Any] = {
        "draws": N_DRAWS, "pairs": int(len(pairs)), "components": int(len(np.unique(comp))),
        "capped_pairs": int(len(cap_idx)),
        "equal_time_pairs_dropped_per_draw": {"mean": float(np.mean(dropped)), "max": int(np.max(dropped))},
        "pair_level": {"significant": pair_sig, "false_positive_rate": pair_sig / N_DRAWS,
                       "fpr_wilson_ci": wilson_ci(pair_sig, N_DRAWS),
                       "accuracy_across_draws": {"mean": float(pa.mean()), "sd": float(pa.std()),
                                                 "p2.5": float(np.percentile(pa, 2.5)), "p97.5": float(np.percentile(pa, 97.5))}},
        "component_level": {"significant": comp_sig, "false_positive_rate": comp_sig / N_DRAWS,
                            "fpr_wilson_ci": wilson_ci(comp_sig, N_DRAWS),
                            "macro_across_draws": {"mean": float(ca.mean()), "sd": float(ca.std()),
                                                   "p2.5": float(np.percentile(ca, 2.5)), "p97.5": float(np.percentile(ca, 97.5))}},
    }
    res["criterion"] = {"naive_fpr_gt_10pct": res["pair_level"]["false_positive_rate"] > 0.10,
                        "component_fpr_le_10pct": res["component_level"]["false_positive_rate"] <= 0.10}
    res["criterion"]["naive_miscalibrated"] = res["criterion"]["naive_fpr_gt_10pct"] and res["criterion"]["component_fpr_le_10pct"]
    save_result("E35_null_simulation", res, {"draws": N_DRAWS, "cap": CAP, "n_boot": N_BOOT, "seed": "42 + r",
                                             "null": "permute true times within each component"})
    append_summary("E35", {"fpr_pair_level": res["pair_level"]["false_positive_rate"],
                           "fpr_component_level": res["component_level"]["false_positive_rate"],
                           "naive_miscalibrated": res["criterion"]["naive_miscalibrated"]})
    print(res["pair_level"], res["component_level"], res["criterion"])


if __name__ == "__main__":
    main()
