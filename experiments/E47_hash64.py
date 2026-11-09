"""E47 - Do the Moltbook conclusions change with 64-bit shingle hashes?

(a) Copy direction: exact Jaccard of every E31 pair is recomputed with 64-bit shingle
hashes; the corrected 0.5-0.95 pair set goes through the E32 component pipeline (functions
imported from experiments/E43_robustness.py). (b) Lineage: the E41-v2 pipeline with 64-bit
hashes in the exact verification stage; LSH candidate buckets keep the 32-bit MinHash
signatures. Method code never reads t.

File structure:
    load_e43       import the E43 helpers
    copy_direction part (a)
    lineage        part (b)
    main
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import copydir  # noqa: E402
from src.adapters import STANDARD_COLUMNS  # noqa: E402
from src.clusters import doc_codes, wald_ci  # noqa: E402
from src.copydir import assert_public, jaccard_csr, minhash_signatures, predict_length, shingle_hashes_csr, shingles  # noqa: E402
from src.evaluate import component_accuracy, lineage_tau_summary, order_from_codes, split_truth, truth_codes  # noqa: E402
from src.io_utils import INTERIM_DIR, REPO_ROOT, RESULTS_DIR, SEED, append_summary, save_result  # noqa: E402
from src.lineage import build_nodes, build_tree, length_rank, lineage_components_scoped, lsh_bucket_components  # noqa: E402

CONFIG = REPO_ROOT / "configs" / "E41_lineage_v2.json"
N_BOOT = 1000


def load_e43():
    """Import experiments/E43_robustness.py as a module (main not run).

    Returns:
        Module.
    """
    spec = importlib.util.spec_from_file_location("e43", REPO_ROOT / "experiments" / "E43_robustness.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def copy_direction(public: pd.DataFrame, truth: pd.Series) -> dict[str, Any]:
    """Part (a): 64-bit Jaccard on E31 pairs and the E32 pipeline on the corrected set.

    Args:
        public: Public Moltbook table.
        truth: t indexed by doc_id (to src/evaluate.py only).

    Returns:
        Results dict.
    """
    e43 = load_e43()
    pairs = pd.read_parquet(INTERIM_DIR / "E31_pairs.parquet")
    a, b, docs = doc_codes(pairs["doc_a"].to_numpy(), pairs["doc_b"].to_numpy())
    j32 = pairs["jaccard"].to_numpy()
    del pairs
    text_of = dict(zip(public["doc_id"], public["text"]))
    texts = [text_of[d] for d in docs]
    flat, off = shingle_hashes_csr(texts, len(texts), bits=64)
    j64 = jaccard_csr(flat, off, a, b)["jaccard"].to_numpy()
    keep = (j64 >= 0.5) & (j64 <= 0.95)
    out: dict[str, Any] = {"pairs_32bit": int(len(a)), "pairs_jaccard_changed": int((np.abs(j64 - j32) > 1e-12).sum()),
                           "max_abs_jaccard_change": float(np.abs(j64 - j32).max()),
                           "pairs_leaving_window": int((~keep).sum()), "pairs_64bit": int(keep.sum())}
    ssize = np.array([len(shingles(t)) for t in texts])
    lens = np.array([len(t) for t in texts])
    tc = truth_codes(truth, docs)
    aa, bb = a[keep], b[keep]
    cs = e43.capped_scored(aa, bb, ssize, tc)
    cp = cs["capped"]
    preds = e43.cue_predictions([texts[i] for i in aa[cp]], [texts[i] for i in bb[cp]])
    comp = cs["comp"][cp]
    methods = {k: component_accuracy((p == cs["a_earlier"]).astype(float), comp, n_boot=N_BOOT, seed=SEED)
               for k, p in preds.items()}
    pl, _ = predict_length(lens[aa], lens[bb], seed=SEED)
    ae, valid = order_from_codes(tc, aa, bb)
    pacc = float((pl[valid] == ae[valid]).mean())
    out.update({"counts_64bit": cs["counts"], "methods_64bit": methods, "go_rule_64bit": e43.go_rule(methods),
                "pair_level_length_64bit": {"accuracy": pacc, "ci": wald_ci(pacc, int(valid.sum()))}})
    e32 = json.loads((RESULTS_DIR / "E32_copy_direction_v2.json").read_text())["results"]
    comp_rows = {}
    for k in ("b_longer_is_later", "i_extension", "ii_insertion_vs_deletion", "a_random"):
        m32 = e32["methods"][k]
        half = (m32["ci_high"] - m32["ci_low"]) / 2
        comp_rows[k] = {"32bit": m32["macro"], "64bit": methods[k]["macro"], "abs_diff": abs(methods[k]["macro"] - m32["macro"]),
                        "half_ci_32": half, "within_half_half_width": bool(abs(methods[k]["macro"] - m32["macro"]) < half / 2)}
    out["comparison_vs_E32"] = comp_rows
    out["go_same_as_E32"] = bool(out["go_rule_64bit"]["robust"] and not e32["go_no_go"]["go"])
    return out


def lineage(cfg: dict[str, Any]) -> dict[str, Any]:
    """Part (b): E41-v2 lineage with 64-bit hashes in the verification stage.

    Args:
        cfg: Frozen E41-v2 config.

    Returns:
        Results per scope with the comparison to E41-v2.
    """
    table = pd.read_parquet(INTERIM_DIR / "moltbook_slim.parquet")
    if list(table.columns) != STANDARD_COLUMNS:
        raise ValueError("not a standard table")
    table = table.sample(frac=1.0, random_state=cfg["row_shuffle_seed"]).reset_index(drop=True)
    public, truth = split_truth(table)
    del table
    assert_public(public)
    nodes = build_nodes(public)
    group_of = dict(zip(public["doc_id"], public["group_id"]))
    node_groups = [frozenset(str(group_of[d]) for d in docs if pd.notna(group_of[d])) for docs in nodes["node_docs"]]
    n = len(nodes["rep_text"])
    flat32, off32 = shingle_hashes_csr(nodes["rep_text"], n)
    sig = minhash_signatures(flat32, off32, seed=cfg["seed"])
    cand = lsh_bucket_components(sig, np.diff(off32) > 0, threshold=cfg["lsh_threshold"])
    del sig, flat32
    flat64, off64 = shingle_hashes_csr(nodes["rep_text"], n, bits=64)
    by_scope, counts = lineage_components_scoped(cand, flat64, off64, cfg, node_groups)
    lengths = np.array([len(t) for t in nodes["rep_text"]])
    e41 = json.loads((RESULTS_DIR / "E41v2_lineage_moltbook.json").read_text())["results"]
    out: dict[str, Any] = {"counts_64bit": counts, "counts_32bit": e41["counts"], "scopes": {}}
    for sc in cfg["pair_scopes"]:
        comps = by_scope[sc]
        rt, rl = np.random.default_rng(cfg["seed"]), np.random.default_rng(cfg["seed"] + 1)
        dr, lr = [], []
        for c in comps:
            dr.append(build_tree(c, rt)["rank"])
            lr.append(length_rank(lengths[c["nodes"]], rl))
        ev = lineage_tau_summary(truth, nodes["node_docs"], [c["nodes"] for c in comps], {"depth": dr, "length": lr},
                                 n_boot=cfg["n_boot"], seed=cfg["seed"])
        d = ev["depth"]
        ev["go_64bit"] = bool((d["macro_ci"][0] > 0 or d["macro_ci"][1] < 0) and d["macro_tau"] > ev["length"]["macro_tau"])
        ref = e41["scopes"][sc]
        ev["go_32bit"] = ref["go_no_go"]["go"]
        ev["comparison"] = {}
        for m in ("depth", "length"):
            r = ref["evaluation"][m]
            half = (r["macro_ci"][1] - r["macro_ci"][0]) / 2
            ev["comparison"][m] = {"32bit": r["macro_tau"], "64bit": ev[m]["macro_tau"],
                                   "abs_diff": abs(ev[m]["macro_tau"] - r["macro_tau"]),
                                   "within_half_half_width": bool(abs(ev[m]["macro_tau"] - r["macro_tau"]) < half / 2)}
        out["scopes"][sc] = ev
    return out


def main() -> None:
    """Run E47 and write results/E47_hash64.json."""
    cfg = json.loads(CONFIG.read_bytes())
    if (cfg["shingle_k_words"], cfg["num_perm"], cfg["lsh_threshold"]) != (copydir.SHINGLE_K, copydir.NUM_PERM, copydir.LSH_THRESHOLD):
        raise ValueError("config does not match src/copydir.py constants")
    public, truth = split_truth(pd.read_parquet(INTERIM_DIR / "moltbook_slim.parquet"))
    assert_public(public)
    res: dict[str, Any] = {"copy_direction": copy_direction(public, truth)}
    del public, truth
    res["lineage"] = lineage(cfg)
    cd = res["copy_direction"]
    lin = res["lineage"]["scopes"]
    res["conclusions_unchanged"] = bool(
        cd["go_same_as_E32"] and all(v["within_half_half_width"] for v in cd["comparison_vs_E32"].values())
        and all(v["go_64bit"] == v["go_32bit"] for v in lin.values())
        and all(c["within_half_half_width"] for v in lin.values() for c in v["comparison"].values()))
    save_result("E47_hash64", res, {"hash": "blake2b digest_size=8 for exact Jaccard; LSH stage unchanged (32-bit)",
                                    "pairs": "E31_pairs.parquet", "config": cfg, "n_boot": N_BOOT})
    append_summary("E47", {"pairs_changed": cd["pairs_jaccard_changed"], "pairs_leaving": cd["pairs_leaving_window"],
                           "len_64": cd["methods_64bit"]["b_longer_is_later"]["macro"],
                           "unchanged": res["conclusions_unchanged"]})
    print(json.dumps({k: v for k, v in cd.items() if k not in ("methods_64bit",)}, indent=1, default=str)[:3000])
    for sc, v in lin.items():
        print(sc, json.dumps(v["comparison"]), v["go_32bit"], v["go_64bit"])
    print(json.dumps({k: res["lineage"]["counts_64bit"][k] for k in res["lineage"]["counts_64bit"] if "lineage_components" in k or "edges" in k}))
    print("conclusions_unchanged", res["conclusions_unchanged"])


if __name__ == "__main__":
    main()
