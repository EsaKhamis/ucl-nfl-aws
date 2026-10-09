"""Build the C2 Play_Table: one row of context per Throw_Play (Requirement 7).

    c2 = build_c2(load.load_plays(), load.load_games(), load.load_scouting(),
                  load.load_players(), game_ids=[2021090900])

Run `python play_table.py [--game 2021090900]` to validate and write
out/c2_plays.parquet (default: every tracking file).

Reuses load.add_los_x, snapshot (events, eligibility, line to gain) and
targets.assign_targets. When snapshot.build calls build_c2(cfg, events=...,
elig=..., directions=...) the tables from its C1 pass are reused and the
file is written to cfg.derived_dir.
"""

import argparse
import json
import time

import numpy as np
import pandas as pd

import contracts_data
import load
import snapshot
import targets
from config import Config

KEYS = ["gameId", "playId"]
# One narrow tracking read gives event frames, play direction (los_x) and the
# roster for the Eligible_Receiver team check.
TRACKING_COLUMNS = ["gameId", "playId", "nflId", "frameId", "team", "playDirection", "event"]
PRESSURE_FLAGS = ["pff_hit", "pff_hurry", "pff_sack"]
PLAY_COLUMNS = ["possessionTeam", "defensiveTeam", "quarter", "down", "yardsToGo", "gameClock",
                "preSnapHomeScore", "preSnapVisitorScore", "absoluteYardlineNumber",
                "pff_passCoverage", "pff_passCoverageType", "pff_playAction", "dropBackType",
                "yardlineSide", "yardlineNumber"]


def scan_tracking(game_ids):
    """One narrow pass over tracking: (frames, directions, roster, errors).

    frames: snapshot.event_frames per play; directions: (gameId, playId,
    playDirection); roster: (gameId, playId, nflId, team) for players. A file
    that fails to load is recorded in errors and skipped (Req 8.5).
    """
    frames, directions, rosters, errors = [], [], [], []
    for gid in game_ids:
        try:
            trk = pd.read_csv(load.DATA_DIR / "tracking" / f"tracking_{int(gid)}.csv",
                              usecols=TRACKING_COLUMNS, na_values=["NA"],
                              dtype={"gameId": "int64", "playId": "int64", "nflId": "Int64",
                                     "frameId": "int64", "event": "object"})
        except Exception as exc:  # keep going; the report lists the failure
            errors.append({"gameId": int(gid), "error": f"{type(exc).__name__}: {exc}"})
            continue
        frames.append(snapshot.event_frames(trk))
        directions.append(trk.groupby(KEYS, as_index=False)["playDirection"].first())
        rosters.append(trk.loc[trk["team"].ne("football"), KEYS + ["nflId", "team"]]
                       .drop_duplicates())
    cat = lambda xs, cols: (pd.concat(xs, ignore_index=True) if xs  # noqa: E731
                            else pd.DataFrame(columns=cols))
    return (cat(frames, KEYS + ["snap_frameId", "release_frameId"]),
            cat(directions, KEYS + ["playDirection"]),
            cat(rosters, KEYS + ["nflId", "team"]), errors)


def qb_per_play(scouting):
    """(gameId, playId, n_qb, qb_nflId): qb_nflId is the pff_role 'Pass' player when exactly one."""
    qb = scouting.loc[scouting["pff_role"].eq("Pass"), KEYS + ["nflId"]]
    g = qb.groupby(KEYS)["nflId"].agg(n_qb="size", qb_nflId="first").reset_index()
    g["qb_nflId"] = g["qb_nflId"].astype("Int64").where(g["n_qb"].eq(1))
    return g


def pressured_per_play(scouting):
    """(gameId, playId, pressured): any scouting row with pff_hit, pff_hurry or pff_sack == 1."""
    flag = scouting[PRESSURE_FLAGS].eq(1).fillna(False).any(axis=1)
    return (flag.groupby([scouting["gameId"], scouting["playId"]]).any()
            .rename("pressured").reset_index())


def fill_los_x(df):
    """Fill missing los_x (absoluteYardlineNumber NA) from yardlineSide/yardlineNumber.

    In standardized coordinates the offense moves toward +x, so LOS_x is
    10 + yardlineNumber in its own half and 110 - yardlineNumber otherwise.
    This reproduces add_los_x on all 8,556 plays that have absoluteYardlineNumber;
    plays.csv has one NA (2021091904/3676, ball at 70.66 at the snap -> 71).
    """
    own = df["yardlineSide"].eq(df["possessionTeam"]).to_numpy()
    derived = np.where(own, 10.0 + df["yardlineNumber"], 110.0 - df["yardlineNumber"])
    return df.assign(los_x=df["los_x"].fillna(pd.Series(derived, index=df.index)))


def score_margin(df):
    """possessionTeam pre-snap score minus defensiveTeam's, with homeTeamAbbr from games.csv."""
    home = df["possessionTeam"].eq(df["homeTeamAbbr"]).to_numpy()
    diff = (df["preSnapHomeScore"] - df["preSnapVisitorScore"]).to_numpy()
    return np.where(home, diff, -diff).astype("int64")


def build_c2(plays, games=None, scouting=None, players=None, game_ids=None, *,
             events=None, elig=None, directions=None, report=None):
    """C2 Play_Table (Contract C2 columns, order and types) for the Throw_Plays in `plays`.

    game_ids None means every tracking file. events/elig/directions skip the
    tracking pass when the caller already has them (snapshot.build). If
    `report` is a dict it is filled with the Data_Report counts for C2.
    If `plays` is a Config (snapshot.build), loads the tables itself and also
    validates and writes cfg.derived_dir/c2_plays.parquet.
    """
    if isinstance(plays, Config):
        return _build_from_cfg(plays, events=events, elig=elig, directions=directions)

    t0 = time.time()
    if game_ids is None:
        game_ids = [int(p.stem.split("_")[1]) for p in load.tracking_files()]
    plays = plays[plays["gameId"].isin(game_ids)].reset_index(drop=True)
    scouting = scouting[scouting["gameId"].isin(game_ids)]
    errors = []
    if events is None or elig is None or directions is None:
        frames, directions, roster, errors = scan_tracking(game_ids)
        events = snapshot.classify_plays(plays, frames)
        runners = snapshot.route_runners(plays, scouting, players, roster=roster)
        elig = snapshot.eligible_receivers(runners, events)

    tbl, req5 = targets.assign_targets(events, plays, scouting, players, elig)
    throws = tbl.loc[tbl["is_throw_play"], KEYS + [
        "passResult", "snap_frameId", "release_frameId", "time_to_throw_s", "n_eligible",
        "target_nflId", "target_source", "is_model_play"]]

    ctx = load.add_los_x(plays[KEYS + PLAY_COLUMNS], directions)
    n_los_filled = int((ctx["los_x"].isna() & ctx["absoluteYardlineNumber"].isna()).sum())
    ctx = snapshot.add_line_to_gain_x(fill_los_x(ctx))
    ctx = ctx.merge(games[["gameId", "week", "homeTeamAbbr", "visitorTeamAbbr"]],
                    on="gameId", how="left")
    c2 = (throws.merge(ctx, on=KEYS, how="left")
          .merge(qb_per_play(scouting), on=KEYS, how="left")
          .merge(pressured_per_play(scouting), on=KEYS, how="left")
          .sort_values(KEYS).reset_index(drop=True))
    c2["score_margin"] = score_margin(c2)
    c2["pressured"] = c2["pressured"].fillna(False).astype(bool)
    c2["is_model_play"] = c2["is_model_play"].astype(bool)
    c2["n_eligible"] = c2["n_eligible"].astype("Int64")
    c2["qb_nflId"] = c2["qb_nflId"].astype("Int64")
    c2["week"] = c2["week"].astype("int64")
    n_qb = c2["n_qb"].fillna(0).astype(int)
    team_ok = (c2["possessionTeam"].eq(c2["homeTeamAbbr"])
               | c2["possessionTeam"].eq(c2["visitorTeamAbbr"]))
    c2 = c2[list(contracts_data.C2_SCHEMA)]

    if report is not None:
        sc_keys = scouting[KEYS].drop_duplicates()
        no_scouting = len(c2) - len(c2[KEYS].merge(sc_keys, on=KEYS))
        report.update({
            "games": len(game_ids),
            "throw_plays": int(len(c2)),
            "model_plays": int(c2["is_model_play"].sum()),
            "match_rate": req5["match_rate"],
            "match_status_counts": req5["match_status_counts"],
            "qb_count_per_play": {str(k): int(v) for k, v in n_qb.value_counts().sort_index()
                                  .items()},
            "qb_exceptions": c2.loc[(n_qb != 1).to_numpy(), KEYS].to_dict("records"),
            "pressured_share": round(float(c2["pressured"].mean()), 4) if len(c2) else None,
            "plays_without_scouting": int(no_scouting),
            "possessionTeam_not_home_or_visitor": int((~team_ok).sum()),
            "plays_los_x_from_yardline": n_los_filled,
            "tracking_load_errors": errors,
            "runtime_s": round(time.time() - t0, 1),
        })
    return c2


def write_c2(c2, out_dir):
    """Validate against Contract C2 and write out_dir/c2_plays.parquet."""
    contracts_data.validate_c2(c2)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / contracts_data.C2_FILE
    c2.to_parquet(path, index=False)
    return path


def _build_from_cfg(cfg, events=None, elig=None, directions=None):
    """snapshot.build entry point: build, validate and write C2 for cfg.games."""
    load.DATA_DIR = cfg.data_dir
    report = {}
    c2 = build_c2(load.load_plays(), load.load_games(), load.load_scouting(),
                  load.load_players(), cfg.games, events=events, elig=elig,
                  directions=directions, report=report)
    path = write_c2(c2, cfg.derived_dir)
    print(f"wrote {path} ({len(c2)} rows, {report['model_plays']} Model_Plays) "
          f"in {report['runtime_s']}s")
    return c2


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="C2 Play_Table (Req 7).")
    ap.add_argument("--game", type=int, help="one gameId for the prototype run")
    args = ap.parse_args()

    t0 = time.time()
    report = {}
    c2 = build_c2(load.load_plays(), load.load_games(), load.load_scouting(),
                  load.load_players(), [args.game] if args.game else None, report=report)
    path = write_c2(c2, load.OUT_DIR)
    print(json.dumps({k: v for k, v in report.items() if k != "qb_exceptions"}, indent=2))
    print(f"qb exceptions (n_qb != 1): {report['qb_exceptions'][:20]}")
    print(f"wrote {path} ({len(c2)} rows) in {time.time() - t0:.1f}s")
