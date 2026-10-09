"""Metrics-stage route features: separation, closing speed, lane penalty, the
composite Openness_Score, context (depth / sticks / QB distance) and rusher
distance (Dev 2; Workstream B, Requirements 11-13).

Consumes C1 Snapshot_Table and C2 Play_Table (see contracts_data.py). Produces
one row per eligible WR/TE/RB route on every Model_Play. The composite
Openness_Score defined in metrics/metrics_plan.md is authoritative:

    openness = separation
             - closing_horizon_s * closing_speed
             - lambda_lane * lane_penalty

NOTE for Dev 1 (config.py owner): Config has closing_horizon_s but not yet the
lane params. Please add `lambda_lane: float = 0.5` and `lane_cushion: float = 2.0`
to the Config dataclass. Until then this module reads them defensively via getattr.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from contracts_data import C1_FILE, C2_FILE, validate_c1, validate_c2

# Columns of C1 we actually need, kept as plain numpy for the per-group hot loop.
_C1_COLS = ["gameId", "playId", "offset", "nflId", "side", "pff_role",
            "is_eligible", "position_group", "x", "y", "s", "dir"]


def _velocity(s, dir_deg):
    """Velocity components (yd/s). dir is clockwise from +y, so dir==90 => +x.

    Confirmed convention: vx = s*sin(dir deg), vy = s*cos(dir deg).
    """
    rad = np.radians(dir_deg)
    return s * np.sin(rad), s * np.cos(rad)


def _frame_features(frame, lane_cushion):
    """Receiver-level features for one (gameId, playId, offset) frame.

    Vectorized over the eligible receivers against every defender in the frame
    (Nearest_Defender uses all defenders, not only Coverage; Req 11.4). Returns a
    dict of numpy arrays aligned to the eligible-receiver rows of `frame`, plus
    the receiver nflIds. If the frame has no defender, the defender-based features
    are NaN (Req 11.6).

    openness is NOT computed here; the caller combines separation/closing_speed/
    lane_penalty with the Config weights so the composite stays in one place.
    """
    is_elig = frame["is_eligible"].to_numpy()
    rec = frame[is_elig]
    n_rec = len(rec)
    rec_ids = rec["nflId"].to_numpy()

    nan = np.full(n_rec, np.nan)
    out = {
        "nflId": rec_ids,
        "separation": nan.copy(),
        "closing_speed": nan.copy(),
        "lane_penalty": nan.copy(),
        "depth": nan.copy(),
        "depth_vs_sticks": nan.copy(),
        "dist_from_qb": nan.copy(),
    }
    if n_rec == 0:
        out["n_no_defender"] = 0
        return out

    rx = rec["x"].to_numpy(dtype=float)
    ry = rec["y"].to_numpy(dtype=float)
    rvx, rvy = _velocity(rec["s"].to_numpy(dtype=float), rec["dir"].to_numpy(dtype=float))

    # --- QB-relative context (Req 13.1-13.3). qb row flagged by the caller. ---
    qb = frame[frame["is_qb"].to_numpy()]
    if len(qb):
        qx = float(qb["x"].iloc[0])
        qy = float(qb["y"].iloc[0])
        out["dist_from_qb"] = np.hypot(rx - qx, ry - qy)
        # Unit vector receiver -> QB for the lane projection.
        ux = qx - rx
        uy = qy - ry
        unorm = np.hypot(ux, uy)
    else:
        qx = qy = np.nan
        ux = uy = unorm = None

    los_x = frame["los_x"].iloc[0]
    line_to_gain_x = frame["line_to_gain_x"].iloc[0]
    out["depth"] = rx - los_x
    out["depth_vs_sticks"] = rx - line_to_gain_x

    # --- Nearest-defender features (Req 11). ---
    dfd = frame[frame["side"].to_numpy() == "defense"]
    if len(dfd) == 0:
        out["n_no_defender"] = n_rec
        return out
    out["n_no_defender"] = 0

    dx = dfd["x"].to_numpy(dtype=float)
    dy = dfd["y"].to_numpy(dtype=float)
    dvx, dvy = _velocity(dfd["s"].to_numpy(dtype=float), dfd["dir"].to_numpy(dtype=float))

    # Pairwise receiver (rows) x defender (cols) displacement p_d - p_r.
    rel_x = dx[None, :] - rx[:, None]
    rel_y = dy[None, :] - ry[:, None]
    dist = np.hypot(rel_x, rel_y)                      # (n_rec, n_def)

    j = np.argmin(dist, axis=1)                        # nearest defender index per rec
    idx = np.arange(n_rec)
    separation = dist[idx, j]
    out["separation"] = separation                     # == min dist to any defender (Req 11.4)

    # Closing speed for the nearest defender (Req 11.2):
    #   closing = -((p_d - p_r) . (v_d - v_r)) / ||p_d - p_r||,  positive = closing.
    nrx = rel_x[idx, j]
    nry = rel_y[idx, j]
    rvx_d = dvx[j] - rvx
    rvy_d = dvy[j] - rvy
    dot = nrx * rvx_d + nry * rvy_d
    with np.errstate(divide="ignore", invalid="ignore"):
        closing = -dot / separation
    closing[separation == 0] = 0.0                     # coincident: no closing rate
    out["closing_speed"] = closing

    # Lane_Penalty for the nearest defender (Req 12.9 input):
    #   perp_dist = |(p_d - p_r) x u_hat|, u_hat = unit receiver->QB.
    #   lane_penalty = max(0, lane_cushion - perp_dist). perp_dist=inf if rec==QB.
    if unorm is not None:
        perp = np.full(n_rec, np.inf)
        ok = unorm > 0
        if ok.any():
            uxh = ux[ok] / unorm[ok]
            uyh = uy[ok] / unorm[ok]
            # 2D cross-product magnitude of (p_d - p_r) with the unit lane vector.
            perp[ok] = np.abs(nrx[ok] * uyh - nry[ok] * uxh)
        out["lane_penalty"] = np.maximum(0.0, lane_cushion - perp)
    # If there is no QB row, lane_penalty stays NaN (cannot define the lane).

    return out


def build_route_features(c1: pd.DataFrame, c2: pd.DataFrame, cfg) -> pd.DataFrame:
    """One row per eligible receiver per Model_Play (Req 11-13, 15.2-15.3).

    Columns: gameId, playId, nflId; the pre-release triple+composite
    (separation_pre, closing_speed_pre, lane_penalty_pre, openness_pre) at
    cfg.pre_release_offset; the release triple+composite (…_rel) at offset 0;
    depth, depth_vs_sticks, dist_from_qb at pre-release; rusher_distance (per
    play, offset 0); is_target; is_most_open (one per play, highest openness_pre,
    ties to lowest nflId); open_flag (most_open mode => is_most_open, else
    separation_pre >= cfg.open_threshold).

    Prints the no-defender and no-rusher route/play counts (Req 11.6, 13.5).
    """
    pre = int(cfg.pre_release_offset)
    closing_horizon_s = getattr(cfg, "closing_horizon_s", 0.5)
    lambda_lane = getattr(cfg, "lambda_lane", 0.5)       # Dev 1: add to Config
    lane_cushion = getattr(cfg, "lane_cushion", 2.0)     # Dev 1: add to Config

    # Model plays only (Req 15.1). Pull their per-play context in one go.
    plays = c2[c2["is_model_play"].astype(bool)][
        ["gameId", "playId", "los_x", "line_to_gain_x", "qb_nflId", "target_nflId"]
    ].copy()
    key = ["gameId", "playId"]

    # Restrict C1 to those plays and the two offsets we score, then attach the
    # per-play context (los/sticks/qb/target) once by merge.
    c1 = c1[_C1_COLS]
    c1 = c1[c1["offset"].isin((0, pre))]
    c1 = c1.merge(plays, on=key, how="inner")
    # nullable Int64 compares produce pd.NA (ball rows); coerce to a plain bool.
    is_qb = (c1["nflId"] == c1["qb_nflId"]) & c1["qb_nflId"].notna()
    c1["is_qb"] = is_qb.fillna(False).to_numpy(dtype=bool)

    def _features_at(offset, suffix):
        sub = c1[c1["offset"] == offset]
        rows = []
        no_def = 0
        for _, frame in sub.groupby(key, sort=False):
            res = _frame_features(frame, lane_cushion)
            no_def += res.pop("n_no_defender")
            g = frame["gameId"].iloc[0]
            p = frame["playId"].iloc[0]
            n = len(res["nflId"])
            df = pd.DataFrame({
                "gameId": np.full(n, g),
                "playId": np.full(n, p),
                "nflId": res["nflId"],
                f"separation{suffix}": res["separation"],
                f"closing_speed{suffix}": res["closing_speed"],
                f"lane_penalty{suffix}": res["lane_penalty"],
                "depth": res["depth"],
                "depth_vs_sticks": res["depth_vs_sticks"],
                "dist_from_qb": res["dist_from_qb"],
            })
            rows.append(df)
        out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
        return out, no_def

    pre_df, no_def_pre = _features_at(pre, "_pre")
    rel_df, no_def_rel = _features_at(0, "_rel")

    # Pre-release carries the context columns; release carries only its triple.
    rel_df = rel_df[["gameId", "playId", "nflId",
                     "separation_rel", "closing_speed_rel", "lane_penalty_rel"]]
    feats = pre_df.merge(rel_df, on=["gameId", "playId", "nflId"], how="left")

    # Composite Openness_Score (authoritative; metrics_plan.md, Req 12.9).
    def _openness(sep, closing, lane):
        return sep - closing_horizon_s * closing - lambda_lane * lane

    feats["openness_pre"] = _openness(
        feats["separation_pre"], feats["closing_speed_pre"], feats["lane_penalty_pre"])
    feats["openness_rel"] = _openness(
        feats["separation_rel"], feats["closing_speed_rel"], feats["lane_penalty_rel"])

    # Rusher distance per play: min QB->Pass Rush distance at offset 0 (Req 13.4).
    rusher, no_rush = _rusher_distance(c1)
    feats = feats.merge(rusher, on=key, how="left")

    # Target flag (Req 15.3).
    tgt = plays[["gameId", "playId", "target_nflId"]]
    feats = feats.merge(tgt, on=key, how="left")
    # Both are plain int64 among eligible receivers; result is a clean bool.
    feats["is_target"] = (feats["nflId"] == feats["target_nflId"]).astype(bool)
    feats = feats.drop(columns=["target_nflId"])

    # Most_Open: one per play, highest openness_pre, ties to lowest nflId (Req 12.6).
    feats = _mark_most_open(feats, key)

    # Open_Flag depends on Open_Mode (Req 12.7-12.8).
    if cfg.open_mode == "most_open":
        feats["open_flag"] = feats["is_most_open"]
    else:
        feats["open_flag"] = feats["separation_pre"] >= cfg.open_threshold

    cols = ["gameId", "playId", "nflId",
            "separation_pre", "closing_speed_pre", "lane_penalty_pre", "openness_pre",
            "separation_rel", "closing_speed_rel", "lane_penalty_rel", "openness_rel",
            "depth", "depth_vs_sticks", "dist_from_qb", "rusher_distance",
            "is_target", "is_most_open", "open_flag"]
    feats = feats[cols].sort_values(key + ["nflId"]).reset_index(drop=True)

    # Expose the missing-data counts (Req 11.6, 13.5).
    feats.attrs["n_no_defender_pre"] = no_def_pre
    feats.attrs["n_no_defender_rel"] = no_def_rel
    feats.attrs["n_no_rusher"] = no_rush
    return feats


def _rusher_distance(c1: pd.DataFrame):
    """Per-play min QB->Pass Rush distance at offset 0 (Req 13.4-13.5).

    Returns (DataFrame[gameId, playId, rusher_distance], n_plays_without_rusher).
    """
    key = ["gameId", "playId"]
    at0 = c1[c1["offset"] == 0]
    qb = at0[at0["is_qb"].to_numpy()][key + ["x", "y"]].rename(
        columns={"x": "qx", "y": "qy"})
    rush = at0[at0["pff_role"].to_numpy() == "Pass Rush"][key + ["x", "y"]]
    rush = rush.merge(qb, on=key, how="inner")
    rush["d"] = np.hypot(rush["x"] - rush["qx"], rush["y"] - rush["qy"])
    nearest = rush.groupby(key, sort=False)["d"].min().reset_index()
    nearest = nearest.rename(columns={"d": "rusher_distance"})

    all_plays = at0[key].drop_duplicates()
    out = all_plays.merge(nearest, on=key, how="left")   # NaN where no rusher
    n_no_rusher = int(out["rusher_distance"].isna().sum())
    return out, n_no_rusher


def _mark_most_open(feats: pd.DataFrame, key):
    """Exactly one is_most_open per play: max openness_pre, ties to lowest nflId.

    NaN openness never wins (sorted last). Every play keeps exactly one winner.
    """
    order = feats.sort_values(
        key + ["openness_pre", "nflId"],
        ascending=[True, True, False, True],
        na_position="last",
    )
    winner_idx = order.groupby(key, sort=False).head(1).index
    feats["is_most_open"] = False
    feats.loc[winner_idx, "is_most_open"] = True
    return feats


if __name__ == "__main__":
    from pathlib import Path

    from config import Config

    cfg = Config()
    c1 = validate_c1(pd.read_parquet(cfg.derived_dir / C1_FILE))
    c2 = validate_c2(pd.read_parquet(cfg.derived_dir / C2_FILE))

    feats = build_route_features(c1, c2, cfg)

    n_plays = feats[["gameId", "playId"]].drop_duplicates().shape[0]
    per_play = feats.groupby(["gameId", "playId"])[["is_target", "is_most_open"]].sum()
    one_target = (per_play["is_target"] == 1).all()
    one_most_open = (per_play["is_most_open"] == 1).all()
    agree = float((feats["is_most_open"] & feats["is_target"]).sum()) / n_plays

    print("=== build_route_features sanity (Req 11-13, 15.2) ===")
    print(f"routes (eligible receiver x model play): {len(feats):,}")
    print(f"model plays covered: {n_plays:,}")
    print(f"exactly one is_target per play:    {one_target}")
    print(f"exactly one is_most_open per play: {one_most_open}")
    print(f"separation_pre  mean={feats['separation_pre'].mean():.3f} "
          f"median={feats['separation_pre'].median():.3f}")
    print(f"openness_pre    mean={feats['openness_pre'].mean():.3f} "
          f"median={feats['openness_pre'].median():.3f}")
    print(f"no-defender routes  pre={feats.attrs['n_no_defender_pre']} "
          f"rel={feats.attrs['n_no_defender_rel']}")
    print(f"no-rusher plays:    {feats.attrs['n_no_rusher']}")
    print(f"is_most_open == is_target agreement rate: {agree:.3f}")

    assert one_target, "a model play does not have exactly one is_target"
    assert one_most_open, "a model play does not have exactly one is_most_open"
