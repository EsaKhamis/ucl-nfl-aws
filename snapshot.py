"""Events and eligibility for the Data stage (Requirements 3 and 4).

Plain functions only; nothing runs at import time. The C1/C2 build(cfg) is
added later and reuses these.

    frames, errors = collect_event_frames()          # one narrow pass over tracking
    events = classify_plays(load_plays(), frames)    # one row per play in plays.csv
    runners = route_runners(load_plays(), load_scouting(), load_players())
    elig = eligible_receivers(runners, events)

Run `python snapshot.py [--game 2021090900]` to write out/eligible_receivers.parquet
and print the Requirement 3/4 summary.
"""

import argparse
import time

import numpy as np
import pandas as pd

import load

KEYS = ["gameId", "playId"]
RELEASE_EVENTS = ("pass_forward", "autoevent_passforward")
EVENT_COLUMNS = ["gameId", "playId", "frameId", "event"]
FRAME_SECONDS = 0.1
ELIGIBLE_POSITIONS = {"WR": "WR", "TE": "TE", "RB": "RB", "FB": "RB"}  # -> Position_Group
OFFENSE_ROLES = ("Pass", "Pass Route", "Pass Block")


# ---------------------------------------------------------------- Requirement 3

def read_events(game_id):
    """Narrow tracking read for one game: gameId, playId, frameId, event only."""
    return pd.read_csv(
        load.DATA_DIR / "tracking" / f"tracking_{int(game_id)}.csv",
        usecols=EVENT_COLUMNS,
        dtype={"gameId": "int64", "playId": "int64", "frameId": "int64", "event": "object"},
        na_values=["NA"],
    )


def release_frames(tracking):
    """First frameId per (gameId, playId) with event 'pass_forward' or 'autoevent_passforward'."""
    rel = tracking[tracking["event"].isin(RELEASE_EVENTS)]
    return (rel.groupby(KEYS, as_index=False)["frameId"].min()
            .rename(columns={"frameId": "release_frameId"}))


def event_frames(tracking):
    """One row per play present in `tracking` with snap_frameId and release_frameId (NA if absent)."""
    plays = tracking[KEYS].drop_duplicates()
    out = (plays.merge(load.snap_frames(tracking), on=KEYS, how="left")
           .merge(release_frames(tracking), on=KEYS, how="left"))
    for col in ("snap_frameId", "release_frameId"):
        out[col] = out[col].astype("Int64")
    return out


def collect_event_frames(game_ids=None):
    """Loop over tracking files one game at a time and return (frames, errors).

    `game_ids` None means every tracking file. A file that fails to load is
    recorded in `errors` as {gameId, error} and skipped (Requirement 8.5).
    """
    if game_ids is None:
        game_ids = [int(p.stem.split("_")[1]) for p in load.tracking_files()]
    parts, errors = [], []
    for gid in game_ids:
        try:
            parts.append(event_frames(read_events(gid)))
        except Exception as exc:  # keep going; the report lists the failure
            errors.append({"gameId": int(gid), "error": f"{type(exc).__name__}: {exc}"})
    cols = KEYS + ["snap_frameId", "release_frameId"]
    frames = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols)
    return frames[cols], errors


def classify_plays(plays, frames):
    """One row per play in `plays` with event frames, Throw_Play flag and exclusion reason.

    Columns: gameId, playId, passResult, snap_frameId, release_frameId,
    time_to_throw_s, is_throw_play, is_sack, is_scramble, exclusion_reason
    (NA for Throw_Plays; else 'sack', 'scramble', 'other_pass_result',
    'no_tracking', 'no_snap', 'no_release' or 'release_not_after_snap').
    """
    out = plays[KEYS + ["passResult"]].merge(frames, on=KEYS, how="left", indicator=True)
    in_tracking = out.pop("_merge").eq("both").to_numpy()
    snap, rel = out["snap_frameId"], out["release_frameId"]
    candidate = out["passResult"].isin(load.THROW_RESULTS).to_numpy()
    has_snap, has_rel = snap.notna().to_numpy(), rel.notna().to_numpy()
    after = (rel > snap).fillna(False).to_numpy(dtype=bool)

    out["is_throw_play"] = candidate & has_snap & has_rel & after
    out["is_sack"] = out["passResult"].eq("S")
    out["is_scramble"] = out["passResult"].eq("R")
    out["time_to_throw_s"] = np.where(out["is_throw_play"],
                                      (rel - snap).astype("float64") * FRAME_SECONDS, np.nan)
    out["time_to_throw_s"] = out["time_to_throw_s"].round(1)
    reason = np.select(
        [out["is_throw_play"], out["is_sack"], out["is_scramble"], ~candidate,
         ~in_tracking, ~has_snap, ~has_rel, ~after],
        [None, "sack", "scramble", "other_pass_result",
         "no_tracking", "no_snap", "no_release", "release_not_after_snap"],
        default=None,
    )
    out["exclusion_reason"] = pd.Series(reason, index=out.index, dtype="object")
    return out[KEYS + ["passResult", "snap_frameId", "release_frameId", "time_to_throw_s",
                       "is_throw_play", "is_sack", "is_scramble", "exclusion_reason"]]


def add_line_to_gain_x(plays):
    """Return a copy of plays (with los_x from load.add_los_x) plus line_to_gain_x = los_x + yardsToGo."""
    return plays.assign(line_to_gain_x=plays["los_x"] + plays["yardsToGo"])


def events_report(events, errors=()):
    """Data_Report fragment for Requirements 3.4, 3.5 and 3.6."""
    throws = events[events["is_throw_play"]]
    cand = events[events["passResult"].isin(load.THROW_RESULTS)]
    excluded = cand[~cand["is_throw_play"]]
    ttt = throws["time_to_throw_s"]
    return {
        "plays": int(len(events)),
        "passResult_counts": {k: int(v) for k, v in events["passResult"].value_counts().items()},
        "candidates_C_I_IN": int(len(cand)),
        "throw_plays": int(len(throws)),
        "exclusion_reasons": {k: int(v) for k, v in
                              events["exclusion_reason"].value_counts().items()},
        "excluded_C_I_IN": [{"gameId": int(r.gameId), "playId": int(r.playId),
                             "passResult": r.passResult, "reason": r.exclusion_reason}
                            for r in excluded.itertuples()],
        "sack_plays_excluded": int(events["is_sack"].sum()),
        "scramble_plays_excluded": int(events["is_scramble"].sum()),
        "C_I_IN_without_release": int(cand["release_frameId"].isna().sum()),
        "S_R_with_release": int(events.loc[events["is_sack"] | events["is_scramble"],
                                           "release_frameId"].notna().sum()),
        "release_after_snap_all_throws": bool((throws["release_frameId"]
                                               > throws["snap_frameId"]).all()),
        "time_to_throw_s": {
            "min": float(ttt.min()), "median": float(ttt.median()), "max": float(ttt.max()),
            "n_under_0_5": int((ttt < 0.5).sum()), "n_over_10": int((ttt > 10).sum()),
        },
        "tracking_load_errors": list(errors),
    }


# ---------------------------------------------------------------- Requirement 4

def route_runners(plays, scouting, players, roster=None):
    """Every pff_role 'Pass Route' row with its position and an is_eligible flag.

    Eligible_Receiver = 'Pass Route' AND officialPosition in WR/TE/RB/FB AND on
    the possessionTeam. Scouting has no team column; Pass Route is an
    offense-only role, so role + position is the rule. When `roster`
    (gameId, playId, nflId, team from tracking) is given, team == possessionTeam
    is also required. position_group maps FB to RB.
    """
    pr = scouting.loc[scouting["pff_role"].eq("Pass Route"), KEYS + ["nflId", "pff_role"]]
    pr = (pr.merge(players[["nflId", "displayName", "officialPosition"]], on="nflId", how="left")
          .merge(plays[KEYS + ["possessionTeam"]], on=KEYS))
    pr["position_ok"] = pr["officialPosition"].isin(ELIGIBLE_POSITIONS.keys())
    pr["is_eligible"] = pr["position_ok"]
    if roster is not None:
        pr = pr.merge(roster[KEYS + ["nflId", "team"]].drop_duplicates(), on=KEYS + ["nflId"],
                      how="left")
        pr["is_eligible"] &= pr["team"].eq(pr["possessionTeam"])
    pr["position_group"] = pr["officialPosition"].map(ELIGIBLE_POSITIONS).where(pr["is_eligible"])
    return pr


def eligible_receivers(runners, events):
    """One row per Eligible_Receiver per Throw_Play."""
    throws = events.loc[events["is_throw_play"], KEYS]
    elig = runners[runners["is_eligible"]].merge(throws, on=KEYS)
    elig = elig[KEYS + ["nflId", "displayName", "officialPosition", "position_group"]]
    return elig.sort_values(KEYS + ["nflId"]).reset_index(drop=True)


def n_eligible(events, elig):
    """Series aligned to `events`: Eligible_Receivers per Throw_Play (NA on other plays)."""
    counts = elig.groupby(KEYS).size().rename("n")
    n = events[KEYS].merge(counts, left_on=KEYS, right_index=True, how="left")["n"]
    n = n.fillna(0).astype("Int64").where(events["is_throw_play"].to_numpy())
    return pd.Series(n.to_numpy(), index=events.index, dtype="Int64")


def tracking_roster(game_id):
    """(gameId, playId, nflId, team) for the players (not the ball) in one game's tracking."""
    trk = pd.read_csv(load.DATA_DIR / "tracking" / f"tracking_{int(game_id)}.csv",
                      usecols=KEYS + ["nflId", "team"], dtype={"nflId": "Int64"},
                      na_values=["NA"])
    return trk[trk["team"].ne("football")].drop_duplicates().reset_index(drop=True)


def team_cross_check(game_id, plays, scouting):
    """Compare scouting offense roles with tracking team == possessionTeam on one game."""
    roster = tracking_roster(game_id).merge(plays[KEYS + ["possessionTeam"]], on=KEYS)
    sc = scouting.loc[scouting["gameId"].eq(game_id), KEYS + ["nflId", "pff_role"]]
    m = sc.merge(roster, on=KEYS + ["nflId"], how="outer", indicator=True)
    on_off = m["team"].eq(m["possessionTeam"])
    off_role = m["pff_role"].isin(OFFENSE_ROLES)
    both = m["_merge"].eq("both")
    route = m["pff_role"].eq("Pass Route")
    return {
        "gameId": int(game_id),
        "scouting_rows": int(len(sc)),
        "tracking_players": int(len(roster)),
        "only_in_scouting": int(m["_merge"].eq("left_only").sum()),
        "only_in_tracking": int(m["_merge"].eq("right_only").sum()),
        "pass_route_rows": int(route.sum()),
        "pass_route_not_on_possession_team": int((both & route & ~on_off).sum()),
        "offense_role_not_on_possession_team": int((both & off_role & ~on_off).sum()),
        "defense_role_on_possession_team": int((both & ~off_role & on_off).sum()),
    }


def eligibility_report(runners, events, elig):
    """Data_Report fragment for Requirements 4.3 and 4.4."""
    throws = events.loc[events["is_throw_play"], KEYS]
    on_throws = runners.merge(throws, on=KEYS)
    other_throw = on_throws[~on_throws["position_ok"]]
    other_all = runners[~runners["position_ok"]]
    n = n_eligible(events, elig)[events["is_throw_play"].to_numpy()]
    return {
        "eligible_routes": int(len(elig)),
        "position_group_counts": {k: int(v) for k, v in
                                  elig["position_group"].value_counts().items()},
        "n_eligible": {"min": int(n.min()), "median": float(n.median()), "max": int(n.max()),
                       "distribution": {str(k): int(v) for k, v in
                                        n.value_counts().sort_index().items()}},
        "pass_route_other_position_on_throw_plays": {
            "count": int(len(other_throw)),
            "by_position": {str(k): int(v) for k, v in
                            other_throw["officialPosition"].value_counts(dropna=False).items()},
        },
        "pass_route_other_position_all_plays": {
            "count": int(len(other_all)),
            "by_position": {str(k): int(v) for k, v in
                            other_all["officialPosition"].value_counts(dropna=False).items()},
        },
    }


# ---------------------------------------------------------------- C1 / C2 (Req 6, 7, 8)

OFFSETS = range(0, 6)
C1_COLUMNS = KEYS + ["offset", "frameId", "clamped", "nflId", "is_ball", "side", "pff_role",
                     "position_group", "is_eligible", "x", "y", "s", "a", "o", "dir"]


def read_tracking(game_id):
    """One game's tracking, Appendix A columns only, standardized (Req 2)."""
    df = pd.read_csv(load.DATA_DIR / "tracking" / f"tracking_{int(game_id)}.csv",
                     usecols=load.REQUIRED_COLUMNS["tracking"],
                     dtype={"gameId": "int64", "playId": "int64", "nflId": "Int64",
                            "frameId": "int64", "event": "object"},
                     na_values=["NA"])
    return load.standardize(df)


def snapshot_frames(events):
    """(gameId, playId, offset, frameId, clamped) for each Throw_Play and offset 0-5.

    frameId = max(release - offset, snap); clamped = release - offset < snap.
    """
    th = events.loc[events["is_throw_play"], KEYS + ["snap_frameId", "release_frameId"]]
    parts = []
    for off in OFFSETS:
        want = th["release_frameId"].astype("int64") - off
        snap = th["snap_frameId"].astype("int64")
        parts.append(pd.DataFrame({"gameId": th["gameId"].to_numpy(),
                                   "playId": th["playId"].to_numpy(), "offset": off,
                                   "frameId": np.maximum(want, snap).to_numpy(),
                                   "clamped": (want < snap).to_numpy()}))
    return pd.concat(parts, ignore_index=True)


def snapshot_rows(tracking, events, plays):
    """Standardized tracking rows at each snapshot frame, with is_ball and side."""
    rows = snapshot_frames(events).merge(tracking, on=KEYS + ["frameId"])
    rows = rows.merge(plays[KEYS + ["possessionTeam"]], on=KEYS)
    rows["is_ball"] = rows["team"].eq("football")
    rows["side"] = np.where(rows["is_ball"], "ball",
                            np.where(rows["team"].eq(rows["possessionTeam"]),
                                     "offense", "defense"))
    return rows


def scan_tracking(plays, game_ids):
    """One pass over tracking: event frames, rosters, play directions and snapshot rows."""
    frames, rosters, dirs, snaps, errors = [], [], [], [], []
    for gid in game_ids:
        try:
            trk = read_tracking(gid)
        except Exception as exc:  # Req 8.5: record and continue
            errors.append({"gameId": int(gid), "error": f"{type(exc).__name__}: {exc}"})
            continue
        fr = event_frames(trk)
        frames.append(fr)
        rosters.append(trk.loc[trk["team"].ne("football"), KEYS + ["nflId", "team"]]
                       .drop_duplicates())
        dirs.append(trk.groupby(KEYS, as_index=False)["playDirection"].first())
        pg = plays[plays["gameId"].eq(gid)]
        snaps.append(snapshot_rows(trk, classify_plays(pg, fr), pg))
    cat = lambda xs: pd.concat(xs, ignore_index=True)  # noqa: E731
    return cat(frames), cat(rosters), cat(dirs), cat(snaps), errors


def finish_c1(rows, scouting, elig):
    """Add pff_role, position_group and is_eligible; return C1 columns and types."""
    c1 = rows.merge(scouting[KEYS + ["nflId", "pff_role"]], on=KEYS + ["nflId"], how="left")
    c1 = c1.merge(elig[KEYS + ["nflId", "position_group"]], on=KEYS + ["nflId"], how="left")
    c1["is_eligible"] = c1["position_group"].notna()
    c1.loc[c1["is_ball"], ["o", "dir"]] = np.nan
    c1 = c1[C1_COLUMNS].sort_values(KEYS + ["offset", "nflId"]).reset_index(drop=True)
    c1["pff_role"] = c1["pff_role"].astype("object").where(c1["pff_role"].notna(), None)
    return c1


def frame_count_issues(c1):
    """Req 6.5: snapshot frames whose player count is not 22 or ball count is not 1."""
    g = c1.groupby(KEYS + ["offset"])
    counts = pd.DataFrame({"players": g["is_ball"].apply(lambda b: int((~b).sum())),
                           "balls": g["is_ball"].sum().astype(int)}).reset_index()
    bad = counts[(counts["players"] != 22) | (counts["balls"] != 1)]
    return {"frames_checked": int(len(counts)), "frames_flagged": int(len(bad)),
            "plays_flagged": int(bad[KEYS].drop_duplicates().shape[0]),
            "player_count_distribution": {str(k): int(v) for k, v in
                                          counts["players"].value_counts().sort_index().items()},
            "flagged": bad.head(200).to_dict("records")}


def build_c1(cfg):
    """C1 for cfg.games (None = every tracking file), plus what C2 needs from the same pass.

    Returns a dict: c1, events (classify_plays for the processed plays), elig
    (Eligible_Receivers, team-checked against tracking), runners, directions
    (gameId, playId, playDirection; feed to load.add_los_x), errors and
    frame_counts (Req 6.5).
    """
    t0 = time.time()
    load.DATA_DIR = cfg.data_dir
    game_ids = cfg.games or [int(p.stem.split("_")[1]) for p in load.tracking_files()]
    plays = load.load_plays()
    plays = plays[plays["gameId"].isin(game_ids)].reset_index(drop=True)
    scouting, players = load.load_scouting(), load.load_players()

    frames, roster, directions, rows, errors = scan_tracking(plays, game_ids)
    events = classify_plays(plays, frames)
    runners = route_runners(plays, scouting, players, roster=roster)
    elig = eligible_receivers(runners, events)
    c1 = finish_c1(rows, scouting, elig)
    return {"c1": c1, "events": events, "elig": elig, "runners": runners,
            "directions": directions, "errors": errors, "plays": plays,
            "frame_counts": frame_count_issues(c1), "runtime_s": round(time.time() - t0, 1)}


def write_c1(cfg, c1):
    """Validate C1 against the contract and write out/c1_snapshot.parquet."""
    import contracts_data

    contracts_data.validate_c1(c1)
    cfg.derived_dir.mkdir(parents=True, exist_ok=True)
    path = cfg.derived_dir / contracts_data.C1_FILE
    c1.to_parquet(path, index=False)
    return path


def build(cfg):
    """Data stage: write C1, then C2 via play_table.build_c2."""
    import play_table

    parts = build_c1(cfg)
    path = write_c1(cfg, parts["c1"])
    print(f"wrote {path} ({len(parts['c1'])} rows) in {parts['runtime_s']}s")
    play_table.build_c2(cfg, events=parts["events"], elig=parts["elig"],
                        directions=parts["directions"])


if __name__ == "__main__":
    import json

    ap = argparse.ArgumentParser(description="Events and eligibility (Req 3, 4).")
    ap.add_argument("--game", type=int, help="one gameId for the prototype run")
    args = ap.parse_args()

    t0 = time.time()
    plays = load.load_plays()
    if args.game:
        plays = plays[plays["gameId"].eq(args.game)]
    frames, errors = collect_event_frames([args.game] if args.game else None)
    events = classify_plays(plays, frames)
    runners = route_runners(plays, load.load_scouting(), load.load_players())
    elig = eligible_receivers(runners, events)
    load.OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = load.OUT_DIR / "eligible_receivers.parquet"
    elig.to_parquet(path, index=False)
    print(json.dumps({"req_3": {k: v for k, v in events_report(events, errors).items()
                                if k != "excluded_C_I_IN"},
                      "req_4": eligibility_report(runners, events, elig)}, indent=2))
    print(f"wrote {path} ({len(elig)} rows) in {time.time() - t0:.1f}s")
