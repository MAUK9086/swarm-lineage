"""T01 - Derived numbers and tables for the report, computed only from saved results.

Every number quoted in the report that is not printed directly in an E## results file is
computed here and saved to results/T01_report_numbers.json, with the source file named.
Also writes the two report tables as Markdown to results/T01_tables.md.

File structure:
    load          read the 'results' block of one results file
    corpora       Table 1 inputs
    copy_cues     cue-minus-length margins, scope shares, algebra checks
    evaluation    inflation, null false-positive rates, Wald SE vs null spread
    lineage       lineage tau summaries and leak check
    monitor       monitor waterfall
    ledger        pre-registered decisions (Table 2)
    main
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.io_utils import RESULTS_DIR, save_result  # noqa: E402


def load(name: str) -> dict[str, Any]:
    """Read the results block of results/<name>.json.

    Args:
        name: File stem.

    Returns:
        The 'results' dict, or {} if the file does not exist.
    """
    p = RESULTS_DIR / f"{name}.json"
    return json.loads(p.read_text())["results"] if p.exists() else {}


def corpora() -> dict[str, Any]:
    """Table 1 inputs."""
    e00, e01, e20, e30 = load("E00_profile"), load("E01_timestamps"), load("E20_profile"), load("E30_profile")
    m36, c36 = load("E36v2_replication_moltbook"), load("E36v2_replication_collusion_wiki")
    rev = e20["revisions"]
    return {
        "swarm_traces": {"rows": e00["n_rows"], "rows_with_time": e01["parsed"], "kinds": e00["fields"]["kind"]["value_counts"],
                         "source": "E00, E01"},
        "moltbook": {"posts": e30["posts"]["posts"], "agents": e30["posts"]["posts_per_agent"]["agents"],
                     "timestamped_share": e30["posts"]["created_at"]["parse_rate"],
                     "exact_duplicate_rate": e30["posts"]["exact_duplicates"]["exact_duplicate_rate"],
                     "sample": e30["sample"]["rows"], "pairs_scored_v2": m36["scopes"]["all"]["pairs_scored"],
                     "components_v2": m36["scopes"]["all"]["component_level"]["counts"]["components"],
                     "components_scored_v2": m36["scopes"]["all"]["component_level"]["counts"]["components_scored"],
                     "source": "E30, E36v2"},
        "collusion_wiki": {"revisions": rev["timestamp"]["non_null"], "pages": rev["revisions_per_page"]["pages"],
                           "timestamped_share": rev["timestamp"]["parse_rate"],
                           "pairs_scored_v2": c36["scopes"]["all"]["pairs_scored"],
                           "components_v2": c36["scopes"]["all"]["component_level"]["counts"]["components"],
                           "components_scored_v2": c36["scopes"]["all"]["component_level"]["counts"]["components_scored"],
                           "source": "E20, E36v2"},
    }


def copy_cues() -> dict[str, Any]:
    """Cue-minus-length margins per scope, scope shares, algebra checks."""
    out: dict[str, Any] = {"margins_vs_length_points": {}, "within_group_share_of_pairs": {}}
    for corp in ("moltbook", "collusion_wiki"):
        s = load(f"E36v2_replication_{corp}")["scopes"]
        out["within_group_share_of_pairs"][corp] = s["within_group"]["pairs_scored"] / s["all"]["pairs_scored"]
        for sc in ("all", "within_group", "cross_group"):
            m = s[sc]["component_level"]["methods"]
            b = m["b_longer_is_later"]["macro"]
            out["margins_vs_length_points"][f"{corp}.{sc}"] = {k: 100 * (v["macro"] - b) for k, v in m.items()
                                                               if k != "b_longer_is_later"}
    e32 = load("E32_copy_direction_v2")
    b = e32["methods"]["b_longer_is_later"]["macro"]
    out["margins_vs_length_points"]["moltbook.E32"] = {k: 100 * (v["macro"] - b) for k, v in e32["methods"].items()
                                                       if k != "b_longer_is_later"}
    e31 = load("E31_copy_direction_pilot")
    out["algebra"] = {
        "containment_ties_share_E31": e31["methods"]["c_containment"]["ties_broken_randomly"] / e31["counts"]["pairs_scored"],
        "insdel_vs_token_count_agreement_non_ties_E32": e32["diagnostics"]["agreement_ii_vs_token_count_rule_on_non_ties"],
        "token_count_ties_E32": e32["diagnostics"]["token_count_ties"],
        "pairs_scored_E32": e32["counts"]["pairs_scored"],
        "extension_ties_E32": e32["methods"]["i_extension"]["ties_broken_randomly"],
        "non_tied_pairs_E32": e32["counts"]["pairs_scored"] - e32["diagnostics"]["token_count_ties"],
        "source": "E31, E32",
    }
    return out


def evaluation() -> dict[str, Any]:
    """Inflation, null false-positive rates, Wald SE vs null spread."""
    e34, e35 = load("E34_inflation_curve"), load("E35_null_simulation")
    n = e35["pairs"]
    se = math.sqrt(0.25 / n)
    sd = e35["pair_level"]["accuracy_across_draws"]["sd"]
    infl = {w: {"pair_none": rows[-1]["pair_level"]["accuracy"], "macro_none": rows[-1]["component_level"]["macro"],
                "inflation_points": rows[-1]["inflation_points"], "ci_width_ratio": rows[-1]["ci_width_ratio_comp_over_pair"],
                "pairs": rows[-1]["pairs"], "components": rows[-1]["components"],
                "max_abs_gap_caps_le_100_points": max(abs(r["inflation_points"]) for r in rows[:-1])}
            for w, rows in e34["grid"].items()}
    m36 = load("E36v2_replication_moltbook")["scopes"]
    v2_gap = {sc: 100 * (m36[sc]["pair_level"]["b_longer_is_later"]["accuracy"]
                         - m36[sc]["component_level"]["methods"]["b_longer_is_later"]["macro"]) for sc in m36}
    return {"E34_inflation_by_window": infl, "E36v2_pair_minus_component_length_points": v2_gap,
            "E35": {"pairs": n, "wald_se_at_0.5": se, "null_sd_pair_level": sd, "null_sd_over_wald_se": sd / se,
                    "fpr_pair_level": e35["pair_level"]["false_positive_rate"], "fpr_pair_ci": e35["pair_level"]["fpr_wilson_ci"],
                    "fpr_component_level": e35["component_level"]["false_positive_rate"],
                    "fpr_component_ci": e35["component_level"]["fpr_wilson_ci"]},
            "source": "E34, E35, E36v2"}


def lineage() -> dict[str, Any]:
    """Lineage tau summaries, null FPR ranges and the row-order leak."""
    e41, e41b = load("E41_lineage_moltbook"), load("E41_lineage_moltbook_rowshuffled")
    out: dict[str, Any] = {"leak": {
        "E41_depth": e41["evaluation"]["depth"]["macro_tau"], "E41_length": e41["evaluation"]["length"]["macro_tau"],
        "E41b_depth": e41b["evaluation"]["depth"]["macro_tau"], "E41b_length": e41b["evaluation"]["length"]["macro_tau"],
        "depth_drop_share": 1 - e41b["evaluation"]["depth"]["macro_tau"] / e41["evaluation"]["depth"]["macro_tau"]}}
    fprs_naive, fprs_macro, rows = [], [], {}
    for corp in ("moltbook", "collusion_wiki"):
        r = load(f"E41v2_lineage_{corp}")
        for sc, e in r["scopes"].items():
            ev = e["evaluation"]
            rows[f"{corp}.{sc}"] = {m: {"macro_tau": ev[m]["macro_tau"], "ci": ev[m]["macro_ci"],
                                        "naive_tau": ev[m]["naive_pooled_tau"]} for m in ("depth", "length")}
            for m in ("depth", "length"):
                fprs_naive.append(ev[m]["null"]["naive_fpr"])
                fprs_macro.append(ev[m]["null"]["macro_fpr"])
        out[f"{corp}_root_is_shortest_share"] = (r["scopes"]["all"]["components_where_root_is_shortest_text"]
                                                 / r["scopes"]["all"]["lineage_components"])
        out[f"{corp}_within_share_of_edges"] = r["counts"]["within_group_verified_edges"] / r["counts"]["all_verified_edges"]
    out["E41v2_rows"] = rows
    out["null_fpr_naive_range"] = [min(fprs_naive), max(fprs_naive)]
    out["null_fpr_macro_range"] = [min(fprs_macro), max(fprs_macro)]
    out["source"] = "E41, E41b, E41v2"
    return out


def monitor() -> dict[str, Any]:
    """AUROC waterfall for the metadata monitor."""
    e37, e38 = load("E37_metadata_monitor_pilot"), load("E38_monitor_matched")
    a = e38["feature_sets"]["a_full"]
    return {"steps": [
        {"label": "naive (E37)", "auroc": e37["metrics"]["gbt"]["auroc"], "ci": e37["metrics"]["gbt"]["auroc_ci"]},
        {"label": "post count only (E37)", "auroc": e37["metrics"]["diagnostic_post_count_only"]["auroc"],
         "ci": e37["metrics"]["diagnostic_post_count_only"]["auroc_ci"]},
        {"label": "activity-matched (E37)", "auroc": e37["matched_diagnostic"]["gbt"]["auroc"],
         "ci": e37["matched_diagnostic"]["gbt"]["auroc_ci"]},
        {"label": "grouped CV, 13 positives (E38)", "auroc": a["pooled"]["auroc"], "ci": a["pooled"]["auroc_ci"]},
        {"label": "held-out components (E38)", "auroc": a["held_out"]["auroc"], "ci": None}],
        "recall_naive": e37["metrics"]["gbt"]["recall_at_1pct_fpr"],
        "recall_matched": e37["matched_diagnostic"]["gbt"]["recall_at_1pct_fpr"],
        "recall_E38_cv": a["pooled"]["recall_at_1pct_fpr"], "recall_E38_heldout": a["held_out"]["recall_at_pooled_threshold"],
        "E38_cv_coordinated": e38["counts"]["cv_coordinated"], "E38_heldout_coordinated": e38["counts"]["held_out_coordinated"],
        "E38_largest_component": e38["counts"]["held_out_component_sizes"]["max"],
        "synchrony_only_cv": e38["feature_sets"]["b_synchrony"]["pooled"]["auroc"],
        "synchrony_only_heldout": e38["feature_sets"]["b_synchrony"]["held_out"]["auroc"],
        "source": "E37, E38"}


def ledger() -> list[dict[str, Any]]:
    """Pre-registered decisions (Table 2)."""
    e31, e32, e34, e35 = load("E31_copy_direction_pilot"), load("E32_copy_direction_v2"), load("E34_inflation_curve"), load("E35_null_simulation")
    e37, e38, e41, e41b = load("E37_metadata_monitor_pilot"), load("E38_monitor_matched"), load("E41_lineage_moltbook"), load("E41_lineage_moltbook_rowshuffled")
    e42 = load("E42_pair_sample_sensitivity")
    rows = [
        {"exp": "E01-E02", "claim": "public Swarm Traces rows carry time", "outcome": "NO-GO", "key": "0 of 189,579 rows timestamped"},
        {"exp": "E31", "claim": "containment beats length by >= 5 pts (pairs)", "outcome": "NO-GO" if not e31["go_no_go"]["go"] else "GO",
         "key": f"{e31['methods']['c_containment']['accuracy']:.3f} vs {e31['methods']['b_longer_is_later']['accuracy']:.3f}"},
        {"exp": "E32", "claim": "edit cue beats length by >= 5 pts (clusters)", "outcome": "NO-GO" if not e32["go_no_go"]["go"] else "GO",
         "key": f"length {e32['methods']['b_longer_is_later']['macro']:.3f}; best cue {max(e32['methods']['i_extension']['macro'], e32['methods']['ii_insertion_vs_deletion']['macro']):.3f}"},
        {"exp": "E34", "claim": "pair-level inflates by >= 5 pts", "outcome": "confirmed" if e34["criterion"]["material_ge_5_points"] else "not confirmed",
         "key": f"{e34['criterion']['inflation_points_full_window_cap_none']:.1f} pts"},
        {"exp": "E35", "claim": "naive FPR > 10% while cluster FPR <= 10%", "outcome": "confirmed" if e35["criterion"]["naive_miscalibrated"] else "not confirmed",
         "key": f"{100*e35['pair_level']['false_positive_rate']:.1f}% vs {100*e35['component_level']['false_positive_rate']:.1f}%"},
        {"exp": "E37", "claim": "metadata monitor AUROC >= 0.75 (unmatched)", "outcome": "GO by rule, not adopted",
         "key": f"{e37['metrics']['gbt']['auroc']:.3f}; post count alone {e37['metrics']['diagnostic_post_count_only']['auroc']:.3f}"},
        {"exp": "E38", "claim": "matched monitor AUROC >= 0.75 and recall >= 0.30", "outcome": "NO-GO" if not e38["go_no_go"]["go"] else "GO",
         "key": f"{e38['go_no_go']['pooled_auroc']:.3f}, recall {e38['go_no_go']['pooled_recall_at_1pct_fpr']:.3f}"},
        {"exp": "E41", "claim": "tree depth orders time, beats length", "outcome": "GO, withdrawn (E41b)",
         "key": f"{e41['go_no_go']['depth_macro_tau']:.3f} -> {e41b['go_no_go']['depth_macro_tau']:.3f} after row shuffle"},
    ]
    if e42:
        a = e42["across_seeds"]["b_longer_is_later"]
        rows.append({"exp": "E42", "claim": "length above chance on every pair sample", "outcome": e42["reading"],
                     "key": f"length {a['min']:.3f}-{a['max']:.3f} over {len(e42['seeds'])} samples"})
    return rows


def main() -> None:
    """Compute and save all report numbers and tables."""
    res: dict[str, Any] = {"corpora": corpora(), "copy_cues": copy_cues(), "evaluation": evaluation(),
                           "lineage": lineage(), "monitor": monitor(), "ledger": ledger()}
    e42 = load("E42_pair_sample_sensitivity")
    if e42:
        res["E42_across_seeds"] = e42["across_seeds"]
        res["E42_reading"] = e42["reading"]
        v2 = load("E36v2_replication_moltbook")["scopes"]["all"]["component_level"]["methods"]["b_longer_is_later"]["macro"]
        five = e42["across_seeds"]["b_longer_is_later"]["macro_per_seed"] + [v2]
        res["moltbook_length_five_samples"] = {"values": five, "min": min(five), "max": max(five),
                                               "source": "E42 seeds 42-45 + E36v2 all"}
    save_result("T01_report_numbers", res, {"inputs": "results/*.json only"})
    c = res["corpora"]
    t02 = load("T02_cluster_concentration")
    t1 = ["| Corpus | Role | Texts | Timestamped | Near-duplicate pairs | Clusters | Median pairs per cluster |", "|---|---|---|---|---|---|---|",
          f"| Moltbook (sample of {c['moltbook']['posts']:,} posts) | development | {c['moltbook']['sample']:,} posts | {100*c['moltbook']['timestamped_share']:.0f}% | {t02['pairs']:,} | {t02['clusters']:,} | {t02['pairs_per_cluster']['median']:.0f} (largest: {t02['pairs_per_cluster']['max']:,}) |",
          f"| collusion.wiki export | held-out | {c['collusion_wiki']['revisions']:,} revisions of {c['collusion_wiki']['pages']:,} pages | {100*c['collusion_wiki']['timestamped_share']:.0f}% | {c['collusion_wiki']['pairs_scored_v2']:,} | {c['collusion_wiki']['components_v2']:,} | - |"]
    a = res["copy_cues"]["algebra"]
    e31 = load("E31_copy_direction_pilot")
    len_ties = e31["methods"]["b_longer_is_later"]["ties_broken_randomly"] / e31["counts"]["pairs_scored"]
    lin = res["lineage"]
    tc = ["| Cue | Predicts A came first when | Equivalent to | Evidence (Moltbook unless noted) |", "|---|---|---|---|",
          f"| Length | A is shorter (characters) | (reference rule) | ties on {100*len_ties:.1f}% of pairs |",
          f"| Shingle containment | A's shingles are more fully contained in B | A has fewer distinct shingles | ties on {100*a['containment_ties_share_E31']:.1f}% of pairs |",
          f"| Insertion vs deletion | the diff A to B inserts more words than it deletes | A has fewer words | same prediction on {100*a['insdel_vs_token_count_agreement_non_ties_E32']:.0f}% of {a['non_tied_pairs_E32']:,} untied pairs |",
          f"| Extension | more of A survives as B's prefix and suffix | A has fewer words; coin flip if nothing shared | {a['extension_ties_E32']:,} of {a['pairs_scored_E32']:,} pairs tied |",
          f"| Lineage root | A is the text most contained in the others | the shortest text is the root | root is shortest in {100*lin['moltbook_root_is_shortest_share']:.0f}% of clusters ({100*lin['collusion_wiki_root_is_shortest_share']:.0f}% on the wiki) |"]
    t2 = ["| Exp. | Pre-registered claim | Outcome | Key number |", "|---|---|---|---|"] + \
         [f"| {r['exp']} | {r['claim']} | {r['outcome']} | {r['key']} |" for r in res["ledger"]]
    (RESULTS_DIR / "T01_tables.md").write_text("Corpora\n\n" + "\n".join(x for x in t1 if x) + "\n\nCues\n\n" + "\n".join(tc)
                                               + "\n\nLedger\n\n" + "\n".join(t2) + "\n", encoding="utf-8")
    t1 = t1 + [""] + tc
    print(json.dumps({"E35_ratio": res["evaluation"]["E35"]["null_sd_over_wald_se"],
                      "within_share": res["copy_cues"]["within_group_share_of_pairs"],
                      "lineage_fpr_naive": res["lineage"]["null_fpr_naive_range"],
                      "lineage_fpr_macro": res["lineage"]["null_fpr_macro_range"]}, indent=1))
    print("\n".join(t1 + [""] + t2))


if __name__ == "__main__":
    main()
