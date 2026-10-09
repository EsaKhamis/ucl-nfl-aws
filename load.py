"""Load the Big Data Bowl 2023 tables and standardize tracking play direction.

Usage:
    from load import load_plays, load_tracking, standardize, add_los_x
    trk = load_tracking(2021090900, standardize=True)
    plays = add_los_x(load_plays(), trk)

Nothing is loaded at import time. Set NFL_DATA_DIR / NFL_OUT_DIR /
NFL_RESULTS_DIR to point at different folders (defaults: ./data, ./out and
./results next to this file).
"""

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(os.environ.get("NFL_DATA_DIR", Path(__file__).parent / "data"))
OUT_DIR = Path(os.environ.get("NFL_OUT_DIR", Path(__file__).parent / "out"))  # Derived_Dir
RESULTS_DIR = Path(os.environ.get("NFL_RESULTS_DIR", Path(__file__).parent / "results"))  # Outputs_Dir

# Field dimensions in yards (x includes both 10-yard end zones).
FIELD_LENGTH = 120.0
FIELD_WIDTH = 53.3

# Appendix A of the requirements: columns each source file must have.
REQUIRED_COLUMNS = {
    "games.csv": ["gameId", "season", "week", "homeTeamAbbr", "visitorTeamAbbr"],
    "plays.csv": [
        "gameId", "playId", "playDescription", "quarter", "down", "yardsToGo",
        "possessionTeam", "defensiveTeam", "gameClock", "preSnapHomeScore",
        "preSnapVisitorScore", "passResult", "playResult", "absoluteYardlineNumber",
        "dropBackType", "pff_playAction", "pff_passCoverage", "pff_passCoverageType",
    ],
    "players.csv": ["nflId", "officialPosition", "displayName"],
    "pffScoutingData.csv": [
        "gameId", "playId", "nflId", "pff_role", "pff_positionLinedUp",
        "pff_hit", "pff_hurry", "pff_sack",
    ],
    "tracking": [
        "gameId", "playId", "nflId", "frameId", "team", "playDirection",
        "x", "y", "s", "a", "o", "dir", "event",
    ],
}

# Counts in our copy of the dataset (Requirement 1.6).
REFERENCE_COUNTS = {"games": 122, "plays": 8557, "players": 1679, "tracking_files": 122}

SNAP_EVENTS = ("ball_snap", "autoevent_ballsnap")
BALL_LOS_TOLERANCE = 2.5   # yards (Requirement 2.7, amended 10:30)
BALL_LOS_INFO_TOLERANCE = 1.5  # yards, reported for information only
DIRECTION_MIN_SHARE = 0.99  # Requirements 2.7 and 2.8
THROW_RESULTS = ("C", "I", "IN")


def _read_csv(path, schema_key, dtype=None):
    """Read a source CSV with "NA" as missing and check the Appendix A columns."""
    df = pd.read_csv(path, dtype=dtype, na_values=["NA"])
    missing = [c for c in REQUIRED_COLUMNS[schema_key] if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name} is missing required columns: {', '.join(missing)}")
    return df


def _strip_strings(df):
    """Strip leading/trailing whitespace from string (object) columns."""
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip()
    return df


def load_games():
    """One row per game."""
    df = _read_csv(DATA_DIR / "games.csv", "games.csv", dtype={"gameId": "int64"})
    return _strip_strings(df)


def load_plays():
    """One row per pass play. Keyed on (gameId, playId)."""
    df = _read_csv(
        DATA_DIR / "plays.csv",
        "plays.csv",
        dtype={
            "gameId": "int64",
            "playId": "int64",
            "penaltyYards": "Int64",
            "foulNFLId1": "Int64",
            "foulNFLId2": "Int64",
            "foulNFLId3": "Int64",
            "defendersInBox": "Int64",
        },
    )
    return _strip_strings(df)


def load_players():
    """One row per player. Keyed on nflId."""
    df = _read_csv(DATA_DIR / "players.csv", "players.csv", dtype={"nflId": "Int64"})
    return _strip_strings(df)


def load_scouting():
    """PFF scouting: one row per player per play. Keyed on (gameId, playId, nflId)."""
    flag_cols = [
        "pff_hit", "pff_hurry", "pff_sack", "pff_beatenByDefender",
        "pff_hitAllowed", "pff_hurryAllowed", "pff_sackAllowed",
        "pff_backFieldBlock",
    ]
    dtype = {"gameId": "int64", "playId": "int64", "nflId": "Int64",
             "pff_nflIdBlockedPlayer": "Int64"}
    dtype.update({c: "Int64" for c in flag_cols})
    df = _read_csv(DATA_DIR / "pffScoutingData.csv", "pffScoutingData.csv", dtype=dtype)
    return _strip_strings(df)


def tracking_files():
    """Sorted list of tracking CSVs found in DATA_DIR/tracking."""
    return sorted((DATA_DIR / "tracking").glob("tracking_*.csv"))


def load_tracking(game_id, standardize=False):
    """Tracking for one game: one row per player (or ball) per 0.1 s frame.

    The ball row has team == 'football', nflId/jerseyNumber NA and NaN o/dir.
    `event` is NaN on frames without an event (the CSV writes 'None').
    """
    df = _read_csv(
        DATA_DIR / "tracking" / f"tracking_{int(game_id)}.csv",
        "tracking",
        dtype={
            "gameId": "int64",
            "playId": "int64",
            "nflId": "Int64",
            "frameId": "int64",
            "jerseyNumber": "Int64",
        },
    )
    if "time" in df:
        df["time"] = pd.to_datetime(df["time"], utc=True)
    if standardize:
        df = _standardize(df)
    return df


def standardize(df):
    """Return a copy of tracking data with offense always moving toward +x.

    For rows with playDirection == 'left':
        x   -> 120 - x
        y   -> 53.3 - y
        o   -> (o + 180) % 360
        dir -> (dir + 180) % 360
    Rows with playDirection == 'right' keep x, y, o and dir, except that a raw
    angle of exactly 360.0 is written as 0.0 (same heading) so every o/dir is
    in [0, 360). NaN o/dir (ball rows) stay NaN. playDirection itself is left
    as-is, so apply this once only: running it twice flips left plays back.

    Angle convention (same for o and dir): degrees clockwise from +y, so
    0 = +y, 90 = +x (downfield after standardizing), 180 = -y, 270 = -x.
        vx = s * sin(radians(dir))
        vy = s * cos(radians(dir))
    """
    out = df.copy()
    left = out["playDirection"].eq("left").to_numpy()
    if "x" in out:
        out["x"] = np.where(left, FIELD_LENGTH - out["x"], out["x"])
    if "y" in out:
        out["y"] = np.where(left, FIELD_WIDTH - out["y"], out["y"])
    for col in ("o", "dir"):
        if col in out:
            out[col] = np.where(left, out[col] + 180, out[col]) % 360
    return out


# load_tracking's `standardize` argument shadows the function name inside it.
_standardize = standardize


def add_los_x(plays, tracking):
    """Return a copy of plays with los_x, the line of scrimmage in standardized x.

    absoluteYardlineNumber is in raw tracking coordinates, so los_x is
    120 - absoluteYardlineNumber on left plays and unchanged on right plays.
    playDirection is taken per (gameId, playId) from `tracking` (raw or
    standardized; any frame with gameId, playId, playDirection works). Plays
    not present in `tracking` get los_x = NaN.
    """
    keys = ["gameId", "playId"]
    direction = tracking.groupby(keys, as_index=False)["playDirection"].first()
    out = plays.merge(direction, on=keys, how="left")
    yardline = out["absoluteYardlineNumber"]
    out["los_x"] = np.where(out["playDirection"].eq("left"), FIELD_LENGTH - yardline,
                            np.where(out["playDirection"].eq("right"), yardline, np.nan))
    return out.drop(columns="playDirection")


def snap_frames(tracking):
    """First frameId per (gameId, playId) with event 'ball_snap' or 'autoevent_ballsnap'."""
    snaps = tracking[tracking["event"].isin(SNAP_EVENTS)]
    return (snaps.groupby(["gameId", "playId"], as_index=False)["frameId"].min()
            .rename(columns={"frameId": "snap_frameId"}))


def direction_check(tracking, plays):
    """Per-play direction checks at the snap frame (Requirements 2.7 and 2.8).

    `tracking` must be standardized; `plays` must have los_x (see add_los_x).
    Returns one row per play with ball_x, offense_x, defense_x (mean x),
    ball_near_los (|ball_x - los_x| <= 2.5), ball_within_1_5 (info only)
    and sides_split (offense_x < los_x < defense_x).
    """
    keys = ["gameId", "playId"]
    f = tracking.merge(snap_frames(tracking), on=keys)
    f = f[f["frameId"] == f["snap_frameId"]]
    f = f.merge(plays[keys + ["possessionTeam", "passResult", "los_x"]], on=keys)
    f["side"] = np.where(f["team"].eq("football"), "ball",
                         np.where(f["team"].eq(f["possessionTeam"]), "offense", "defense"))
    mean_x = f.groupby(keys + ["side"])["x"].mean().unstack("side")
    per_play = (f.groupby(keys)[["passResult", "los_x", "snap_frameId"]].first()
                .join(mean_x.rename(columns=lambda s: f"{s}_x")).reset_index())
    gap = (per_play["ball_x"] - per_play["los_x"]).abs()
    per_play["ball_near_los"] = gap <= BALL_LOS_TOLERANCE
    per_play["ball_within_1_5"] = gap <= BALL_LOS_INFO_TOLERANCE
    per_play["sides_split"] = ((per_play["offense_x"] < per_play["los_x"])
                               & (per_play["defense_x"] > per_play["los_x"]))
    return per_play


def direction_summary(per_play):
    """Shares from direction_check() for all plays and the C/I/IN subset; warns below 99%."""
    summary = {}
    subsets = {"all_plays": per_play,
               "passResult_C_I_IN": per_play[per_play["passResult"].isin(THROW_RESULTS)]}
    for name, sub in subsets.items():
        summary[name] = {
            "n_plays": int(len(sub)),
            "ball_near_los_share": round(float(sub["ball_near_los"].mean()), 4),
            "sides_split_share": round(float(sub["sides_split"].mean()), 4),
            "ball_within_1_5_share_info": round(float(sub["ball_within_1_5"].mean()), 4),
        }
        for check in ("ball_near_los_share", "sides_split_share"):
            if summary[name][check] < DIRECTION_MIN_SHARE:
                print(f"WARNING: {name} {check} = {summary[name][check]:.4f} "
                      f"(< {DIRECTION_MIN_SHARE})")
    return summary


def build_data_report(games, plays, players, scouting):
    """Data_Report counts (Requirement 1.5). Prints one warning if any differ from reference."""
    report = {"counts": {
        "games": int(len(games)),
        "plays": int(len(plays)),
        "players": int(len(players)),
        "scouting_rows": int(len(scouting)),
        "tracking_files": len(tracking_files()),
    }}
    diffs = [f"{k}: found {report['counts'][k]}, expected {v}"
             for k, v in REFERENCE_COUNTS.items() if report["counts"][k] != v]
    if diffs:
        print("WARNING: counts differ from the reference copy: " + "; ".join(diffs))
    report["count_differences"] = diffs
    return report


def write_data_report(report, path=None):
    """Write the Data_Report dict as JSON (default RESULTS_DIR/data_report.json)."""
    path = Path(path) if path else RESULTS_DIR / "data_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    return path


if __name__ == "__main__":
    game_id = 2021090900
    games = load_games()
    plays = load_plays()
    players = load_players()
    scouting = load_scouting()
    report = build_data_report(games, plays, players, scouting)

    tracking = load_tracking(game_id, standardize=True)
    game_plays = add_los_x(plays[plays["gameId"] == game_id], tracking)
    report["direction_check"] = {"games": [game_id],
                                 **direction_summary(direction_check(tracking, game_plays))}

    for name, table in [("games", games), ("plays", plays), ("players", players),
                        ("scouting", scouting), (f"tracking {game_id}", tracking)]:
        print(f"{name:<20} {table.shape}")
    print("direction check:", json.dumps(report["direction_check"]))
    print("wrote", write_data_report(report))
