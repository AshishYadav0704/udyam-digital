"""Train and evaluate the lead-activation propensity model.

Usage: python -I ml/train_propensity.py [data_dir]
Outputs:
  ml/artifacts/propensity_model.joblib    model + metadata used by the API
  ml/artifacts/model_card.json            metrics, split, features, fairness, decision
  analysis/outputs/ml_report.md           human-readable evaluation
  analysis/outputs/charts/ml_*.png        PR, ROC, calibration, lift, importance

Design choices
  * Target: activated (1) vs not (0). Features: creation-time only (see app/ml/features.py).
  * Chronological hold-out: train on leads created Apr-May 2026, test on June 2026.
  * Model selection on expanding-window CV inside the training period, scored by PR-AUC
    (7.4% positives, so PR-AUC and top-K precision matter more than ROC-AUC).
  * If a complex model does not beat logistic regression by a meaningful margin, the simpler,
    explainable model is shipped.
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
warnings.filterwarnings("ignore")

import joblib  # noqa: E402
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.calibration import calibration_curve  # noqa: E402
from sklearn.compose import ColumnTransformer  # noqa: E402
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix, f1_score,  # noqa: E402
                             precision_recall_curve, precision_score, recall_score, roc_auc_score, roc_curve)
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import OneHotEncoder, StandardScaler  # noqa: E402

from app.domain.catalogue import Catalogue  # noqa: E402
from app.ml.features import (FEATURE_SETS, FEATURES, IDENTIFIER_COLUMNS, LEAKAGE_COLUMNS,  # noqa: E402
                             build_row, catalogue_lookups)

D = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "data" / "raw"
ART = ROOT / "ml" / "artifacts"
OUT = ROOT / "analysis" / "outputs"
CH = OUT / "charts"
ART.mkdir(parents=True, exist_ok=True)
SEED = 42

# ------------------------------------------------------------------------------------------ data
leads = pd.read_csv(D / "smb_leads.csv", dtype=str, keep_default_na=False)
gst = pd.read_csv(D / "mock_gstin_registry.csv", dtype=str, keep_default_na=False).set_index("gstin").status.to_dict()
cat = Catalogue.from_csv(D / "product_catalogue.csv")
floor, tier1, gstreq = catalogue_lookups(cat)
X = pd.DataFrame([build_row(r, floor, tier1, gstreq, gst.get(r["gstin"])) for r in leads.to_dict("records")])[FEATURES]
y = (leads.outcome == "Activated").astype(int).values
created = pd.to_datetime(leads.created_date)
assert not set(LEAKAGE_COLUMNS + IDENTIFIER_COLUMNS) & set(X.columns), "leakage/identifier column in features"

train_mask = created < "2026-06-01"
Xtr, Xte, ytr, yte = X[train_mask].reset_index(drop=True), X[~train_mask].reset_index(drop=True), y[train_mask], y[~train_mask]
order = np.argsort(created[train_mask].values, kind="stable")
Xtr, ytr = Xtr.iloc[order].reset_index(drop=True), ytr[order]
meta_te = leads[~train_mask].reset_index(drop=True)
print(f"train {len(Xtr)} ({ytr.mean():.2%} pos) | test {len(Xte)} ({yte.mean():.2%} pos)")


FS = {"cats": None, "nums": None}   # filled by the feature-set selection step below


def preproc(scale: bool, cats=None, nums=None):
    cats, nums = cats or FS["cats"], nums or FS["nums"]
    return ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=10, sparse_output=False), cats),
        ("num", StandardScaler() if scale else "passthrough", nums),
    ])


folds = np.array_split(np.arange(len(Xtr)), 5)


def cv_score(build):
    s = []
    for k in range(1, 5):
        tr_idx, va_idx = np.concatenate(folds[:k]), folds[k]
        m = build().fit(Xtr.iloc[tr_idx], ytr[tr_idx])
        p = m.predict_proba(Xtr.iloc[va_idx])[:, 1]
        s.append((average_precision_score(ytr[va_idx], p), roc_auc_score(ytr[va_idx], p)))
    s = np.array(s)
    return s[:, 0].mean(), s[:, 0].std(), s[:, 1].mean()


# ------------------------------------------------------------------------------------------ feature-set + C selection (CV only)
ablation = []
for fs_name, (cats, nums) in FEATURE_SETS.items():
    for C in (0.03, 0.1, 0.3, 1.0):
        mu, sd, roc = cv_score(lambda: Pipeline([("pre", preproc(True, cats, nums)), ("clf", LogisticRegression(
            C=C, class_weight="balanced", max_iter=3000, random_state=SEED))]))
        ablation.append({"feature_set": fs_name, "C": C, "cv_pr_auc": mu, "cv_pr_auc_std": sd, "cv_roc_auc": roc})
abl = pd.DataFrame(ablation)
best_fs = abl.groupby("feature_set").cv_pr_auc.max().idxmax()
sub = abl[abl.feature_set == best_fs]
top = sub.loc[sub.cv_pr_auc.idxmax()]
one_se = sub[sub.cv_pr_auc >= top.cv_pr_auc - top.cv_pr_auc_std].sort_values("C").iloc[0]   # most regularised within 1 SE
BEST_C = float(one_se.C)
FS["cats"], FS["nums"] = FEATURE_SETS[best_fs]
print(abl.round(4).to_string(index=False))
print(f"feature set: {best_fs} | C (1-SE rule): {BEST_C}")


class SegmentGstinBaseline:
    """Simple benchmark: historic activation rate of the lead's (segment x GSTIN) cell."""
    def fit(self, X, y):
        df = pd.DataFrame({"s": X["segment"].values, "g": X["has_gstin"].values, "y": y})
        self.table = df.groupby(["s", "g"]).y.mean().to_dict()
        self.prior = float(np.mean(y))
        return self

    def predict_proba(self, X):
        p = np.array([self.table.get((s, g), self.prior) for s, g in zip(X["segment"], X["has_gstin"])])
        return np.vstack([1 - p, p]).T


def make_models():
    m = {
        "Segment x GSTIN rate (baseline)": SegmentGstinBaseline(),
        "Logistic regression": Pipeline([("pre", preproc(True)), ("clf", LogisticRegression(
            C=BEST_C, class_weight="balanced", max_iter=3000, random_state=SEED))]),
        "Random forest": Pipeline([("pre", preproc(False)), ("clf", RandomForestClassifier(
            n_estimators=500, min_samples_leaf=20, max_features="sqrt", class_weight="balanced_subsample",
            n_jobs=-1, random_state=SEED))]),
        "Extra trees": Pipeline([("pre", preproc(False)), ("clf", ExtraTreesClassifier(
            n_estimators=500, min_samples_leaf=20, max_features="sqrt", class_weight="balanced_subsample",
            n_jobs=-1, random_state=SEED))]),
        "HistGradientBoosting": Pipeline([("pre", preproc(False)), ("clf", HistGradientBoostingClassifier(
            learning_rate=0.05, max_depth=3, max_iter=250, l2_regularization=1.0, min_samples_leaf=30,
            class_weight="balanced", random_state=SEED))]),
    }
    try:
        from catboost import CatBoostClassifier
        m["CatBoost"] = Pipeline([("pre", preproc(False)), ("clf", CatBoostClassifier(
            depth=4, iterations=400, learning_rate=0.05, l2_leaf_reg=5, auto_class_weights="Balanced",
            random_seed=SEED, verbose=False, thread_count=2))])
    except ImportError:
        pass
    try:
        from lightgbm import LGBMClassifier
        m["LightGBM"] = Pipeline([("pre", preproc(False)), ("clf", LGBMClassifier(
            n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=30, subsample=0.8,
            subsample_freq=1, colsample_bytree=0.8, class_weight="balanced", random_state=SEED, verbose=-1))])
    except ImportError:
        pass
    try:
        from xgboost import XGBClassifier
        m["XGBoost"] = Pipeline([("pre", preproc(False)), ("clf", XGBClassifier(
            n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
            scale_pos_weight=float((ytr == 0).sum() / (ytr == 1).sum()), random_state=SEED, n_jobs=2,
            eval_metric="logloss"))])
    except ImportError:
        pass
    return m


def top_k(y_true, score, frac):
    k = max(1, int(round(len(score) * frac)))
    idx = np.argsort(-score, kind="stable")[:k]
    prec = y_true[idx].mean()
    rec = y_true[idx].sum() / max(1, y_true.sum())
    return prec, rec, prec / y_true.mean()


# ------------------------------------------------------------------------------------------ CV on training period
cv = {}
for name, model in make_models().items():
    scores, t0 = [], time.time()
    for k in range(1, 5):
        tr_idx = np.concatenate(folds[:k])
        va_idx = folds[k]
        model.fit(Xtr.iloc[tr_idx], ytr[tr_idx])
        p = model.predict_proba(Xtr.iloc[va_idx])[:, 1]
        scores.append((average_precision_score(ytr[va_idx], p), roc_auc_score(ytr[va_idx], p)))
    s = np.array(scores)
    cv[name] = {"cv_pr_auc_mean": s[:, 0].mean(), "cv_pr_auc_std": s[:, 0].std(), "cv_roc_auc_mean": s[:, 1].mean(),
                "fit_seconds": time.time() - t0}
    print(f"{name:34s} CV PR-AUC {s[:,0].mean():.3f} ± {s[:,0].std():.3f} | ROC-AUC {s[:,1].mean():.3f}")

# ------------------------------------------------------------------------------------------ hold-out evaluation
results, probs, fitted = {}, {}, {}
for name, model in make_models().items():
    model.fit(Xtr, ytr)
    p = model.predict_proba(Xte)[:, 1]
    fitted[name], probs[name] = model, p
    p10, r10, l10 = top_k(yte, p, 0.10)
    p20, r20, l20 = top_k(yte, p, 0.20)
    results[name] = {**cv[name], "test_pr_auc": average_precision_score(yte, p), "test_roc_auc": roc_auc_score(yte, p),
                     "brier": brier_score_loss(yte, p), "precision_at_10pct": p10, "recall_at_10pct": r10, "lift_at_10pct": l10,
                     "precision_at_20pct": p20, "recall_at_20pct": r20, "lift_at_20pct": l20}

lb = pd.DataFrame(results).T.sort_values("cv_pr_auc_mean", ascending=False)
print(lb[["cv_pr_auc_mean", "test_pr_auc", "test_roc_auc", "lift_at_10pct", "lift_at_20pct", "brier"]].round(3).to_string())

# ------------------------------------------------------------------------------------------ selection rule
ml_models = [n for n in lb.index if "baseline" not in n]
best = max(ml_models, key=lambda n: results[n]["cv_pr_auc_mean"])
lr = "Logistic regression"
margin = results[best]["cv_pr_auc_mean"] - results[lr]["cv_pr_auc_mean"]
noise = max(results[best]["cv_pr_auc_std"], results[lr]["cv_pr_auc_std"])
chosen = best if (best != lr and margin > noise) else lr
base_name = "Segment x GSTIN rate (baseline)"
beats_baseline = results[chosen]["cv_pr_auc_mean"] - results[base_name]["cv_pr_auc_mean"]
decision = (f"Best CV PR-AUC: {best} ({results[best]['cv_pr_auc_mean']:.3f}). Margin over logistic regression "
            f"{margin:+.3f} vs fold noise {noise:.3f} -> shipped model: {chosen}. "
            f"Gain over the segment x GSTIN baseline: {beats_baseline:+.3f} PR-AUC (CV).")
print(decision)

# ------------------------------------------------------------------------------------------ calibration of the chosen model
# Platt-style recalibration fitted on out-of-fold predictions from the training period (no test data used)
oof_p, oof_y = [], []
for k in range(1, 5):
    tr_idx, va_idx = np.concatenate(folds[:k]), folds[k]
    m = make_models()[chosen].fit(Xtr.iloc[tr_idx], ytr[tr_idx])
    oof_p.append(m.predict_proba(Xtr.iloc[va_idx])[:, 1])
    oof_y.append(ytr[va_idx])
oof_p, oof_y = np.concatenate(oof_p), np.concatenate(oof_y)
logit = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))  # noqa: E731
cal = LogisticRegression(C=1e6).fit(logit(oof_p).reshape(-1, 1), oof_y)
model = fitted[chosen]
raw_te = probs[chosen]
cal_te = cal.predict_proba(logit(raw_te).reshape(-1, 1))[:, 1]
results[chosen]["brier_calibrated"] = brier_score_loss(yte, cal_te)
frac_pos, mean_pred = calibration_curve(yte, cal_te, n_bins=8, strategy="quantile")

# operating points: 'priority' = top 20% of scores in the training period
train_scores = cal.predict_proba(logit(model.predict_proba(Xtr)[:, 1]).reshape(-1, 1))[:, 1]
priority_cut = float(np.quantile(train_scores, 0.80))
watch_cut = float(np.quantile(train_scores, 0.50))
pred = (cal_te >= priority_cut).astype(int)
cm = confusion_matrix(yte, pred).tolist()
op = {"threshold": priority_cut, "precision": precision_score(yte, pred, zero_division=0),
      "recall": recall_score(yte, pred), "f1": f1_score(yte, pred), "flagged_share": pred.mean(), "confusion_matrix": cm}

# ------------------------------------------------------------------------------------------ fairness / subgroup checks
def group_table(col_values):
    rows = {}
    for g in sorted(set(col_values)):
        mk = np.array(col_values) == g
        yy, pp = yte[mk], cal_te[mk]
        sel = pp >= priority_cut
        rows[g] = {"n": int(mk.sum()), "observed_rate": float(yy.mean()), "mean_predicted": float(pp.mean()),
                   "roc_auc": float(roc_auc_score(yy, pp)) if 0 < yy.sum() < len(yy) else None,
                   "flagged_share": float(sel.mean()),
                   "precision_if_flagged": float(yy[sel].mean()) if sel.any() else None,
                   "recall": float(yy[sel].sum() / yy.sum()) if yy.sum() else None}
    return rows

fair = {"segment": group_table(meta_te.segment.tolist()), "has_gstin": group_table(meta_te.has_gstin.tolist()),
        "city_tier": group_table(meta_te.city_tier.tolist())}

# ------------------------------------------------------------------------------------------ explainability
perm = permutation_importance(model, Xte, yte, scoring="average_precision", n_repeats=10, random_state=SEED, n_jobs=1)
imp = pd.Series(perm.importances_mean, index=Xte.columns).sort_values(ascending=False)
lr_model = fitted[lr]
lr_names = lr_model.named_steps["pre"].get_feature_names_out()
lr_coef = pd.Series(lr_model.named_steps["clf"].coef_[0], index=lr_names).sort_values()

# ------------------------------------------------------------------------------------------ persist
artifact = {"model": model, "calibrator": cal, "model_name": chosen, "features": FEATURES,
            "priority_threshold": priority_cut, "watch_threshold": watch_cut,
            "train_window": ["2026-04-01", "2026-05-31"], "test_window": ["2026-06-01", "2026-06-30"],
            "base_rate_train": float(ytr.mean()),
            "lr_model": lr_model, "lr_feature_names": list(lr_names),
            "feature_set": best_fs, "model_categorical": FS["cats"], "model_numeric": FS["nums"]}
joblib.dump(artifact, ART / "propensity_model.joblib")

def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if np.isnan(o) else round(float(o), 4)
    if isinstance(o, np.integer):
        return int(o)
    return o

card = {"feature_set": best_fs, "C": BEST_C, "feature_set_ablation": ablation,
        "model_categorical": FS["cats"], "model_numeric": FS["nums"],
        "target": "activated (outcome == 'Activated')", "train_rows": int(len(Xtr)), "test_rows": int(len(Xte)),
        "train_positive_rate": float(ytr.mean()), "test_positive_rate": float(yte.mean()),
        "features": FEATURES, "excluded_leakage_columns": LEAKAGE_COLUMNS, "excluded_identifiers": IDENTIFIER_COLUMNS,
        "leaderboard": results, "chosen_model": chosen, "decision": decision, "operating_point_top20": op,
        "fairness": fair, "permutation_importance_top15": imp.head(15).to_dict(),
        "lr_top_positive": lr_coef.tail(10)[::-1].to_dict(), "lr_top_negative": lr_coef.head(10).to_dict(),
        "calibration_bins": {"mean_predicted": mean_pred.tolist(), "observed": frac_pos.tolist()}}
(ART / "model_card.json").write_text(json.dumps(clean(card), indent=2))

# ------------------------------------------------------------------------------------------ charts
INK, MUTED, HI, GREY = "#1f1f1f", "#6b6b6b", "#d0021b", "#9a9a9a"
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#cccccc"})
fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
for name in [chosen, base_name] + [n for n in ml_models if n not in (chosen,)][:2]:
    pr, rc, _ = precision_recall_curve(yte, probs[name])
    axes[0].plot(rc, pr, lw=2 if name == chosen else 1, color=HI if name == chosen else GREY if "baseline" in name else "#4a4a4a",
                 label=f"{name} (AP {results[name]['test_pr_auc']:.3f})")
    fpr, tpr, _ = roc_curve(yte, probs[name])
    axes[1].plot(fpr, tpr, lw=2 if name == chosen else 1, color=HI if name == chosen else GREY if "baseline" in name else "#4a4a4a",
                 label=f"{name} ({results[name]['test_roc_auc']:.3f})")
axes[0].axhline(yte.mean(), color=MUTED, lw=0.8); axes[0].set_title("Precision-recall (June hold-out)", loc="left")
axes[0].set_xlabel("recall"); axes[0].set_ylabel("precision"); axes[0].legend(fontsize=7, frameon=False)
axes[1].plot([0, 1], [0, 1], color="#dddddd", lw=0.8); axes[1].set_title("ROC (June hold-out)", loc="left")
axes[1].set_xlabel("false positive rate"); axes[1].legend(fontsize=7, frameon=False)
axes[2].plot([0, 0.3], [0, 0.3], color="#dddddd", lw=0.8)
axes[2].plot(mean_pred, frac_pos, marker="o", color=HI, lw=2)
axes[2].set_title(f"Calibration ({chosen}, recalibrated)", loc="left"); axes[2].set_xlabel("predicted"); axes[2].set_ylabel("observed")
fig.tight_layout(); fig.savefig(CH / "ml_curves.png", dpi=180); plt.close(fig)

fig, ax = plt.subplots(figsize=(6.5, 3.8))
top = imp.head(12)[::-1]
ax.barh(top.index, top.values, color=GREY)
ax.set_title(f"Permutation importance (drop in PR-AUC), {chosen}", loc="left", fontsize=9)
fig.tight_layout(); fig.savefig(CH / "ml_importance.png", dpi=180); plt.close(fig)

deciles = pd.qcut(pd.Series(cal_te).rank(method="first"), 10, labels=False)
lift = pd.DataFrame({"d": 9 - deciles, "y": yte}).groupby("d").y.mean() / yte.mean()
fig, ax = plt.subplots(figsize=(6, 3))
ax.bar([f"D{i+1}" for i in lift.index], lift.values, color=[HI if i < 2 else GREY for i in lift.index])
ax.axhline(1, color=MUTED, lw=0.8); ax.set_title("Lift by score decile (D1 = highest scores), June hold-out", loc="left", fontsize=9)
fig.tight_layout(); fig.savefig(CH / "ml_lift.png", dpi=180); plt.close(fig)

# ------------------------------------------------------------------------------------------ report
def fmt(x, pct=False):
    return "-" if x is None else (f"{x:.1%}" if pct else f"{x:.3f}")

rows = "\n".join(
    f"| {n}{' **(shipped)**' if n == chosen else ''} | {fmt(r['cv_pr_auc_mean'])} ± {fmt(r['cv_pr_auc_std'])} | {fmt(r['test_pr_auc'])} | "
    f"{fmt(r['test_roc_auc'])} | {fmt(r['precision_at_10pct'], True)} | {r['lift_at_10pct']:.2f}x | {fmt(r['precision_at_20pct'], True)} | "
    f"{fmt(r['recall_at_20pct'], True)} | {r['lift_at_20pct']:.2f}x | {fmt(r['brier'])} |"
    for n, r in sorted(results.items(), key=lambda kv: -kv[1]["cv_pr_auc_mean"]))
fair_rows = "\n".join(
    f"| {dim} | {g} | {v['n']} | {fmt(v['observed_rate'], True)} | {fmt(v['mean_predicted'], True)} | {fmt(v['roc_auc'])} | "
    f"{fmt(v['flagged_share'], True)} | {fmt(v['precision_if_flagged'], True)} | {fmt(v['recall'], True)} |"
    for dim, tbl in fair.items() for g, v in tbl.items())
md = f"""# Lead propensity model - evaluation report

**Question:** which newly created leads are most likely to activate, so a human (inside sales, partner or field
sales) can be assigned to them first? The score prioritises help; it never blocks or rejects a customer.

## Data and split
- 5,000 leads; target = activated (7.36% overall). Creation-time features only ({len(FEATURES)} columns, see
  `backend/app/ml/features.py`); excluded for leakage: {', '.join(LEAKAGE_COLUMNS)}.
- Chronological hold-out: train = leads created 1 Apr-31 May 2026 ({len(Xtr):,}, {ytr.mean():.2%} positive),
  test = 1-30 Jun 2026 ({len(Xte):,}, {yte.mean():.2%} positive). Model selection used 4 expanding-window folds inside
  the training period only.

## Feature-set selection (logistic regression, CV PR-AUC, training period only)
{abl.pivot(index="feature_set", columns="C", values="cv_pr_auc").round(4).to_markdown()}

Selected **{best_fs}** ({len(FS['cats'])} categorical + {len(FS['nums'])} numeric inputs); C = {BEST_C} by the one-standard-error rule.
Dropping the 25 product-interest flags and the high-cardinality business type / state / language one-hots removes noise
that the larger models were fitting.

## Leaderboard on the selected feature set (sorted by CV PR-AUC)
| Model | CV PR-AUC | Test PR-AUC | Test ROC-AUC | Precision@10% | Lift@10% | Precision@20% | Recall@20% | Lift@20% | Brier |
|---|---|---|---|---|---|---|---|---|---|
{rows}

Random ranking would score PR-AUC ≈ {yte.mean():.3f} and lift 1.0x.

**Decision:** {decision}

## Operating point (calibrated score ≥ top-20% training cut-off {priority_cut:.3f})
- Precision {op['precision']:.1%}, recall {op['recall']:.1%}, F1 {op['f1']:.3f}, {op['flagged_share']:.1%} of June leads flagged.
- Confusion matrix [[TN, FP], [FN, TP]]: {cm}
- Brier score {results[chosen]['brier']:.4f} raw -> {results[chosen].get('brier_calibrated', float('nan')):.4f} after Platt recalibration (fitted on
  out-of-fold training predictions).

## Subgroup checks (June hold-out)
| Dimension | Group | n | Observed rate | Mean predicted | ROC-AUC | Flagged | Precision if flagged | Recall |
|---|---|---|---|---|---|---|---|---|
{fair_rows}

GSTIN status and segment are legitimate drivers of activation in this data (9.6% vs 2.0% with/without GSTIN), so the
model ranks non-GST leads lower. Because the score is only used to order human follow-up, the routing layer adds a
rule that keeps a share of follow-up capacity for non-GST micro businesses (assisted KYC path) so they are not
systematically ignored.

## What drives the score
Permutation importance (drop in test PR-AUC when a feature is shuffled):
{chr(10).join(f'- {k}: {v:.4f}' for k, v in imp.head(10).items())}

Logistic-regression coefficients (standardised; positive = more likely to activate):
{chr(10).join(f'- {k}: {v:+.3f}' for k, v in lr_coef.tail(8)[::-1].items())}
{chr(10).join(f'- {k}: {v:+.3f}' for k, v in lr_coef.head(6).items())}

## Limitations
- One quarter of synthetic data; 245 training positives. Expect wide confidence intervals.
- No interaction history (opens, clicks, advisor engagement) - in production the digital journey itself will add
  much stronger signals (e.g. completed advisor, quote viewed) and the model should be retrained monthly.
- Calibration is checked on 1,704 June leads only; re-check after every retrain.
"""
(OUT / "ml_report.md").write_text(md)
print(f"\nShipped: {chosen}; priority cut {priority_cut:.3f}; test precision@20% {results[chosen]['precision_at_20pct']:.1%} "
      f"lift {results[chosen]['lift_at_20pct']:.2f}x")
