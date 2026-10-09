"""Contract tooling for the Metrics tables: the C3-C6 schemas, validators and fixtures.

Mirrors contracts_data.py: a schema is {column: (kind, nullable, allowed)} with
kind one of "int", "float", "str", "bool"; validate() collects every violation and
raises one ValueError (Req 20.1, 20.2). The extra per-table checks encode the metric
invariants (xtarget sums to 1 per play, toe sums to 0 per split, openness_gap >= 0).

    from contracts_metrics import validate_c3, validate_c4
    c3 = validate_c3(pd.read_parquet("out/c3_routes.parquet"))

Nullable int columns must use pandas "Int64". fixture_c3c6(cfg) writes synthetic
C3-C6 parquet to out/fixtures/ so Dev 3 can build charts before real numbers land.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from contracts_data import _examples, validate

C3_FILE = "c3_routes.parquet"
C4_FILE = "c4_receiver_toe.parquet"
C5A_FILE = "c5a_offense.parquet"
C5B_FILE = "c5b_defense.parquet"
C6_FILE = "c6_instead.parquet"

POSITION_GROUPS = {"WR", "TE", "RB"}
COVERAGE_TYPES = {"Man", "Zone", "Other"}

# Contract C3 Route_Features_Table: one row per Route on a Model_Play.
C3_SCHEMA = {
    "gameId": ("int", False, None),
    "playId": ("int", False, None),
    "nflId": ("int", False, None),
    "week": ("int", False, None),
    "displayName": ("str", False, None),
    "position_group": ("str", False, POSITION_GROUPS),
    "possessionTeam": ("str", False, None),
    "defensiveTeam": ("str", False, None),
    "coverage_type": ("str", True, COVERAGE_TYPES),
    "coverage_family": ("str", True, None),
    "down": ("int", False, None),
    "yardsToGo": ("int", False, None),
    "separation_pre": ("float", False, None),
    "closing_speed_pre": ("float", False, None),
    "openness_pre": ("float", False, None),
    "separation_rel": ("float", False, None),
    "closing_speed_rel": ("float", False, None),
    "openness_rel": ("float", False, None),
    "lane_penalty_pre": ("float", False, None),
    "lane_penalty_rel": ("float", False, None),
    "depth": ("float", False, None),
    "depth_vs_sticks": ("float", False, None),
    "dist_from_qb": ("float", False, None),
    "rusher_distance": ("float", True, None),
    "pressured": ("bool", False, None),
    "is_most_open": ("bool", False, None),
    "open_flag": ("bool", False, None),
    "is_target": ("bool", False, None),
    "xtarget": ("float", False, None),
    "xtarget_rel": ("float", True, None),
}
C3_KEY = ["gameId", "playId", "nflId"]

# Contract C4 Receiver_TOE_Table: one row per receiver per Split.
C4_SCHEMA = {
    "nflId": ("int", False, None),
    "displayName": ("str", False, None),
    "position_group": ("str", True, POSITION_GROUPS),
    "team": ("str", False, None),
    "split": ("str", False, None),
    "routes": ("int", False, None),
    "targets": ("int", False, None),
    "open_routes": ("int", False, None),
    "x_targets": ("float", False, None),
    "toe": ("float", False, None),
    "toe_per_100_routes": ("float", False, None),
    "open_rate": ("float", False, None),
    "target_share": ("float", False, None),
    "meets_minimum": ("bool", False, None),
}
C4_KEY = ["nflId", "split"]

# Contract C5a Offense_Team_Table: one row per offense.
C5A_SCHEMA = {
    "team": ("str", False, None),
    "model_plays": ("int", False, None),
    "routes": ("int", False, None),
    "funnel_index": ("float", False, None),
    "top_over_nflId": ("int", True, None),
    "top_over_name": ("str", True, None),
    "top_over_toe": ("float", True, None),
    "top_ignored_nflId": ("int", True, None),
    "top_ignored_name": ("str", True, None),
    "top_ignored_toe": ("float", True, None),
}
C5A_KEY = ["team"]

# Contract C5b Defense_Team_Table: one row per defense.
C5B_SCHEMA = {
    "team": ("str", False, None),
    "model_plays": ("int", False, None),
    "ignored_open_events": ("int", False, None),
    "ignored_open_rate": ("float", False, None),
    "mean_most_open_separation": ("float", True, None),
}
C5B_KEY = ["team"]

# Contract C6 Instead_Table: one row per Ignored_Open_Event.
C6_SCHEMA = {
    "gameId": ("int", False, None),
    "playId": ("int", False, None),
    "possessionTeam": ("str", False, None),
    "defensiveTeam": ("str", False, None),
    "coverage_type": ("str", True, COVERAGE_TYPES),
    "coverage_family": ("str", True, None),
    "down": ("int", False, None),
    "ignored_nflId": ("int", False, None),
    "ignored_name": ("str", False, None),
    "ignored_position_group": ("str", True, POSITION_GROUPS),
    "ignored_separation": ("float", False, None),
    "ignored_depth": ("float", False, None),
    "ignored_openness": ("float", False, None),
    "target_nflId": ("int", False, None),
    "target_name": ("str", False, None),
    "target_position_group": ("str", True, POSITION_GROUPS),
    "target_separation": ("float", False, None),
    "target_depth": ("float", False, None),
    "target_openness": ("float", False, None),
    "openness_gap": ("float", False, None),
}
C6_KEY = ["gameId", "playId"]


# ---------------------------------------------------------------------------
# Extra per-table invariant checks (beyond the schema).

def c3_extra_checks(df):
    """C3 rules beyond the schema: one target / one most-open per play; xtarget sums to 1."""
    errors = []
    key = ["gameId", "playId"]
    per_play = df.groupby(key)[["is_target", "is_most_open"]].sum()
    bad_t = per_play[per_play["is_target"] != 1]
    if len(bad_t):
        errors.append(f"is_target: {len(bad_t)} play(s) without exactly one target, "
                      f"e.g. {_examples(bad_t.index)}")
    bad_o = per_play[per_play["is_most_open"] != 1]
    if len(bad_o):
        errors.append(f"is_most_open: {len(bad_o)} play(s) without exactly one most-open, "
                      f"e.g. {_examples(bad_o.index)}")
    sums = df.groupby(key)["xtarget"].sum()
    off = sums[~np.isclose(sums, 1.0, atol=1e-6)]
    if len(off):
        errors.append(f"xtarget: {len(off)} play(s) whose xtarget does not sum to 1, "
                      f"e.g. {_examples(off.round(4).index)}")
    bad_x = df[(df["xtarget"] < -1e-9) | (df["xtarget"] > 1 + 1e-9)]
    if len(bad_x):
        errors.append(f"xtarget: {len(bad_x)} value(s) outside [0, 1]")
    return errors


# Position-group breakdowns of a coverage family (Req 16.3) carry " | <group>" in the
# split name. They aggregate only some receivers per play, so TOE need not sum to 0;
# the Req 16.7 invariant is checked on the whole-play splits only.
def _is_whole_play_split(split):
    return " | " not in str(split)


def c4_extra_checks(df):
    """C4 rules beyond the schema: toe sums to 0 per whole-play split; rates in [0,1]."""
    errors = []
    whole = df[df["split"].map(_is_whole_play_split)]
    toe = whole.groupby("split")["toe"].sum()
    off = toe[~np.isclose(toe, 0.0, atol=1e-6)]
    if len(off):
        errors.append(f"toe: {len(off)} split(s) whose toe does not sum to 0, "
                      f"e.g. {_examples(off.round(6).index)} (Req 16.7)")
    for col in ("open_rate", "target_share"):
        bad = df[(df[col] < -1e-9) | (df[col] > 1 + 1e-9)]
        if len(bad):
            errors.append(f"{col}: {len(bad)} value(s) outside [0, 1] (Req 16.8)")
    bad_tr = df[df["targets"] > df["routes"]]
    if len(bad_tr):
        errors.append(f"targets: {len(bad_tr)} row(s) with targets > routes (Req 16.8)")
    # Man + Zone routes <= All routes per receiver (Req 16.9).
    wide = df.pivot_table(index="nflId", columns="split", values="routes",
                          aggfunc="sum", fill_value=0)
    for sp in ("All", "Man", "Zone"):
        if sp not in wide.columns:
            wide[sp] = 0
    bad_mz = wide[(wide["Man"] + wide["Zone"]) > wide["All"] + 1e-9]
    if len(bad_mz):
        errors.append(f"routes: {len(bad_mz)} receiver(s) with Man+Zone > All routes (Req 16.9)")
    return errors


def c5a_extra_checks(df):
    """C5a rules beyond the schema: funnel_index non-negative (Req 17.5)."""
    errors = []
    bad = df[df["funnel_index"] < -1e-9]
    if len(bad):
        errors.append(f"funnel_index: {len(bad)} team(s) with a negative funnel_index (Req 17.5)")
    return errors


def c5b_extra_checks(df):
    """C5b rules beyond the schema: ignored_open_rate in [0, 1]."""
    errors = []
    bad = df[(df["ignored_open_rate"] < -1e-9) | (df["ignored_open_rate"] > 1 + 1e-9)]
    if len(bad):
        errors.append(f"ignored_open_rate: {len(bad)} value(s) outside [0, 1]")
    return errors


def c6_extra_checks(df):
    """C6 rules beyond the schema: openness_gap >= 0 and ignored != target (Req 18.3, 18.4)."""
    errors = []
    bad_gap = df[df["openness_gap"] < -1e-6]
    if len(bad_gap):
        errors.append(f"openness_gap: {len(bad_gap)} event(s) with a negative gap (Req 18.4)")
    bad_id = df[df["ignored_nflId"] == df["target_nflId"]]
    if len(bad_id):
        errors.append(f"ignored_nflId: {len(bad_id)} event(s) where ignored == target (Req 18.3)")
    return errors


def validate_c3(df, name="C3 Route_Features_Table"):
    return validate(df, C3_SCHEMA, C3_KEY, name, checks=(c3_extra_checks,))


def validate_c4(df, name="C4 Receiver_TOE_Table"):
    return validate(df, C4_SCHEMA, C4_KEY, name, checks=(c4_extra_checks,))


def validate_c5a(df, name="C5a Offense_Team_Table"):
    return validate(df, C5A_SCHEMA, C5A_KEY, name, checks=(c5a_extra_checks,))


def validate_c5b(df, name="C5b Defense_Team_Table"):
    return validate(df, C5B_SCHEMA, C5B_KEY, name, checks=(c5b_extra_checks,))


def validate_c6(df, name="C6 Instead_Table"):
    return validate(df, C6_SCHEMA, C6_KEY, name, checks=(c6_extra_checks,))


# ---------------------------------------------------------------------------
# Fixtures (Req 20.3): >= 20 receivers across 4 teams; xtarget sums to 1 per play;
# toe sums to 0 per split. Synthetic but contract-valid so Dev 3 can build early.

_FX_TEAMS = ["FXA", "FXB", "FXC", "FXD"]
_FX_DEFENSE = {"FXA": "FXB", "FXB": "FXA", "FXC": "FXD", "FXD": "FXC"}
_FX_GROUPS = ["WR", "WR", "TE", "RB", "WR", "TE"]   # 6 receivers per team => 24 receivers
_FX_FAMILIES = {"Man": "Cover-1", "Zone": "Cover-3"}


def _fixture_tables(cfg):
    """Build contract-valid C3-C6 frames in memory; return (c3, c4, c5a, c5b, c6)."""
    rng = np.random.default_rng(20231009)

    # 24 receivers: 6 per team, globally unique nflId. 10 model plays per team.
    receivers = []
    for ti, team in enumerate(_FX_TEAMS):
        for ri, group in enumerate(_FX_GROUPS):
            receivers.append(dict(
                nflId=800000 + ti * 100 + ri,
                displayName=f"{team} Receiver {ri}",
                position_group=group,
                team=team,
            ))
    rec_df = pd.DataFrame(receivers)

    # --- C3: one row per receiver per model play, 2 plays per team. ---
    c3_rows = []
    game_id = 9999999950
    play_counter = 0
    for ti, team in enumerate(_FX_TEAMS):
        team_recs = rec_df[rec_df["team"] == team].reset_index(drop=True)
        for p in range(2):
            play_counter += 1
            play_id = 1000 + play_counter
            cov_type = "Man" if (p % 2 == 0) else "Zone"
            cov_family = _FX_FAMILIES[cov_type]
            n = len(team_recs)
            sep = rng.uniform(1.0, 8.0, n)
            closing = rng.uniform(-1.0, 3.0, n)
            lane = np.maximum(0.0, rng.uniform(-1.0, 2.0, n))
            openness = sep - 0.5 * closing - 0.5 * lane
            depth = rng.uniform(-2.0, 20.0, n)
            # xtarget: softmax over openness so it sums to 1 per play (Req 14.4).
            w = np.exp(openness - openness.max())
            xtarget = w / w.sum()
            most_open = int(np.argmax(openness))
            target = int(rng.integers(0, n))
            for i in range(n):
                r = team_recs.iloc[i]
                c3_rows.append(dict(
                    gameId=game_id, playId=play_id, nflId=int(r["nflId"]),
                    week=1 + ti, displayName=r["displayName"],
                    position_group=r["position_group"],
                    possessionTeam=team, defensiveTeam=_FX_DEFENSE[team],
                    coverage_type=cov_type, coverage_family=cov_family,
                    down=1 + (p % 4), yardsToGo=10,
                    separation_pre=float(sep[i]), closing_speed_pre=float(closing[i]),
                    openness_pre=float(openness[i]),
                    separation_rel=float(sep[i] + rng.normal(0, 0.3)),
                    closing_speed_rel=float(closing[i] + rng.normal(0, 0.3)),
                    openness_rel=float(openness[i] + rng.normal(0, 0.3)),
                    lane_penalty_pre=float(lane[i]),
                    lane_penalty_rel=float(max(0.0, lane[i] + rng.normal(0, 0.2))),
                    depth=float(depth[i]),
                    depth_vs_sticks=float(depth[i] - 10.0),
                    dist_from_qb=float(abs(depth[i]) + rng.uniform(1, 5)),
                    rusher_distance=float(rng.uniform(1.0, 6.0)),
                    pressured=bool(rng.integers(0, 2)),
                    is_most_open=(i == most_open),
                    open_flag=(i == most_open),
                    is_target=(i == target),
                    xtarget=float(xtarget[i]),
                    xtarget_rel=float(xtarget[i]),
                ))
    c3 = pd.DataFrame(c3_rows)

    # --- C4: build per split so toe sums to 0 within each split (Req 16.7). ---
    c4 = _fixture_c4(c3, cfg)

    # --- C5a / C5b: per team, consistent with C3. ---
    c5a, c5b = _fixture_c5(c3)

    # --- C6: Ignored_Open_Events (most_open != target) from C3. ---
    c6 = _fixture_c6(c3)

    return _cast_c3(c3), c4, c5a, c5b, c6


def _cast_c3(c3):
    c3 = c3.astype({
        "gameId": "int64", "playId": "int64", "nflId": "int64", "week": "int64",
        "down": "int64", "yardsToGo": "int64", "pressured": bool,
        "is_most_open": bool, "open_flag": bool, "is_target": bool,
    })
    return c3[list(C3_SCHEMA)]


def _c4_rows_for_split(sub, split, cfg):
    """One C4 row per receiver over the C3 slice `sub` (already filtered to the split)."""
    minimum = cfg.route_minimum if split == "All" else cfg.split_route_minimum
    rows = []
    for nfl_id, g in sub.groupby("nflId"):
        routes = len(g)
        targets = int(g["is_target"].sum())
        x_targets = float(g["xtarget"].sum())
        open_routes = int(g["open_flag"].sum())
        rows.append(dict(
            nflId=int(nfl_id), displayName=g["displayName"].iloc[0],
            position_group=g["position_group"].iloc[0],
            team=g["possessionTeam"].mode().iloc[0], split=split,
            routes=routes, targets=targets, open_routes=open_routes,
            x_targets=x_targets, toe=float(targets - x_targets),
            toe_per_100_routes=float((targets - x_targets) / routes * 100),
            open_rate=float(open_routes / routes),
            target_share=float(targets / routes),
            meets_minimum=bool(routes >= minimum),
        ))
    return rows


def _fixture_c4(c3, cfg):
    rows = []
    rows += _c4_rows_for_split(c3, "All", cfg)
    for cov_type in ("Man", "Zone"):
        rows += _c4_rows_for_split(c3[c3["coverage_type"] == cov_type], cov_type, cfg)
    for family in sorted(c3["coverage_family"].dropna().unique()):
        rows += _c4_rows_for_split(c3[c3["coverage_family"] == family], family, cfg)
    c4 = pd.DataFrame(rows).astype({
        "nflId": "int64", "routes": "int64", "targets": "int64",
        "open_routes": "int64", "meets_minimum": bool,
    })
    return c4[list(C4_SCHEMA)]


def _fixture_c5(c3):
    key = ["gameId", "playId"]
    a_rows, b_rows = [], []
    for team, g in c3.groupby("possessionTeam"):
        model_plays = g[key].drop_duplicates().shape[0]
        routes = len(g)
        toe_by_rec = (g.assign(toe=g["is_target"].astype(float) - g["xtarget"])
                        .groupby(["nflId", "displayName"])["toe"].sum())
        funnel = float(toe_by_rec[toe_by_rec > 0].sum() / model_plays)
        over = toe_by_rec.idxmax()
        ign = toe_by_rec.idxmin()
        a_rows.append(dict(
            team=team, model_plays=model_plays, routes=routes, funnel_index=funnel,
            top_over_nflId=int(over[0]), top_over_name=over[1],
            top_over_toe=float(toe_by_rec.max()),
            top_ignored_nflId=int(ign[0]), top_ignored_name=ign[1],
            top_ignored_toe=float(toe_by_rec.min()),
        ))
    for team, g in c3.groupby("defensiveTeam"):
        plays = g.groupby(key)
        model_plays = plays.ngroups
        ignored = 0
        seps = []
        for _, pg in plays:
            mo = pg[pg["is_most_open"]]
            seps.append(float(mo["separation_pre"].iloc[0]))
            if not bool(mo["is_target"].iloc[0]):
                ignored += 1
        b_rows.append(dict(
            team=team, model_plays=model_plays, ignored_open_events=ignored,
            ignored_open_rate=float(ignored / model_plays),
            mean_most_open_separation=float(np.mean(seps)),
        ))
    c5a = pd.DataFrame(a_rows).astype({
        "model_plays": "int64", "routes": "int64",
        "top_over_nflId": "Int64", "top_ignored_nflId": "Int64",
    })[list(C5A_SCHEMA)]
    c5b = pd.DataFrame(b_rows).astype({
        "model_plays": "int64", "ignored_open_events": "int64",
    })[list(C5B_SCHEMA)]
    return c5a, c5b


def _fixture_c6(c3):
    key = ["gameId", "playId"]
    rows = []
    for (g_id, p_id), pg in c3.groupby(key):
        mo = pg[pg["is_most_open"]].iloc[0]
        tg = pg[pg["is_target"]].iloc[0]
        if int(mo["nflId"]) == int(tg["nflId"]):
            continue
        rows.append(dict(
            gameId=int(g_id), playId=int(p_id),
            possessionTeam=mo["possessionTeam"], defensiveTeam=mo["defensiveTeam"],
            coverage_type=mo["coverage_type"], coverage_family=mo["coverage_family"],
            down=int(mo["down"]),
            ignored_nflId=int(mo["nflId"]), ignored_name=mo["displayName"],
            ignored_position_group=mo["position_group"],
            ignored_separation=float(mo["separation_pre"]),
            ignored_depth=float(mo["depth"]),
            ignored_openness=float(mo["openness_pre"]),
            target_nflId=int(tg["nflId"]), target_name=tg["displayName"],
            target_position_group=tg["position_group"],
            target_separation=float(tg["separation_pre"]),
            target_depth=float(tg["depth"]),
            target_openness=float(tg["openness_pre"]),
            openness_gap=float(mo["openness_pre"] - tg["openness_pre"]),
        ))
    c6 = pd.DataFrame(rows).astype({
        "gameId": "int64", "playId": "int64",
        "ignored_nflId": "int64", "target_nflId": "int64", "down": "int64",
    })
    return c6[list(C6_SCHEMA)]


def fixture_c3c6(cfg):
    """Write synthetic C3-C6 (24 receivers, 4 teams) to out/fixtures/; return the tables.

    Validates every table before writing (Req 20.3): xtarget sums to 1 per play,
    toe sums to 0 per split, openness_gap >= 0.
    """
    c3, c4, c5a, c5b, c6 = _fixture_tables(cfg)

    validate_c3(c3, "C3 fixture")
    validate_c4(c4, "C4 fixture")
    validate_c5a(c5a, "C5a fixture")
    validate_c5b(c5b, "C5b fixture")
    validate_c6(c6, "C6 fixture")

    out_dir = cfg.derived_dir / "fixtures"
    out_dir.mkdir(parents=True, exist_ok=True)
    c3.to_parquet(out_dir / C3_FILE, index=False)
    c4.to_parquet(out_dir / C4_FILE, index=False)
    c5a.to_parquet(out_dir / C5A_FILE, index=False)
    c5b.to_parquet(out_dir / C5B_FILE, index=False)
    c6.to_parquet(out_dir / C6_FILE, index=False)
    return c3, c4, c5a, c5b, c6
