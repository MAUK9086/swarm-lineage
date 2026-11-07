"""E38 - Metadata monitor, activity-matched, grouped cross-validation, feature-set ablation.

File structure:
    Constants     feature sets, thresholds
    cv_scores     out-of-fold scores and per-fold metrics for one feature set
    main          labels, sample, hold-out, cross-validation, held-out test, jitter, save
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.evaluate import detection_metrics, recall_at_fpr, recall_fixed_threshold  # noqa: E402
from src.io_utils import INTERIM_DIR, SEED, append_summary, save_result  # noqa: E402
from src.monitor import account_features, created_at_clustering  # noqa: E402
from src.monitor_data import build_features, build_labels, load_agents  # noqa: E402

MIN_POSTS = 20
MAX_PER_CLASS = 5_000
HOLDOUT_SHARE = 0.01
N_FOLDS = 5
N_BOOT = 1000
JITTER_MIN = (0, 1, 5, 30, 120)
SYNC = ["sync_share_any", "sync_mean_log1p", "sync_ratio_to_expected"]
INTERVALS = ["iv_median_log", "iv_mean_log", "iv_share_lt_60s", "iv_min_log", "iv_cv", "burstiness"]
CREATION = ["created_missing", "created_within_60s_log1p", "created_within_1h_log1p"]
ACCOUNT = ["karma_slog1p", "followers_log1p", "following_log1p"]
TIMELINE = SYNC + INTERVALS + ["hour_entropy"]
FEATURE_SETS = {
    "a_full": SYNC + ["n_posts_log1p"] + INTERVALS + ["hour_entropy"] + CREATION + ACCOUNT,
    "b_synchrony": SYNC,
    "c_activity": ["n_posts_log1p"] + INTERVALS,
    "d_creation": CREATION,
    "e_karma": ["karma_slog1p"],
}
GO_MIN_AUROC = 0.75
GO_MIN_RECALL = 0.30


def _gbt() -> HistGradientBoostingClassifier:
    """Primary model.

    Returns:
        Unfitted classifier.
    """
    return HistGradientBoostingClassifier(random_state=SEED)


def _lr():
    """Secondary model.

    Returns:
        Unfitted pipeline.
    """
    return make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(),
                         LogisticRegression(max_iter=2000))


def cv_scores(X: pd.DataFrame, folds: list[tuple[np.ndarray, np.ndarray]], feats: list[str], make) -> dict[str, Any]:
    """Out-of-fold scores, per-fold metrics and fitted fold models.

    Args:
        X: Cross-validation frame with y and the feature columns.
        folds: (train_idx, test_idx) per fold.
        feats: Feature columns.
        make: Model factory.

    Returns:
        Dict with oof scores, fold id per row, models and per-fold metrics.
    """
    y = X["y"].to_numpy()
    oof = np.full(len(X), np.nan)
    fold_of = np.full(len(X), -1)
    models, per_fold = [], []
    for k, (tr, te) in enumerate(folds):
        m = make().fit(X.iloc[tr][feats], y[tr])
        s = m.predict_proba(X.iloc[te][feats])[:, 1]
        oof[te], fold_of[te] = s, k
        models.append(m)
        per_fold.append({"auroc": float(roc_auc_score(y[te], s)), "recall_at_1pct_fpr": recall_at_fpr(y[te], s)[0],
                         "test_authors": int(len(te)), "test_coordinated": int(y[te].sum())})
    au = np.array([f["auroc"] for f in per_fold])
    rc = np.array([f["recall_at_1pct_fpr"] for f in per_fold])
    return {"oof": oof, "fold_of": fold_of, "models": models, "per_fold": per_fold,
            "auroc_mean_sd": [float(au.mean()), float(au.std(ddof=1))],
            "recall_mean_sd": [float(rc.mean()), float(rc.std(ddof=1))]}


def main() -> None:
    """Run E38 and write results/E38_monitor_matched.json."""
    L = build_labels()
    codes, t, uniques, coord, n_posts, comp = (L[k] for k in ("codes", "t", "uniques", "coord", "n_posts", "comp"))
    pos_pool = np.flatnonzero(coord & (n_posts >= MIN_POSTS))
    neg_pool = np.flatnonzero(~coord & (n_posts >= MIN_POSTS))
    rng = np.random.default_rng(SEED)
    pos = np.sort(rng.choice(pos_pool, min(MAX_PER_CLASS, len(pos_pool)), replace=False))
    neg = np.sort(rng.choice(neg_pool, min(MAX_PER_CLASS, len(neg_pool)), replace=False))
    sample = np.concatenate([pos, neg])
    counts: dict[str, Any] = {"posts": int(len(t)), "authors": int(len(uniques)), "marked_posts": L["marked_posts"],
                              "coordinated_ge_20": int(len(pos_pool)), "organic_ge_20": int(len(neg_pool)),
                              "sampled_coordinated": int(len(pos)), "sampled_organic": int(len(neg))}

    agents = load_agents()
    static = created_at_clustering(agents["created_s"]).join(account_features(agents))
    X = build_features(t, codes, sample, uniques, static)
    X["n_posts_log1p"] = np.log1p(X["n_posts"])
    X["y"] = coord[X.index.to_numpy()].astype(int)
    X["group"] = comp[X.index.to_numpy()]

    gsize = X.groupby("group").size().reset_index(name="n").sort_values(["n", "group"], ascending=[False, True])
    n_hold = math.ceil(HOLDOUT_SHARE * len(gsize))
    hold_groups = set(gsize["group"].iloc[:n_hold])
    is_hold = X["group"].isin(hold_groups).to_numpy()
    cv, ho = X[~is_hold].copy(), X[is_hold].copy()
    counts.update({"components_with_sampled_authors": int(len(gsize)), "held_out_components": int(n_hold),
                   "held_out_component_sizes": {"min": int(gsize["n"].iloc[:n_hold].min()), "max": int(gsize["n"].iloc[0])},
                   "held_out_authors": int(len(ho)), "held_out_coordinated": int(ho["y"].sum()),
                   "cv_authors": int(len(cv)), "cv_coordinated": int(cv["y"].sum()), "cv_components": int(cv["group"].nunique())})
    X.assign(author_id=uniques[X.index.to_numpy()], held_out=is_hold).to_parquet(INTERIM_DIR / "E38_features.parquet")

    skf = StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
    folds = list(skf.split(cv, cv["y"], cv["group"]))
    y, g = cv["y"].to_numpy(), cv["group"].to_numpy()
    sets: dict[str, Any] = {}
    fitted: dict[str, Any] = {}
    for name, feats in tqdm(FEATURE_SETS.items(), desc="feature sets"):
        r = cv_scores(cv, folds, feats, _gbt)
        pooled = detection_metrics(y, r["oof"], g, n_boot=N_BOOT, seed=SEED)
        full = _gbt().fit(cv[feats], y)
        hs = full.predict_proba(ho[feats])[:, 1]
        hy = ho["y"].to_numpy()
        held: dict[str, Any] = {"recall_at_pooled_threshold": float((hs[hy == 1] > pooled["threshold"]).mean()) if (hy == 1).any() else None}
        if (hy == 0).sum() >= 20 and (hy == 1).any():
            held["auroc"], held["auroc_reference"] = float(roc_auc_score(hy, hs)), "held-out organic authors"
        elif (hy == 1).any():
            ref = r["oof"][y == 0]
            held["auroc"] = float(roc_auc_score(np.r_[np.ones((hy == 1).sum()), np.zeros(len(ref))], np.r_[hs[hy == 1], ref]))
            held["auroc_reference"] = "pooled out-of-fold organic scores"
        sets[name] = {"features": feats, "per_fold": r["per_fold"], "auroc_mean_sd": r["auroc_mean_sd"],
                      "recall_mean_sd": r["recall_mean_sd"], "pooled": pooled, "held_out": held}
        fitted[name] = r
    lr = cv_scores(cv, folds, FEATURE_SETS["a_full"], _lr)
    sets["a_full_logistic_secondary"] = {"auroc_mean_sd": lr["auroc_mean_sd"], "recall_mean_sd": lr["recall_mean_sd"],
                                         "pooled": detection_metrics(y, lr["oof"], g, n_boot=N_BOOT, seed=SEED)}

    coord_cv = cv.index[cv["y"] == 1].to_numpy()
    post_mask = np.isin(codes, coord_cv)
    row_of = {c: i for i, c in enumerate(cv.index.to_numpy())}
    jitter: dict[str, Any] = {"a_full": {}, "b_synchrony": {}}
    for j in tqdm(JITTER_MIN, desc="jitter"):
        tj = t.copy()
        if j > 0:
            tj[post_mask] += np.random.default_rng(SEED).uniform(-j * 60, j * 60, int(post_mask.sum()))
        Xj = build_features(tj, codes, coord_cv, uniques, static)
        cvj = cv.copy()
        cvj.loc[coord_cv, TIMELINE] = Xj.loc[coord_cv, TIMELINE].to_numpy()
        for name in jitter:
            r = fitted[name]
            sj = r["oof"].copy()
            for c in coord_cv:
                i = row_of[c]
                sj[i] = r["models"][r["fold_of"][i]].predict_proba(cvj.iloc[[i]][FEATURE_SETS[name]])[:, 1][0]
            jitter[name][str(j)] = recall_fixed_threshold(y, sj, g, sets[name]["pooled"]["threshold"], n_boot=N_BOOT, seed=SEED)

    a = sets["a_full"]["pooled"]
    go = {"pooled_auroc": a["auroc"], "auroc_ge_075": a["auroc"] >= GO_MIN_AUROC,
          "pooled_recall_at_1pct_fpr": a["recall_at_1pct_fpr"], "recall_ge_030": a["recall_at_1pct_fpr"] >= GO_MIN_RECALL}
    go["go"] = go["auroc_ge_075"] and go["recall_ge_030"]
    res = {"counts": counts, "feature_sets": sets, "jitter": jitter, "go_no_go": go}
    save_result("E38_monitor_matched", res, {"min_posts": MIN_POSTS, "max_per_class": MAX_PER_CLASS,
                                             "holdout_share": HOLDOUT_SHARE, "n_folds": N_FOLDS, "n_boot": N_BOOT,
                                             "jitter_minutes": list(JITTER_MIN), "feature_sets": FEATURE_SETS})
    append_summary("E38", {"auroc_a": a["auroc"], "recall_a": a["recall_at_1pct_fpr"],
                           "auroc_b": sets["b_synchrony"]["pooled"]["auroc"], "auroc_c": sets["c_activity"]["pooled"]["auroc"],
                           "go": go["go"]})
    print(counts)
    for k, v in sets.items():
        p = v["pooled"]
        print(k, v["auroc_mean_sd"], v["recall_mean_sd"], round(p["auroc"], 4), p["auroc_ci"], round(p["recall_at_1pct_fpr"], 4), v.get("held_out"))
    print({k: {j: round(x["recall"], 3) for j, x in d.items()} for k, d in jitter.items()})
    print(go)


if __name__ == "__main__":
    main()
