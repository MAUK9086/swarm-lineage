"""E43 - Copy-direction robustness on Moltbook: Jaccard threshold, two-stage bootstrap,
author-merged clusters.

Reads E31's scored pairs. The component pipeline (template filter, cap of 20 pairs per
cluster, cues, cluster bootstrap) follows E32 / experiments/E36_replication.py exactly;
the Jaccard 0.5 row must reproduce E32. Method code sees text and author ids only; time is
read only through src/evaluate.py.

File structure:
    Constants         thresholds, cap, paths
    capped_scored     E32 pipeline up to the capped, scored pairs (per-pair arrays kept)
    cue_predictions   predictions of every cue on the capped pairs
    two_stage         cluster-then-pair bootstrap on all eligible pairs (length, containment)
    author_merged     merge clusters that share an author; re-bootstrap
    main
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.clusters import doc_codes, macro_bootstrap, union_find  # noqa: E402
from src.copydir import (  # noqa: E402
    assert_public,
    predict_containment,
    predict_extension,
    predict_insdel,
    predict_length,
    predict_random,
    shingles,
    tokens,
)
from src.evaluate import component_accuracy, order_from_codes, split_truth, truth_codes  # noqa: E402
from src.io_utils import INTERIM_DIR, REPO_ROOT, SEED, append_summary, save_result  # noqa: E402

THRESHOLDS = (0.5, 0.6, 0.7, 0.8)
J_HI = 0.95
CAP = 20
N_BOOT = 1000
GO_MARGIN = 0.05
CUES = ("c_containment", "i_extension", "ii_insertion_vs_deletion")
CONFIG = REPO_ROOT / "configs" / "E36_pipeline.json"


def capped_scored(a: np.ndarray, b: np.ndarray, ssize: np.ndarray, tc: np.ndarray) -> dict[str, Any]:
    """Components, template filter, cap and time validity, as in E32.

    Args:
        a: Doc code of the first element per pair (pairs in E31 order).
        b: Doc code of the second element per pair.
        ssize: Shingle-set size per doc code.
        tc: Time codes per doc code (from src/evaluate.py).

    Returns:
        Dict with comp (all pairs), kept mask, capped indices, a_earlier for capped, counts.
    """
    comp = union_find(a, b)
    eq = pd.Series(ssize[a] == ssize[b]).groupby(comp).all()
    dropped = eq[eq].index
    kept_mask = ~pd.Series(comp).isin(dropped).to_numpy()
    kept_idx = np.flatnonzero(kept_mask)
    r = np.random.default_rng(SEED).random(len(kept_idx))
    df = pd.DataFrame({"comp": comp[kept_idx], "r": r, "idx": kept_idx})
    capped = df.sort_values(["comp", "r"]).groupby("comp", sort=False).head(CAP)["idx"].to_numpy()
    a_earlier, valid = order_from_codes(tc, a[capped], b[capped])
    sizes = pd.Series(comp).value_counts()
    counts = {"pairs": int(len(a)), "components": int(eq.size), "components_dropped_all_equal_size": int(len(dropped)),
              "pairs_in_dropped_components": int((~kept_mask).sum()), "pairs_after_cap": int(len(capped)),
              "pairs_equal_time_dropped": int((~valid).sum()),
              "largest_cluster_share_of_pairs": float(sizes.iloc[0] / len(a)),
              "two_largest_share_of_pairs": float(sizes.iloc[:2].sum() / len(a))}
    capped, a_earlier = capped[valid], a_earlier[valid]
    counts["pairs_scored"] = int(len(capped))
    counts["components_scored"] = int(pd.unique(comp[capped]).size)
    return {"comp": comp, "kept_mask": kept_mask, "capped": capped, "a_earlier": a_earlier, "counts": counts}


def cue_predictions(texts_a: list[str], texts_b: list[str]) -> dict[str, np.ndarray]:
    """Predictions ('a came first') of every cue, as in experiments/E36_replication.py.

    Args:
        texts_a: Texts of the first elements.
        texts_b: Texts of the second elements.

    Returns:
        Cue name -> boolean prediction array.
    """
    toks_a, toks_b = [tokens(x) for x in texts_a], [tokens(x) for x in texts_b]
    sh_a, sh_b = [shingles(x) for x in texts_a], [shingles(x) for x in texts_b]
    inter = np.array([len(x & y) for x, y in zip(sh_a, sh_b)])
    return {
        "a_random": predict_random(len(texts_a), seed=SEED),
        "b_longer_is_later": predict_length(np.array([len(x) for x in texts_a]), np.array([len(x) for x in texts_b]), seed=SEED)[0],
        "c_containment": predict_containment(inter, np.array([len(x) for x in sh_a]), np.array([len(x) for x in sh_b]), seed=SEED)[0],
        "i_extension": predict_extension(toks_a, toks_b, seed=SEED)[0],
        "ii_insertion_vs_deletion": predict_insdel(toks_a, toks_b, seed=SEED)[0],
    }


def go_rule(methods: dict[str, Any]) -> dict[str, Any]:
    """E32's GO rule for each cue against length, plus whether the length CI includes 0.5.

    Args:
        methods: Cue name -> component_accuracy output.

    Returns:
        Dict of rule outcomes.
    """
    base = methods["b_longer_is_later"]["macro"]
    out: dict[str, Any] = {}
    for c in CUES:
        m = methods[c]
        out[c] = {"margin_vs_length": m["macro"] - base,
                  "passes_go": bool(m["macro"] - base >= GO_MARGIN and m["ci_low"] > base)}
    ln = methods["b_longer_is_later"]
    out["length_ci_includes_0.5"] = bool(ln["ci_low"] <= 0.5 <= ln["ci_high"])
    out["robust"] = bool(not any(out[c]["passes_go"] for c in CUES) and out["length_ci_includes_0.5"])
    return out


def two_stage(correct: np.ndarray, comp: np.ndarray, n_boot: int, seed: int) -> dict[str, Any]:
    """Resample clusters, then min(CAP, n) pairs without replacement inside each drawn cluster.

    Args:
        correct: 1.0 / 0.0 per eligible pair.
        comp: Cluster id per eligible pair.
        n_boot: Resamples.
        seed: Random seed.

    Returns:
        Dict with the expected macro (uncapped per-cluster mean) and the two-stage 95% CI.
    """
    g = pd.Series(correct).groupby(comp)
    k_corr = g.sum().to_numpy().astype(np.int64)
    n = g.size().to_numpy().astype(np.int64)
    draw = np.minimum(n, CAP)
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    for r in tqdm(range(n_boot), desc="two-stage bootstrap", unit="draw"):
        pick = rng.integers(0, n.size, n.size)
        hits = rng.hypergeometric(k_corr[pick], n[pick] - k_corr[pick], draw[pick])
        boots[r] = (hits / draw[pick]).mean()
    return {"macro_all_pairs": float((k_corr / n).mean()), "ci": [float(np.percentile(boots, 2.5)),
            float(np.percentile(boots, 97.5))], "clusters": int(n.size), "eligible_pairs": int(n.sum())}


def author_merged(comp_capped: np.ndarray, comp_all: np.ndarray, a: np.ndarray, b: np.ndarray,
                  kept_mask: np.ndarray, author_code: np.ndarray) -> tuple[np.ndarray, dict[str, int]]:
    """Merge clusters that share any author (over all docs of each kept cluster).

    Args:
        comp_capped: Cluster id per capped scored pair.
        comp_all: Cluster id per pair (all pairs).
        a: Doc code of the first element per pair.
        b: Doc code of the second element per pair.
        kept_mask: Pairs in clusters kept by the template filter.
        author_code: Author code per doc code (-1 if unknown).

    Returns:
        (merged unit id per capped pair, counts)
    """
    docs_comp = pd.DataFrame({"doc": np.concatenate([a[kept_mask], b[kept_mask]]),
                              "comp": np.concatenate([comp_all[kept_mask], comp_all[kept_mask]])}).drop_duplicates()
    docs_comp["author"] = author_code[docs_comp["doc"].to_numpy()]
    docs_comp = docs_comp[docs_comp["author"] >= 0]
    comps = pd.unique(docs_comp["comp"])
    cnode = {c: k for k, c in enumerate(comps)}
    off = len(comps)
    ca = docs_comp["comp"].map(cnode).to_numpy()
    au = docs_comp["author"].to_numpy() + off
    root = union_find(ca, au)
    unit_of_comp = dict(zip(docs_comp["comp"].to_numpy(), root))
    units = np.array([unit_of_comp.get(c, -1 - int(c)) for c in comp_capped])
    counts = {"clusters_scored": int(pd.unique(comp_capped).size), "merged_units": int(pd.unique(units).size)}
    return units, counts


def main() -> None:
    """Run E43 and write results/E43_robustness.json."""
    cfg = json.loads(CONFIG.read_text())
    if (cfg["cap_per_component"], cfg["n_boot"], cfg["seed"]) != (CAP, N_BOOT, SEED):
        raise ValueError("constants differ from configs/E36_pipeline.json")
    public, truth = split_truth(pd.read_parquet(INTERIM_DIR / "moltbook_slim.parquet"))
    assert_public(public)
    pairs = pd.read_parquet(INTERIM_DIR / "E31_pairs.parquet")
    a, b, docs = doc_codes(pairs["doc_a"].to_numpy(), pairs["doc_b"].to_numpy())
    jac = pairs["jaccard"].to_numpy()
    del pairs
    text_of = dict(zip(public["doc_id"], public["text"]))
    texts = [text_of[d] for d in docs]
    ssize = np.array([len(shingles(t)) for t in tqdm(texts, desc="shingle sizes", unit="doc")])
    lens = np.array([len(t) for t in texts])
    tc = truth_codes(truth, docs)
    author_of = dict(zip(public["doc_id"], public["author_id"]))
    acode, _ = pd.factorize(pd.Series([author_of[d] for d in docs]), use_na_sentinel=True)
    res: dict[str, Any] = {"thresholds": {}}

    anchor = None
    for w in THRESHOLDS:
        sel = np.flatnonzero(jac >= w)
        aa, bb = a[sel], b[sel]
        cs = capped_scored(aa, bb, ssize, tc)
        cp = cs["capped"]
        preds = cue_predictions([texts[i] for i in aa[cp]], [texts[i] for i in bb[cp]])
        comp = cs["comp"][cp]
        methods = {k: component_accuracy((p == cs["a_earlier"]).astype(float), comp, n_boot=N_BOOT, seed=SEED)
                   for k, p in preds.items()}
        res["thresholds"][f"{w}-{J_HI}"] = {"counts": cs["counts"], "methods": methods, "go_rule": go_rule(methods)}
        if w == THRESHOLDS[0]:
            anchor = (aa, bb, cs, preds)

    aa, bb, cs, preds = anchor
    e32 = json.loads((REPO_ROOT / "results" / "E32_copy_direction_v2.json").read_text())["results"]["methods"]
    a05 = res["thresholds"][f"0.5-{J_HI}"]["methods"]
    res["anchor_check_vs_E32"] = {k: {"E43": a05[k]["macro"], "E32": e32[k]["macro"]} for k in e32}
    res["anchor_check_vs_E32"]["exact_1e-12"] = all(abs(v["E43"] - v["E32"]) < 1e-12
                                                    for v in res["anchor_check_vs_E32"].values() if isinstance(v, dict))

    elig = np.flatnonzero(cs["kept_mask"])
    a_e, valid = order_from_codes(tc, aa[elig], bb[elig])
    elig, a_e = elig[valid], a_e[valid]
    ln_pred, _ = predict_length(lens[aa[elig]], lens[bb[elig]], seed=SEED)
    ct_pred, _ = predict_containment(np.ones(len(elig)), ssize[aa[elig]], ssize[bb[elig]], seed=SEED)
    comp_e = cs["comp"][elig]
    res["two_stage_bootstrap_0.5"] = {
        "note": "containment on all pairs uses inter = 1: C(i) > C(j) iff size_i < size_j for any inter > 0",
        "b_longer_is_later": two_stage((ln_pred == a_e).astype(float), comp_e, N_BOOT, SEED),
        "c_containment": two_stage((ct_pred == a_e).astype(float), comp_e, N_BOOT, SEED),
        "cluster_bootstrap_E32_design": {k: [a05[k]["ci_low"], a05[k]["ci_high"]] for k in ("b_longer_is_later", "c_containment")},
    }
    for k in ("b_longer_is_later", "c_containment"):
        ts = res["two_stage_bootstrap_0.5"][k]
        e = res["two_stage_bootstrap_0.5"]["cluster_bootstrap_E32_design"][k]
        ts["ci_width_ratio_two_stage_over_cluster"] = (ts["ci"][1] - ts["ci"][0]) / (e[1] - e[0])
        ts["ci_includes_0.5"] = bool(ts["ci"][0] <= 0.5 <= ts["ci"][1])

    units, ucounts = author_merged(cs["comp"][cs["capped"]], cs["comp"], aa, bb, cs["kept_mask"], acode)
    merged = {k: macro_bootstrap((p == cs["a_earlier"]).astype(float), units, n_boot=N_BOOT, seed=SEED)
              for k, p in preds.items()}
    res["author_merged_0.5"] = {"counts": ucounts, "methods": merged, "go_rule": go_rule(merged)}

    res["robust_overall"] = bool(all(v["go_rule"]["robust"] for v in res["thresholds"].values())
                                 and res["author_merged_0.5"]["go_rule"]["robust"]
                                 and all(res["two_stage_bootstrap_0.5"][k]["ci_includes_0.5"]
                                         for k in ("b_longer_is_later", "c_containment")))
    save_result("E43_robustness", res, {"pairs": "data/interim/E31_pairs.parquet", "thresholds": list(THRESHOLDS),
                                        "j_hi": J_HI, "cap": CAP, "n_boot": N_BOOT, "go_margin": GO_MARGIN,
                                        "template_filter": "drop clusters where all pairs have equal shingle-set size",
                                        "author_merge": "union-find over (cluster, author) for all docs of kept clusters"})
    summ = {f"len_{w}": res["thresholds"][f"{w}-{J_HI}"]["methods"]["b_longer_is_later"]["macro"] for w in THRESHOLDS}
    summ.update({"anchor_exact": res["anchor_check_vs_E32"]["exact_1e-12"], "robust_overall": res["robust_overall"]})
    append_summary("E43", summ)
    for w, v in res["thresholds"].items():
        print(w, v["counts"]["components_scored"], v["counts"]["pairs_scored"],
              round(v["counts"]["largest_cluster_share_of_pairs"], 3),
              {k: (round(m["macro"], 4), round(m["ci_low"], 4), round(m["ci_high"], 4)) for k, m in v["methods"].items()},
              v["go_rule"]["robust"])
    print(json.dumps(res["anchor_check_vs_E32"]))
    print(json.dumps({k: v for k, v in res["two_stage_bootstrap_0.5"].items() if k != "note"}))
    print(ucounts, {k: (round(m["macro"], 4), round(m["ci_low"], 4), round(m["ci_high"], 4)) for k, m in merged.items()})
    print("robust_overall", res["robust_overall"])


if __name__ == "__main__":
    main()
