"""Expected-target model (Dev 2; Workstream B, Requirements 14 and 19).

A logistic model estimates, for each Route on a Model_Play, the probability it was
the target; probabilities are normalized within each (gameId, playId) so a play's
xtarget values sum to 1 (Req 14.3/14.4). TOE in aggregate.py is `is_target - xtarget`.

    from model import add_xtarget
    feats = add_xtarget(feats, cfg)   # adds 'xtarget' and 'xtarget_rel'

Features (Req 14.1, amended in design.md): openness_pre, depth, dist_from_qb,
rusher_distance x depth, rusher_distance x dist_from_qb. Missing feature values are
filled with the column median and counted (Req 14.9). Fitting uses the whole dataset;
GroupKFold(5) on gameId gives per-fold log loss, AUC and top-1 accuracy. Coefficients
and fold metrics are written to results/model_report.json (Req 14.6-14.8).

Accuracy-first with a baseline fallback (metrics_plan.md): the real logistic model
fills xtarget; if cfg.use_model is False or fitting raises, an equal-share baseline
(1/n per play) fills it instead, so the pipeline always yields a valid xtarget.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

PLAY_KEY = ["gameId", "playId"]

# Base feature columns; the two interactions are built from rusher_distance.
_BASE_FEATURES = ["openness_pre", "depth", "dist_from_qb"]
_INTERACTIONS = [("rusher_distance", "depth"), ("rusher_distance", "dist_from_qb")]


def _feature_matrix(feats, openness_col):
    """Build the design matrix (Req 14.1), filling missing values with the median.

    openness_col is 'openness_pre' for xtarget, 'openness_rel' for xtarget_rel.
    Returns (X DataFrame, n_filled) where n_filled counts imputed cells (Req 14.9).
    """
    cols = {
        "openness": feats[openness_col],
        "depth": feats["depth"],
        "dist_from_qb": feats["dist_from_qb"],
        "rusher_distance": feats["rusher_distance"],
    }
    raw = pd.DataFrame(cols)
    n_filled = int(raw.isna().sum().sum())
    raw = raw.fillna(raw.median())
    # Interactions are built after the median fill (design.md).
    X = pd.DataFrame({
        "openness": raw["openness"],
        "depth": raw["depth"],
        "dist_from_qb": raw["dist_from_qb"],
        "rusher_x_depth": raw["rusher_distance"] * raw["depth"],
        "rusher_x_dist_from_qb": raw["rusher_distance"] * raw["dist_from_qb"],
    })
    return X, n_filled


def _normalize_within_play(prob, groups):
    """xtarget = p / sum(p) within each play so each play sums to 1 (Req 14.3/14.4)."""
    s = pd.Series(prob, index=groups.index)
    totals = s.groupby([groups["gameId"], groups["playId"]]).transform("sum")
    totals = totals.replace(0.0, np.nan)
    out = (s / totals).to_numpy()
    # A play whose probabilities summed to 0 falls back to equal share.
    if np.isnan(out).any():
        out = np.where(np.isnan(out), _equal_share(groups), out)
    return out


def _equal_share(groups):
    """Baseline xtarget: 1 / n_eligible within each play (Req fallback, metrics_plan.md)."""
    n = groups.groupby(PLAY_KEY)["gameId"].transform("size")
    return (1.0 / n).to_numpy()


def _fold_metrics(X, y, groups):
    """Per-fold log loss, AUC and top-1 accuracy with GroupKFold(5) on gameId (Req 14.6)."""
    game_ids = groups["gameId"].to_numpy()
    n_splits = min(5, len(np.unique(game_ids)))
    folds = []
    if n_splits < 2:
        return folds   # too few games to cross-validate (fixtures)
    gkf = GroupKFold(n_splits=n_splits)
    for i, (train_idx, test_idx) in enumerate(gkf.split(X, y, groups=game_ids)):
        pipe = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
        pipe.fit(X.iloc[train_idx], y[train_idx])
        prob = pipe.predict_proba(X.iloc[test_idx])[:, 1]
        test_groups = groups.iloc[test_idx]
        xt = _normalize_within_play(prob, test_groups)
        fold = {
            "fold": i,
            "n_test": int(len(test_idx)),
            "log_loss": _safe_log_loss(y[test_idx], prob),
            "auc": _safe_auc(y[test_idx], prob),
            "top1_accuracy": _top1_accuracy(test_groups, xt, y[test_idx]),
        }
        folds.append(fold)
    return folds


def _safe_log_loss(y, prob):
    if len(np.unique(y)) < 2:
        return None
    return float(log_loss(y, prob, labels=[0, 1]))


def _safe_auc(y, prob):
    if len(np.unique(y)) < 2:
        return None
    return float(roc_auc_score(y, prob))


def _top1_accuracy(groups, xtarget, y):
    """Share of plays where argmax(xtarget) is the actual target (Req 14 report / design)."""
    df = groups[PLAY_KEY].copy()
    df["xtarget"] = xtarget
    df["is_target"] = y
    hits = 0
    total = 0
    for _, g in df.groupby(PLAY_KEY, sort=False):
        total += 1
        pred = g["xtarget"].to_numpy().argmax()
        if bool(g["is_target"].to_numpy()[pred]):
            hits += 1
    return float(hits / total) if total else None


def _fit_predict(feats, openness_col):
    """Fit on all routes, return (xtarget array, fitted pipeline, feature names, n_filled)."""
    X, n_filled = _feature_matrix(feats, openness_col)
    y = feats["is_target"].astype(int).to_numpy()
    pipe = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    pipe.fit(X, y)
    prob = pipe.predict_proba(X)[:, 1]
    xt = _normalize_within_play(prob, feats[PLAY_KEY])
    return xt, pipe, list(X.columns), n_filled


def _coefficients(pipe, feature_names):
    lr = pipe.named_steps["logisticregression"]
    coefs = dict(zip(feature_names, lr.coef_[0].astype(float)))
    coefs["intercept"] = float(lr.intercept_[0])
    return coefs


def add_xtarget(feats, cfg):
    """Add 'xtarget' (and 'xtarget_rel') to feats; write results/model_report.json.

    Uses the fitted logistic model unless cfg.use_model is False or fitting raises,
    in which case the equal-share baseline fills xtarget so the pipeline still runs
    (metrics_plan.md accuracy-first-with-fallback rule).
    """
    feats = feats.copy()
    use_model = getattr(cfg, "use_model", True)
    report = {"n_routes": int(len(feats)),
              "n_model_plays": int(feats[PLAY_KEY].drop_duplicates().shape[0])}

    if not use_model:
        feats["xtarget"] = _equal_share(feats[PLAY_KEY])
        feats["xtarget_rel"] = _equal_share(feats[PLAY_KEY])
        report["mode"] = "baseline (use_model=False)"
        _write_report(cfg, report)
        return feats

    try:
        xt, pipe, names, n_filled = _fit_predict(feats, "openness_pre")
        feats["xtarget"] = xt
        X, _ = _feature_matrix(feats, "openness_pre")
        y = feats["is_target"].astype(int).to_numpy()
        folds = _fold_metrics(X, y, feats[PLAY_KEY])
        coefs = _coefficients(pipe, names)

        report["mode"] = "logistic"
        report["features"] = names
        report["n_filled_features"] = int(n_filled)
        report["coefficients"] = coefs
        report["folds"] = folds
        report["cv_mean"] = _cv_mean(folds)

        if coefs.get("openness", 0.0) <= 0:
            print(f"WARNING: openness_pre coefficient is not positive "
                  f"({coefs.get('openness'):.4f}); expected positive (Req 14.8)")

        # Release-frame variant for xtarget_rel (Req 19.1).
        try:
            xt_rel, _, _, _ = _fit_predict(feats, "openness_rel")
            feats["xtarget_rel"] = xt_rel
            report["xtarget_rel"] = "fitted (openness_rel)"
        except Exception as err:   # robustness variant must not break the pipeline
            feats["xtarget_rel"] = pd.array([pd.NA] * len(feats), dtype="Float64")
            report["xtarget_rel"] = f"unavailable: {err}"

        _print_fold_metrics(folds, coefs)
    except Exception as err:
        print(f"WARNING: model fitting failed ({err}); using equal-share baseline xtarget")
        feats["xtarget"] = _equal_share(feats[PLAY_KEY])
        feats["xtarget_rel"] = pd.array([pd.NA] * len(feats), dtype="Float64")
        report["mode"] = f"baseline (fit failed: {err})"

    _write_report(cfg, report)
    return feats


def _cv_mean(folds):
    def _mean(key):
        vals = [f[key] for f in folds if f.get(key) is not None]
        return float(np.mean(vals)) if vals else None
    return {k: _mean(k) for k in ("log_loss", "auc", "top1_accuracy")}


def _print_fold_metrics(folds, coefs):
    print("=== expected-target model (Req 14) ===")
    print(f"coefficients: " + ", ".join(f"{k}={v:+.4f}" for k, v in coefs.items()))
    if not folds:
        print("fold metrics: not enough games for GroupKFold")
        return
    for f in folds:
        ll = "n/a" if f["log_loss"] is None else f"{f['log_loss']:.4f}"
        auc = "n/a" if f["auc"] is None else f"{f['auc']:.4f}"
        acc = "n/a" if f["top1_accuracy"] is None else f"{f['top1_accuracy']:.4f}"
        print(f"  fold {f['fold']}: log_loss={ll}  auc={auc}  top1_acc={acc}  n={f['n_test']}")
    cv = _cv_mean(folds)
    print(f"  mean: log_loss={cv['log_loss']:.4f}  auc={cv['auc']:.4f}  "
          f"top1_acc={cv['top1_accuracy']:.4f}")


def _write_report(cfg, report):
    cfg.outputs_dir.mkdir(parents=True, exist_ok=True)
    path = cfg.outputs_dir / "model_report.json"
    with open(path, "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"model: wrote {path}")
