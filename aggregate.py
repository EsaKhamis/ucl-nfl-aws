"""Metrics stage: build C3-C6 and the model report (Dev 2; Requirements 15-18).

`build(cfg)` is the stage entry point run.py calls. It reads C1/C2 from Derived_Dir
(or out/fixtures/ when cfg.fixtures), computes route features (features.py), fits the
expected-target model (model.py), then assembles and validates:

    C3  Route_Features_Table   one row per Route on a Model_Play
    C4  Receiver_TOE_Table      per receiver per Split (All, Man, Zone, families, by pos)
    C5a Offense_Team_Table      per offense (funnel index, top over / ignored receiver)
    C5b Defense_Team_Table      per defense (ignored-open events / rate / mean separation)
    C6  Instead_Table           one row per Ignored_Open_Event

C3 and C4 are P0 and always written. C5/C6 are P1: wrapped in try/except so a failure
there still leaves a valid C3 and C4 on disk. Every table is validated via
contracts_metrics before build returns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import contracts_data
import contracts_metrics as cm
import features
import model

PLAY_KEY = ["gameId", "playId"]


# ---------------------------------------------------------------------------
# Loading inputs.

def _load_inputs(cfg):
    """Read + validate C1/C2 (from fixtures when cfg.fixtures); return (c1, c2)."""
    src = cfg.derived_dir / "fixtures" if cfg.fixtures else cfg.derived_dir
    c1 = contracts_data.validate_c1(pd.read_parquet(src / contracts_data.C1_FILE))
    c2 = contracts_data.validate_c2(pd.read_parquet(src / contracts_data.C2_FILE))
    if cfg.games:
        games = set(cfg.games)
        c1 = c1[c1["gameId"].isin(games)].reset_index(drop=True)
        c2 = c2[c2["gameId"].isin(games)].reset_index(drop=True)
    return c1, c2


def _player_names(cfg):
    """displayName per nflId, from players.csv (position_group comes from C1)."""
    players = pd.read_csv(cfg.data_dir / "players.csv", na_values=["NA"])
    return players[["nflId", "displayName"]].copy()


def _position_groups(c1):
    """WR/TE/RB Position_Group per nflId, taken from the eligible C1 rows (C1 is authoritative)."""
    elig = c1[c1["is_eligible"].astype(bool) & c1["position_group"].notna()]
    pg = elig[["nflId", "position_group"]].drop_duplicates("nflId")
    pg["nflId"] = pg["nflId"].astype("int64")
    return pg


# ---------------------------------------------------------------------------
# C3 Route_Features_Table (Req 15).

def _build_c3(feats, c2, names, pos_groups, cfg):
    """Assemble C3 from route features + per-play context (C2) + names + position groups."""
    ctx = c2[[
        "gameId", "playId", "week", "possessionTeam", "defensiveTeam",
        "pff_passCoverageType", "pff_passCoverage", "down", "yardsToGo",
        "pressured", "target_nflId",
    ]].rename(columns={
        "pff_passCoverageType": "coverage_type",
        "pff_passCoverage": "coverage_family",
    })

    c3 = feats.merge(ctx, on=PLAY_KEY, how="left")
    # displayName from players.csv; position_group (WR/TE/RB) from the eligible C1 rows.
    c3 = c3.merge(names, on="nflId", how="left")
    c3 = c3.merge(pos_groups, on="nflId", how="left")
    c3["displayName"] = c3["displayName"].fillna("Unknown")

    # Asserts (Req 15.2, 15.3).
    per_play = c3.groupby(PLAY_KEY)[["is_target", "is_most_open"]].sum()
    assert (per_play["is_target"] == 1).all(), "a Model_Play lacks exactly one is_target (Req 15.2)"
    assert (per_play["is_most_open"] == 1).all(), "a Model_Play lacks exactly one is_most_open"
    assert (c3["is_target"] == (c3["nflId"] == c3["target_nflId"])).all(), \
        "is_target does not match nflId == target_nflId (Req 15.3)"

    c3 = c3.astype({
        "gameId": "int64", "playId": "int64", "nflId": "int64", "week": "int64",
        "down": "int64", "yardsToGo": "int64", "pressured": bool,
        "is_most_open": bool, "open_flag": bool, "is_target": bool,
    })
    c3["xtarget"] = c3["xtarget"].astype(float)
    if c3["xtarget_rel"].isna().all():
        c3["xtarget_rel"] = pd.array([pd.NA] * len(c3), dtype="Float64")
    else:
        c3["xtarget_rel"] = c3["xtarget_rel"].astype("Float64")
    c3 = c3[list(cm.C3_SCHEMA)].sort_values(cm.C3_KEY).reset_index(drop=True)
    return c3


# ---------------------------------------------------------------------------
# C4 Receiver_TOE_Table (Req 16).

def _receiver_team(c3):
    """possessionTeam with the most Routes per receiver (Req 16 / C4.team)."""
    counts = c3.groupby(["nflId", "possessionTeam"]).size().reset_index(name="n")
    counts = counts.sort_values(["nflId", "n", "possessionTeam"],
                                ascending=[True, False, True])
    best = counts.groupby("nflId").head(1)[["nflId", "possessionTeam"]]
    return best.rename(columns={"possessionTeam": "team"})


def _c4_split(sub, split, minimum, team_map):
    """One C4 row per receiver over the C3 slice `sub` (already filtered to the split)."""
    sub = sub.assign(toe_row=sub["is_target"].astype(float) - sub["xtarget"])
    grp = sub.groupby(["nflId", "displayName", "position_group"], dropna=False)
    agg = grp.agg(
        routes=("is_target", "size"),
        targets=("is_target", "sum"),
        open_routes=("open_flag", "sum"),
        x_targets=("xtarget", "sum"),
        toe=("toe_row", "sum"),
    ).reset_index()
    agg["toe_per_100_routes"] = agg["toe"] / agg["routes"] * 100
    agg["open_rate"] = agg["open_routes"] / agg["routes"]
    agg["target_share"] = agg["targets"] / agg["routes"]
    agg["split"] = split
    agg["meets_minimum"] = agg["routes"] >= minimum
    agg = agg.merge(team_map, on="nflId", how="left")
    return agg


def _build_c4(c3, cfg):
    """All, Man, Zone, each Coverage_Family (Other only in All), families by Position_Group."""
    team_map = _receiver_team(c3)
    parts = []
    parts.append(_c4_split(c3, "All", cfg.route_minimum, team_map))
    for cov in ("Man", "Zone"):
        parts.append(_c4_split(c3[c3["coverage_type"] == cov], cov,
                               cfg.split_route_minimum, team_map))

    families = sorted(c3.loc[c3["coverage_type"].isin(["Man", "Zone"]),
                             "coverage_family"].dropna().unique())
    for fam in families:
        fam_rows = c3[c3["coverage_family"] == fam]
        parts.append(_c4_split(fam_rows, fam, cfg.split_route_minimum, team_map))
        # Also aggregate the family by Position_Group (Req 16.3).
        for pg, pg_rows in fam_rows.groupby("position_group"):
            parts.append(_c4_split(pg_rows, f"{fam} | {pg}",
                                   cfg.split_route_minimum, team_map))

    c4 = pd.concat(parts, ignore_index=True)
    c4 = c4.astype({
        "nflId": "int64", "routes": "int64", "targets": "int64",
        "open_routes": "int64", "x_targets": "float64", "toe": "float64",
        "meets_minimum": bool,
    })
    c4 = c4[list(cm.C4_SCHEMA)].sort_values(cm.C4_KEY).reset_index(drop=True)

    # Asserts (Req 16.7, 16.8, 16.9). TOE sums to 0 within every whole-play split;
    # the family-by-position-group breakdowns (Req 16.3) are partial, so are excluded.
    whole = c4[~c4["split"].str.contains(r" \| ", regex=True)]
    toe_by_split = whole.groupby("split")["toe"].sum()
    assert np.allclose(toe_by_split.to_numpy(), 0.0, atol=1e-6), \
        "toe does not sum to 0 within every whole-play split (Req 16.7)"
    assert (c4["targets"] <= c4["routes"]).all(), "targets > routes (Req 16.8)"
    assert c4["open_rate"].between(0, 1).all() and c4["target_share"].between(0, 1).all(), \
        "open_rate or target_share outside [0, 1] (Req 16.8)"
    wide = c4.pivot_table(index="nflId", columns="split", values="routes",
                          aggfunc="sum", fill_value=0)
    for sp in ("All", "Man", "Zone"):
        if sp not in wide.columns:
            wide[sp] = 0
    assert ((wide["Man"] + wide["Zone"]) <= wide["All"] + 1e-9).all(), \
        "Man + Zone routes exceed All routes for some receiver (Req 16.9)"
    return c4


def _report_route_quartiles(c4):
    """Print min / quartiles / max of All-split routes per receiver (Req 16.5)."""
    allsplit = c4[c4["split"] == "All"]["routes"]
    q = allsplit.quantile([0.0, 0.25, 0.5, 0.75, 1.0])
    print("=== All-split routes per receiver (set Route_Minimum from this, Req 16.5) ===")
    print(f"  receivers={len(allsplit)}  min={int(q[0.0])}  q1={q[0.25]:.0f}  "
          f"median={q[0.5]:.0f}  q3={q[0.75]:.0f}  max={int(q[1.0])}")


# ---------------------------------------------------------------------------
# C5 Team tables (Req 17, P1).

def _build_c5(c3, cfg):
    team_map = _receiver_team(c3)
    c3 = c3.assign(toe_row=c3["is_target"].astype(float) - c3["xtarget"])

    # C5a offense.
    a_rows = []
    for team, g in c3.groupby("possessionTeam"):
        model_plays = g[PLAY_KEY].drop_duplicates().shape[0]
        routes = len(g)
        toe_by_rec = g.groupby(["nflId", "displayName"])["toe_row"].sum()
        route_by_rec = g.groupby("nflId").size()
        funnel = float(toe_by_rec[toe_by_rec > 0].sum() / model_plays) if model_plays else 0.0

        eligible = toe_by_rec[route_by_rec.reindex(
            toe_by_rec.index.get_level_values("nflId")).to_numpy() >= cfg.team_route_minimum]
        over = ign = None
        if len(eligible):
            over = eligible.idxmax()
            ign = eligible.idxmin()
        a_rows.append(dict(
            team=team, model_plays=model_plays, routes=routes, funnel_index=funnel,
            top_over_nflId=int(over[0]) if over else pd.NA,
            top_over_name=over[1] if over else pd.NA,
            top_over_toe=float(eligible.max()) if over else pd.NA,
            top_ignored_nflId=int(ign[0]) if ign else pd.NA,
            top_ignored_name=ign[1] if ign else pd.NA,
            top_ignored_toe=float(eligible.min()) if ign else pd.NA,
        ))
    c5a = pd.DataFrame(a_rows).astype({
        "model_plays": "int64", "routes": "int64", "funnel_index": "float64",
        "top_over_nflId": "Int64", "top_ignored_nflId": "Int64",
        "top_over_toe": "Float64", "top_ignored_toe": "Float64",
    })[list(cm.C5A_SCHEMA)].sort_values("team").reset_index(drop=True)

    # C5b defense.
    b_rows = []
    for team, g in c3.groupby("defensiveTeam"):
        plays = g.groupby(PLAY_KEY)
        model_plays = plays.ngroups
        most_open = g[g["is_most_open"]]
        ignored = int((~most_open["is_target"]).sum())
        b_rows.append(dict(
            team=team, model_plays=model_plays, ignored_open_events=ignored,
            ignored_open_rate=float(ignored / model_plays) if model_plays else 0.0,
            mean_most_open_separation=float(most_open["separation_pre"].mean()),
        ))
    c5b = pd.DataFrame(b_rows).astype({
        "model_plays": "int64", "ignored_open_events": "int64",
    })[list(cm.C5B_SCHEMA)].sort_values("team").reset_index(drop=True)
    return c5a, c5b


# ---------------------------------------------------------------------------
# C6 Instead_Table (Req 18, P1).

def _build_c6(c3):
    rows = []
    for (g_id, p_id), pg in c3.groupby(PLAY_KEY, sort=False):
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
    c6 = pd.DataFrame(rows, columns=list(cm.C6_SCHEMA))
    if len(c6):
        c6 = c6.astype({
            "gameId": "int64", "playId": "int64",
            "ignored_nflId": "int64", "target_nflId": "int64", "down": "int64",
        })
        # openness_gap >= 0 by construction (most_open has the highest openness_pre).
        assert (c6["openness_gap"] >= -1e-6).all(), "openness_gap < 0 (Req 18.4)"
    return c6


def _report_headline(c4):
    """Print top-5 over-targeted and top-5 ignored receivers by TOE in the All split."""
    allsplit = c4[c4["split"] == "All"].copy()
    ranked = allsplit[allsplit["meets_minimum"]]
    if ranked.empty:   # fixtures / no one meets the minimum: fall back to everyone
        ranked = allsplit
    over = ranked.sort_values("toe", ascending=False).head(5)
    ign = ranked.sort_values("toe", ascending=True).head(5)
    print("=== top-5 over-targeted (All split, by TOE) ===")
    for _, r in over.iterrows():
        print(f"  {r['displayName']:<24} {r['team']:<4} toe={r['toe']:+.2f} "
              f"routes={int(r['routes'])}")
    print("=== top-5 open but ignored (All split, by TOE) ===")
    for _, r in ign.iterrows():
        print(f"  {r['displayName']:<24} {r['team']:<4} toe={r['toe']:+.2f} "
              f"routes={int(r['routes'])}")


# ---------------------------------------------------------------------------
# Stage entry point.

def build(cfg):
    """Build and validate C3-C6 for the configured games; write parquet to Derived_Dir."""
    c1, c2 = _load_inputs(cfg)
    names = _player_names(cfg)
    pos_groups = _position_groups(c1)

    feats = features.build_route_features(c1, c2, cfg)
    print(f"features: {len(feats):,} routes over "
          f"{feats[PLAY_KEY].drop_duplicates().shape[0]:,} model plays")
    print(f"features: no-defender routes pre={feats.attrs.get('n_no_defender_pre')} "
          f"rel={feats.attrs.get('n_no_defender_rel')}  "
          f"no-rusher plays={feats.attrs.get('n_no_rusher')}")

    feats = model.add_xtarget(feats, cfg)

    out_dir = cfg.derived_dir / "fixtures" if cfg.fixtures else cfg.derived_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- C3 + C4 (P0: always written and validated). ---
    c3 = _build_c3(feats, c2, names, pos_groups, cfg)
    cm.validate_c3(c3)
    c3.to_parquet(out_dir / cm.C3_FILE, index=False)
    print(f"C3 Route_Features_Table: {len(c3):,} rows -> {out_dir / cm.C3_FILE}")

    c4 = _build_c4(c3, cfg)
    cm.validate_c4(c4)
    c4.to_parquet(out_dir / cm.C4_FILE, index=False)
    print(f"C4 Receiver_TOE_Table: {len(c4):,} rows -> {out_dir / cm.C4_FILE}")

    _report_route_quartiles(c4)
    _report_headline(c4)

    # --- C5 + C6 (P1: must not take down C3/C4 if they fail). ---
    try:
        c5a, c5b = _build_c5(c3, cfg)
        cm.validate_c5a(c5a)
        cm.validate_c5b(c5b)
        c5a.to_parquet(out_dir / cm.C5A_FILE, index=False)
        c5b.to_parquet(out_dir / cm.C5B_FILE, index=False)
        print(f"C5a Offense_Team_Table: {len(c5a)} teams -> {out_dir / cm.C5A_FILE}")
        print(f"C5b Defense_Team_Table: {len(c5b)} teams -> {out_dir / cm.C5B_FILE}")

        c6 = _build_c6(c3)
        cm.validate_c6(c6)
        c6.to_parquet(out_dir / cm.C6_FILE, index=False)
        print(f"C6 Instead_Table: {len(c6):,} ignored-open events -> {out_dir / cm.C6_FILE}")
    except Exception as err:
        print(f"WARNING: C5/C6 (P1) failed, C3/C4 are intact: {err}")
