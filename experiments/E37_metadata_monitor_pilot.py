"""E37 - Metadata-only monitor pilot for coordinated posting on Moltbook.

Labels come from content (src/labels.py) and the text is then discarded. Monitor
features (src/monitor.py) use only post times and agent metadata.

File structure:
    Constants        sample size, split, jitter levels, colours
    load_posts       author, time and text hash for every post (text dropped per file)
    load_agents      deduplicated agent metadata
    build_features   timeline + created_at + account features for a set of authors
    fit_models       gradient-boosted trees, logistic regression, karma-only, post-count-only
    plot_jitter      recall at 1% FPR against jitter
    main
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.model_selection import GroupShuffleSplit  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402
from tqdm import tqdm  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.adapters.moltbook import author_ids, post_text  # noqa: E402
from src.evaluate import detection_metrics, recall_fixed_threshold  # noqa: E402
from src.io_utils import FIGURES_DIR, INTERIM_DIR, REPO_ROOT, SEED, append_summary, save_result  # noqa: E402
from src.labels import duplicate_components, marked_posts, norm_hash  # noqa: E402
from src.monitor import account_features, created_at_clustering, timeline_features  # noqa: E402

RAW = REPO_ROOT / "data" / "raw" / "moltbook" / "data"
MAX_PER_CLASS = 10_000
ORGANIC_MIN_POSTS = 20
TEST_SIZE = 0.3
N_BOOT = 1000
JITTER_MIN = (0, 1, 5, 30, 120)
GO_MIN_AUROC = 0.75
FEATURES = ["sync_share_any", "sync_mean_log1p", "sync_ratio_to_expected", "iv_median_log", "iv_mean_log",
            "iv_share_lt_60s", "iv_min_log", "iv_cv", "burstiness", "hour_entropy", "created_missing",
            "created_within_60s_log1p", "created_within_1h_log1p", "karma_slog1p", "followers_log1p",
            "following_log1p"]
TIMELINE = ["sync_share_any", "sync_mean_log1p", "sync_ratio_to_expected", "iv_median_log", "iv_mean_log",
            "iv_share_lt_60s", "iv_min_log", "iv_cv", "burstiness", "hour_entropy"]
C_GBT, C_LR = "#2a78d6", "#eb6834"
C_SURFACE, C_TEXT, C_TEXT2, C_GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"


def load_posts() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Author, time (s) and normalised-text hash for every post; text is not kept.

    Returns:
        (author string array, time float64 seconds, hash int64)
    """
    authors, times, hashes = [], [], []
    for p in tqdm(sorted((RAW / "posts").glob("*.parquet")), desc="posts", unit="file"):
        raw = pq.read_table(p, columns=["id", "agent_id", "agent_name", "title", "content", "created_at"]).to_pandas()
        raw = raw.drop_duplicates("id")
        text = post_text(raw)
        hashes.append(np.fromiter((norm_hash(s) for s in text), dtype=np.int64, count=len(text)))
        del text
        authors.append(author_ids(raw).to_numpy(dtype=object))
        t = pd.to_datetime(raw["created_at"], utc=True).dt.tz_convert(None).to_numpy(dtype="datetime64[ns]")
        times.append(t.astype(np.int64) / 1e9)
    a, t, h = np.concatenate(authors), np.concatenate(times), np.concatenate(hashes)
    ok = pd.notna(a) & np.isfinite(t)
    return a[ok], t[ok], h[ok]


def load_agents() -> pd.DataFrame:
    """Latest snapshot of every agent: created_at (s), karma, follower / following counts.

    Returns:
        Frame indexed by agent id.
    """
    parts = []
    for k, p in enumerate(sorted((RAW / "agents").glob("*.parquet"))):
        df = pq.read_table(p, columns=["id", "karma", "follower_count", "following_count", "created_at",
                                       "dump_date"]).to_pandas()
        df["_f"] = k
        parts.append(df)
    d = pd.concat(parts).sort_values(["dump_date", "_f"]).drop_duplicates("id", keep="last").set_index("id")
    c = pd.to_datetime(d["created_at"], utc=True).dt.tz_convert(None)
    d["created_s"] = c.to_numpy(dtype="datetime64[ns]").astype(np.int64) / 1e9
    d.loc[c.isna().to_numpy(), "created_s"] = np.nan
    return d


def build_features(t: np.ndarray, codes: np.ndarray, sample: np.ndarray, uniques: np.ndarray,
                   agent_static: pd.DataFrame) -> pd.DataFrame:
    """Feature frame for the sampled authors.

    Args:
        t: Post times (s), whole timeline.
        codes: Author code per post.
        sample: Author codes to featurise.
        uniques: Author string per code.
        agent_static: created_at clustering + account features indexed by agent id.

    Returns:
        Frame indexed by author code with FEATURES and n_posts.
    """
    tl = timeline_features(t, codes, sample)
    ids = pd.Index(uniques[tl.index.to_numpy()])
    static = agent_static.reindex(ids)
    static.index = tl.index
    static["created_missing"] = static["created_missing"].fillna(1.0)
    return tl.join(static)


def fit_models(Xtr: pd.DataFrame, ytr: np.ndarray, feats: list[str]) -> dict[str, Any]:
    """Fit the gradient-boosted and logistic models on the given features.

    Args:
        Xtr: Training features.
        ytr: Training labels.
        feats: Feature columns.

    Returns:
        Dict of fitted models.
    """
    gbt = HistGradientBoostingClassifier(random_state=SEED).fit(Xtr[feats], ytr)
    lr = make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(),
                       LogisticRegression(max_iter=2000)).fit(Xtr[feats], ytr)
    return {"gbt": gbt, "lr": lr}


def _single_feature_lr(Xtr: pd.DataFrame, ytr: np.ndarray, col: str):
    """Logistic regression on one feature plus a missing flag.

    Args:
        Xtr: Training features.
        ytr: Training labels.
        col: Feature column.

    Returns:
        Fitted pipeline.
    """
    return make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(),
                         LogisticRegression(max_iter=2000)).fit(Xtr[[col]], ytr)


def plot_jitter(jit: dict[str, Any]) -> str:
    """Plot recall at 1% FPR against jitter for both models.

    Args:
        jit: Jitter results keyed by model then jitter level.

    Returns:
        Repo-relative figure path.
    """
    x = np.arange(len(JITTER_MIN))
    fig, ax = plt.subplots(figsize=(7.5, 4), facecolor=C_SURFACE)
    ax.set_facecolor(C_SURFACE)
    for name, label, col in (("gbt", "Gradient-boosted trees", C_GBT), ("lr", "Logistic regression", C_LR)):
        r = np.array([jit[name][str(j)]["recall"] for j in JITTER_MIN])
        lo = np.array([jit[name][str(j)]["ci"][0] for j in JITTER_MIN])
        hi = np.array([jit[name][str(j)]["ci"][1] for j in JITTER_MIN])
        ax.fill_between(x, lo, hi, color=col, alpha=0.15, linewidth=0)
        ax.plot(x, r, color=col, linewidth=2, marker="o", markersize=8, label=label,
                markeredgecolor=C_SURFACE, markeredgewidth=2)
        ax.annotate(f"{label}  {r[-1]:.2f}", (x[-1], r[-1]), xytext=(8, 0), textcoords="offset points",
                    va="center", fontsize=8, color=C_TEXT2)
    ax.set_xticks(x, [f"{j} min" for j in JITTER_MIN])
    ax.set_ylim(0, 1)
    ax.set_xlim(-0.3, len(x) - 1 + 1.6)
    ax.set_xlabel("uniform timestamp jitter applied to coordinated test authors (±)", color=C_TEXT2)
    ax.set_ylabel("recall at 1% FPR", color=C_TEXT2)
    ax.set_title("Monitor recall under timestamp jitter (95% group-bootstrap CI)", loc="left", fontsize=11, color=C_TEXT)
    ax.tick_params(colors=C_TEXT2, labelsize=8)
    ax.grid(axis="y", color=C_GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(C_GRID)
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    fig.tight_layout()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES_DIR / "E37_jitter_recall.png", dpi=150, facecolor=C_SURFACE)
    plt.close(fig)
    return "figures/E37_jitter_recall.png"


def main() -> None:
    """Run E37 and write results/E37_metadata_monitor_pilot.json."""
    a_str, t, h = load_posts()
    codes, uniques = pd.factorize(a_str)
    uniques = np.asarray(uniques, dtype=object)
    n_auth = len(uniques)
    counts: dict[str, Any] = {"posts": int(len(t)), "authors": int(n_auth)}

    mark = marked_posts(h, t, codes)
    coord = np.zeros(n_auth, dtype=bool)
    coord[np.unique(codes[mark])] = True
    n_posts = np.bincount(codes, minlength=n_auth)
    organic = (n_posts >= ORGANIC_MIN_POSTS) & ~coord
    comp = duplicate_components(h, codes, n_auth)
    del h  # content-derived values are not used past this point
    counts.update({"marked_posts": int(mark.sum()), "coordinated_authors": int(coord.sum()),
                   "organic_authors": int(organic.sum()),
                   "coordinated_authors_ge_20_posts": int((coord & (n_posts >= 20)).sum())})

    rng = np.random.default_rng(SEED)
    c_all, o_all = np.flatnonzero(coord), np.flatnonzero(organic)
    c_s = np.sort(rng.choice(c_all, min(MAX_PER_CLASS, len(c_all)), replace=False))
    o_s = np.sort(rng.choice(o_all, min(MAX_PER_CLASS, len(o_all)), replace=False))
    sample = np.concatenate([c_s, o_s])
    counts.update({"sampled_coordinated": int(len(c_s)), "sampled_organic": int(len(o_s))})

    agents = load_agents()
    static = created_at_clustering(agents["created_s"]).join(account_features(agents))
    X = build_features(t, codes, sample, uniques, static)
    X["y"] = coord[X.index.to_numpy()].astype(int)
    X["group"] = comp[X.index.to_numpy()]
    counts["sampled_authors_in_agents_table"] = int(pd.Index(uniques[sample]).isin(agents.index).sum())
    counts["feature_missing_rate"] = {f: float(X[f].isna().mean()) for f in FEATURES}
    X.assign(author_id=uniques[X.index.to_numpy()]).to_parquet(INTERIM_DIR / "E37_features.parquet")

    split = GroupShuffleSplit(n_splits=1, test_size=TEST_SIZE, random_state=SEED)
    tr_idx, te_idx = next(split.split(X, X["y"], X["group"]))
    tr, te = X.iloc[tr_idx], X.iloc[te_idx]
    counts["train"] = {"authors": int(len(tr)), "coordinated": int(tr["y"].sum()), "groups": int(tr["group"].nunique())}
    counts["test"] = {"authors": int(len(te)), "coordinated": int(te["y"].sum()), "groups": int(te["group"].nunique())}
    counts["groups_on_both_sides"] = int(len(set(tr["group"]) & set(te["group"])))
    ytr, yte, gte = tr["y"].to_numpy(), te["y"].to_numpy(), te["group"].to_numpy()

    models = fit_models(tr, ytr, FEATURES)
    karma = _single_feature_lr(tr, ytr, "karma_slog1p")
    tr_c = tr.assign(n_posts_log1p=np.log1p(tr["n_posts"]))
    te_c = te.assign(n_posts_log1p=np.log1p(te["n_posts"]))
    count_only = _single_feature_lr(tr_c, ytr, "n_posts_log1p")
    scores = {
        "gbt": models["gbt"].predict_proba(te[FEATURES])[:, 1],
        "lr": models["lr"].predict_proba(te[FEATURES])[:, 1],
        "random": np.random.default_rng(SEED).random(len(te)),
        "karma_only": karma.predict_proba(te[["karma_slog1p"]])[:, 1],
        "diagnostic_post_count_only": count_only.predict_proba(te_c[["n_posts_log1p"]])[:, 1],
    }
    metrics = {k: detection_metrics(yte, s, gte, n_boot=N_BOOT, seed=SEED) for k, s in tqdm(scores.items(), desc="metrics")}
    lr_coef = models["lr"].named_steps["logisticregression"].coef_[0]
    names = list(models["lr"].named_steps["simpleimputer"].get_feature_names_out(FEATURES))
    top = sorted(zip(names, lr_coef.tolist()), key=lambda z: -abs(z[1]))[:8]

    # Matched diagnostic: coordinated authors also need >= 20 posts.
    keep_tr = (tr["y"] == 0) | (tr["n_posts"] >= ORGANIC_MIN_POSTS)
    keep_te = (te["y"] == 0) | (te["n_posts"] >= ORGANIC_MIN_POSTS)
    matched: dict[str, Any] = {"train_coordinated": int(tr.loc[keep_tr, "y"].sum()),
                               "test_coordinated": int(te.loc[keep_te, "y"].sum())}
    if matched["train_coordinated"] >= 20 and matched["test_coordinated"] >= 20:
        mm = fit_models(tr[keep_tr], tr.loc[keep_tr, "y"].to_numpy(), FEATURES)
        tem = te[keep_te]
        for k in ("gbt", "lr"):
            matched[k] = detection_metrics(tem["y"].to_numpy(), mm[k].predict_proba(tem[FEATURES])[:, 1],
                                           tem["group"].to_numpy(), n_boot=N_BOOT, seed=SEED)

    # Evasion test: jitter the coordinated test authors' posts.
    te_coord = te.index[te["y"] == 1].to_numpy()
    post_mask = np.isin(codes, te_coord)
    jit: dict[str, Any] = {"gbt": {}, "lr": {}}
    pos_rows = te["y"].to_numpy() == 1
    for j in JITTER_MIN:
        tj = t.copy()
        if j > 0:
            tj[post_mask] += np.random.default_rng(SEED).uniform(-j * 60, j * 60, int(post_mask.sum()))
        Xj = build_features(tj, codes, te_coord, uniques, static)
        tej = te.copy()
        tej.loc[te_coord, TIMELINE] = Xj.loc[te_coord, TIMELINE].to_numpy()
        for k in ("gbt", "lr"):
            sj = models[k].predict_proba(tej[FEATURES])[:, 1]
            jit[k][str(j)] = recall_fixed_threshold(yte, sj, gte, metrics[k]["threshold"], n_boot=N_BOOT, seed=SEED)
    del pos_rows
    fig = plot_jitter(jit)

    g = metrics["gbt"]
    go = {"gbt_auroc": g["auroc"], "auroc_ge_075": g["auroc"] >= GO_MIN_AUROC,
          "gbt_ci_low": g["auroc_ci"][0], "karma_only_auroc": metrics["karma_only"]["auroc"],
          "ci_low_above_karma_point": g["auroc_ci"][0] > metrics["karma_only"]["auroc"]}
    go["go"] = go["auroc_ge_075"] and go["ci_low_above_karma_point"]
    res = {"counts": counts, "metrics": metrics, "lr_top_standardised_coefficients": top,
           "matched_diagnostic": matched, "jitter": jit, "figure": fig, "go_no_go": go}
    params = {"window_h": 24, "min_authors": 3, "organic_min_posts": ORGANIC_MIN_POSTS,
              "max_per_class": MAX_PER_CLASS, "test_size": TEST_SIZE, "n_boot": N_BOOT,
              "jitter_minutes": list(JITTER_MIN), "sync_window_s": 60, "features": FEATURES,
              "gbt": "HistGradientBoostingClassifier defaults", "lr": "median impute + indicators, scaled, max_iter 2000"}
    save_result("E37_metadata_monitor_pilot", res, params)
    append_summary("E37", {"auroc_gbt": g["auroc"], "auroc_lr": metrics["lr"]["auroc"],
                           "auroc_karma": metrics["karma_only"]["auroc"],
                           "auroc_post_count_diag": metrics["diagnostic_post_count_only"]["auroc"],
                           "recall1_gbt": g["recall_at_1pct_fpr"], "go": go["go"]})
    print(counts)
    for k, v in metrics.items():
        print(k, round(v["auroc"], 4), v["auroc_ci"], round(v["recall_at_1pct_fpr"], 4), v["recall_ci"])
    print("matched", {k: (v["auroc"] if isinstance(v, dict) else v) for k, v in matched.items()})
    print("jitter", {k: {j: round(v["recall"], 3) for j, v in d.items()} for k, d in jit.items()})
    print(go)


if __name__ == "__main__":
    main()
