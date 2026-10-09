"""Contract tooling for the Data tables: validate(), the C1/C2 schemas and fixtures.

A schema is {column: (kind, nullable, allowed_values_or_None)} with kind one of
"int", "float", "str", "bool". validate() collects every violation and raises
one ValueError listing all of them (Req 9.1, 9.2).

    from contracts_data import validate_c1, validate_c2
    c1 = validate_c1(pd.read_parquet("out/c1_snapshot.parquet"))

Nullable int columns must use pandas "Int64" (a float64 nflId is rejected).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

C1_FILE = "c1_snapshot.parquet"
C2_FILE = "c2_plays.parquet"
POSITION_GROUPS = {"WR", "TE", "RB"}

# Contract C1 Snapshot_Table: one row per player or ball, per Throw_Play, per offset 0-5.
C1_SCHEMA = {
    "gameId": ("int", False, None),
    "playId": ("int", False, None),
    "offset": ("int", False, {0, 1, 2, 3, 4, 5}),
    "frameId": ("int", False, None),
    "clamped": ("bool", False, None),
    "nflId": ("int", True, None),
    "is_ball": ("bool", False, None),
    "side": ("str", False, {"offense", "defense", "ball"}),
    "pff_role": ("str", True, None),
    "position_group": ("str", True, POSITION_GROUPS),
    "is_eligible": ("bool", False, None),
    "x": ("float", False, None),
    "y": ("float", False, None),
    "s": ("float", False, None),
    "a": ("float", False, None),
    "o": ("float", True, None),
    "dir": ("float", True, None),
}
C1_KEY = ["gameId", "playId", "offset", "nflId"]

# Contract C2 Play_Table: one row per Throw_Play.
C2_SCHEMA = {
    "gameId": ("int", False, None),
    "playId": ("int", False, None),
    "week": ("int", False, None),
    "possessionTeam": ("str", False, None),
    "defensiveTeam": ("str", False, None),
    "quarter": ("int", False, None),
    "down": ("int", False, None),
    "yardsToGo": ("int", False, None),
    "gameClock": ("str", False, None),
    "score_margin": ("int", False, None),
    "los_x": ("float", False, None),
    "line_to_gain_x": ("float", False, None),
    "pff_passCoverage": ("str", True, None),
    "pff_passCoverageType": ("str", True, None),
    "pff_playAction": ("int", False, {0, 1}),
    # Contract says str "as in plays.csv"; plays.csv has 474 Throw_Plays with NA here.
    "dropBackType": ("str", True, None),
    "passResult": ("str", False, None),
    "snap_frameId": ("int", False, None),
    "release_frameId": ("int", False, None),
    "time_to_throw_s": ("float", False, None),
    "qb_nflId": ("int", True, None),
    "pressured": ("bool", False, None),
    "n_eligible": ("int", False, None),
    "target_nflId": ("int", True, None),
    "target_source": ("str", False, {"description", "nflverse", "none"}),
    "is_model_play": ("bool", False, None),
}
C2_KEY = ["gameId", "playId"]


def _kind_ok(series, kind):
    dtype = series.dtype
    if kind == "int":
        return pd.api.types.is_integer_dtype(dtype)      # int64 or nullable Int64
    if kind == "float":
        return pd.api.types.is_float_dtype(dtype)
    if kind == "bool":
        return pd.api.types.is_bool_dtype(dtype)         # bool or nullable boolean
    if kind == "str":
        if dtype == object:
            return bool(series.dropna().map(lambda v: isinstance(v, str)).all())
        return isinstance(dtype, pd.StringDtype)
    raise ValueError(f"unknown schema kind {kind!r}")


def _examples(values, n=3):
    values = list(values)
    more = f" (+{len(values) - n} more)" if len(values) > n else ""
    return ", ".join(repr(v) for v in values[:n]) + more


def validate(df, schema, key, name, checks=()):
    """Check df against a contract; return df, or raise one ValueError listing every violation.

    checks: optional functions df -> list[str] of extra rule violations. A check
    that needs a missing column is skipped (the missing column is already reported).
    """
    errors = []
    missing = [c for c in schema if c not in df.columns]
    if missing:
        errors.append(f"missing columns: {', '.join(missing)}")

    for col, (kind, nullable, allowed) in schema.items():
        if col not in df.columns:
            continue
        series = df[col]
        if not _kind_ok(series, kind):
            hint = " (use Int64 for nullable ints)" if kind == "int" else ""
            errors.append(f"{col}: expected {kind}, got dtype {series.dtype}{hint}")
        n_null = int(series.isna().sum())
        if n_null and not nullable:
            errors.append(f"{col}: {n_null} null value(s) in a non-nullable column")
        if allowed is not None:
            values = series.dropna()
            bad = values[~values.isin(list(allowed))]
            if len(bad):
                errors.append(f"{col}: {len(bad)} value(s) outside {sorted(allowed)}, "
                              f"e.g. {_examples(pd.unique(bad))}")

    key_missing = [c for c in key if c not in df.columns]
    if not key_missing:
        dup = df.duplicated(key, keep=False)
        if dup.any():
            keys = df.loc[dup, key].drop_duplicates().itertuples(index=False, name=None)
            errors.append(f"key ({', '.join(key)}) not unique: {int(dup.sum())} rows share a key, "
                          f"e.g. {_examples(keys)}")

    for check in checks:
        try:
            errors.extend(check(df))
        except KeyError:
            pass

    if errors:
        extra = [c for c in df.columns if c not in schema]
        lines = [f"{name} failed contract validation ({len(errors)} violation(s)):"]
        lines += [f"  - {e}" for e in errors]
        if extra:
            lines.append(f"  (note: extra columns, allowed: {', '.join(map(str, extra))})")
        raise ValueError("\n".join(lines))
    return df


def c1_extra_checks(df):
    """C1 rules beyond the schema: angle range, ball rows, eligibility, one frame per offset."""
    errors = []
    for col in ("o", "dir"):
        vals = df[col].dropna()
        bad = vals[(vals < 0) | (vals >= 360)]
        if len(bad):
            errors.append(f"{col}: {len(bad)} value(s) outside [0, 360), e.g. {_examples(bad.unique())}")

    is_ball = df["is_ball"].astype(bool)
    n_null_player = int((df["nflId"].isna() & ~is_ball).sum())
    if n_null_player:
        errors.append(f"nflId: null on {n_null_player} non-ball row(s); null is allowed only for the ball")
    n_ball_with_id = int((df["nflId"].notna() & is_ball).sum())
    if n_ball_with_id:
        errors.append(f"nflId: {n_ball_with_id} ball row(s) have a non-null nflId")
    if (df["side"].eq("ball") != is_ball).any():
        errors.append("side/is_ball: side == 'ball' must match is_ball")
    for col in ("pff_role", "o", "dir"):
        n = int((df[col].notna() & is_ball).sum())
        if n:
            errors.append(f"{col}: {n} ball row(s) are not null")

    group_keys = ["gameId", "playId", "offset"]
    balls = is_ball.groupby([df[k] for k in group_keys]).sum()
    bad_balls = balls[balls != 1]
    if len(bad_balls):
        errors.append(f"ball: {len(bad_balls)} (gameId, playId, offset) group(s) without exactly one "
                      f"ball row, e.g. {_examples(bad_balls.index)}")

    eligible = df["is_eligible"].astype(bool)
    n_bad_group = int((df["position_group"].notna() != eligible).sum())
    if n_bad_group:
        errors.append(f"position_group: {n_bad_group} row(s) where position_group is set but "
                      f"is_eligible is false, or the reverse")

    frames = df.groupby(group_keys)["frameId"].nunique()
    if (frames > 1).any():
        errors.append(f"frameId: {int((frames > 1).sum())} (gameId, playId, offset) group(s) "
                      f"use more than one frame")
    return errors


def c2_extra_checks(df):
    """C2 rules beyond the schema: frame order, time to throw, line to gain, target fields."""
    errors = []
    n = int((df["release_frameId"] <= df["snap_frameId"]).sum())
    if n:
        errors.append(f"release_frameId: {n} play(s) not after snap_frameId")
    ttt = (df["release_frameId"] - df["snap_frameId"]) * 0.1
    n = int((~np.isclose(df["time_to_throw_s"], ttt)).sum())
    if n:
        errors.append(f"time_to_throw_s: {n} play(s) != (release - snap) * 0.1")
    n = int((~np.isclose(df["line_to_gain_x"], df["los_x"] + df["yardsToGo"])).sum())
    if n:
        errors.append(f"line_to_gain_x: {n} play(s) != los_x + yardsToGo")
    n = int((df["target_nflId"].isna() != df["target_source"].eq("none")).sum())
    if n:
        errors.append(f"target_source: {n} play(s) where target_source 'none' does not match "
                      f"a null target_nflId")
    n = int((df["is_model_play"].astype(bool) & df["target_nflId"].isna()).sum())
    if n:
        errors.append(f"is_model_play: {n} Model_Play(s) without a target_nflId")
    return errors


def validate_c1(df, name="C1 Snapshot_Table"):
    return validate(df, C1_SCHEMA, C1_KEY, name, checks=(c1_extra_checks,))


def validate_c2(df, name="C2 Play_Table"):
    return validate(df, C2_SCHEMA, C2_KEY, name, checks=(c2_extra_checks,))


# ---------------------------------------------------------------------------
# Fixtures (Req 9.3): 3 synthetic plays x 6 offsets x 23 rows.

_FIXTURE_PLAYS = [
    # Model_Play, 2.8 s to throw, 5 eligible, Zone.
    dict(gameId=9999999901, playId=101, week=1, possessionTeam="FXA", defensiveTeam="FXB",
         quarter=1, down=1, yardsToGo=10, gameClock="13:33", score_margin=0, los_x=35.0,
         pff_passCoverage="Cover-3", pff_passCoverageType="Zone", pff_playAction=0,
         dropBackType="TRADITIONAL", passResult="C", snap_frameId=11, release_frameId=39,
         pressured=False, target_source="description", target_slot=7, n_rush=4,
         receivers=[(6, "WR"), (7, "WR"), (8, "WR"), (9, "TE"), (10, "RB")], blockers=[]),
    # Model_Play, quick 0.4 s throw (offset 5 clamped to the snap), 4 eligible, Man.
    dict(gameId=9999999902, playId=102, week=2, possessionTeam="FXB", defensiveTeam="FXA",
         quarter=2, down=3, yardsToGo=7, gameClock="02:10", score_margin=-7, los_x=52.0,
         pff_passCoverage="Cover-1", pff_passCoverageType="Man", pff_playAction=1,
         dropBackType="DESIGNED_ROLLOUT_RIGHT", passResult="I", snap_frameId=11, release_frameId=15,
         pressured=True, target_source="description", target_slot=9, n_rush=5,
         receivers=[(6, "WR"), (7, "WR"), (9, "TE"), (10, "RB")], blockers=[(11, "TE")]),
    # Unmatched target: target_source 'none', not a Model_Play. dropBackType NA as in plays.csv.
    dict(gameId=9999999903, playId=103, week=3, possessionTeam="FXA", defensiveTeam="FXB",
         quarter=4, down=2, yardsToGo=3, gameClock="00:45", score_margin=3, los_x=77.0,
         pff_passCoverage="Cover-2", pff_passCoverageType="Zone", pff_playAction=0,
         dropBackType=None, passResult="I", snap_frameId=11, release_frameId=33,
         pressured=False, target_source="none", target_slot=None, n_rush=3,
         receivers=[(6, "WR"), (7, "WR"), (9, "TE")], blockers=[(10, "RB"), (11, "TE")]),
]
_TEAM_BASE = {"FXA": 991000, "FXB": 992000}   # nflId = base + (0 offense | 50 defense) + slot
_MID_Y = 26.65


def _nfl_id(team, side, slot):
    return _TEAM_BASE[team] + (0 if side == "offense" else 50) + slot


def _velocity(s, dir_deg):
    rad = np.radians(dir_deg)
    return s * np.sin(rad), s * np.cos(rad)   # dir is clockwise from +y; 90 = +x


def _fixture_players(play, rng):
    """Alignment at the snap plus a constant velocity for each of the 22 players."""
    los, off, dfn = play["los_x"], play["possessionTeam"], play["defensiveTeam"]
    players = []

    def add(team, side, slot, role, group, x, y, s, dir_deg):
        players.append(dict(nflId=_nfl_id(team, side, slot), side=side, pff_role=role,
                            position_group=group, x0=x, y0=y, s=s, dir=dir_deg % 360))

    add(off, "offense", 0, "Pass", None, los - 5.0, _MID_Y, rng.uniform(0.5, 1.0), 270)
    for i, dy in enumerate((-4, -2, 0, 2, 4)):
        add(off, "offense", 1 + i, "Pass Block", None, los - rng.uniform(0.8, 1.5), _MID_Y + dy,
            rng.uniform(0.3, 1.0), 270 + rng.uniform(-20, 20))
    for slot, pos in play["blockers"]:
        x = los - (5.0 if pos == "RB" else 1.0)
        add(off, "offense", slot, "Pass Block", None, x, _MID_Y + rng.uniform(-5, 5),
            rng.uniform(0.5, 1.5), 270 + rng.uniform(-40, 40))

    receivers = []
    for i, (slot, group) in enumerate(play["receivers"]):
        if group == "RB":
            x, y = los - rng.uniform(4, 6), _MID_Y + rng.uniform(-2, 2)
        else:
            x = los - rng.uniform(0.3, 1.5)
            y = [5.0, 48.0, 12.0, 41.0, 20.0][i] if group == "WR" else _MID_Y + rng.choice([-5, 5])
        add(off, "offense", slot, "Pass Route", group, x, y, rng.uniform(4, 7.5),
            90 + rng.uniform(-35, 35))
        receivers.append(players[-1])

    n_rush = play["n_rush"]
    for slot in range(n_rush):
        add(dfn, "defense", slot, "Pass Rush", None, los + rng.uniform(0.5, 1.5),
            _MID_Y + rng.uniform(-6, 6), rng.uniform(1.5, 2.0), 270 + rng.uniform(-15, 15))
    for j, slot in enumerate(range(n_rush, 11)):
        if j < len(receivers):   # cover a receiver: in front of him, slower, same heading
            rec = receivers[j]
            add(dfn, "defense", slot, "Coverage", None, max(rec["x0"] + rng.uniform(2, 6),
                los + rng.uniform(1, 5)), rec["y0"] + rng.uniform(-2, 2),
                rec["s"] * rng.uniform(0.5, 0.8), rec["dir"] + rng.uniform(-10, 10))
        else:                    # deep zone
            add(dfn, "defense", slot, "Coverage", None, los + rng.uniform(10, 15),
                rng.uniform(12, 41), rng.uniform(1, 3), 90 + rng.uniform(-60, 60))
    return pd.DataFrame(players)


def _fixture_c1_play(play, rng):
    snap, release = play["snap_frameId"], play["release_frameId"]
    people = _fixture_players(play, rng)
    vx, vy = _velocity(people["s"].to_numpy(), people["dir"].to_numpy())
    qb = people.iloc[0]
    rows = []
    for offset in range(6):
        frame = max(release - offset, snap)
        t = (frame - snap) * 0.1
        snap_rows = pd.DataFrame({
            "nflId": people["nflId"], "side": people["side"], "pff_role": people["pff_role"],
            "position_group": people["position_group"],
            "x": people["x0"] + vx * t, "y": people["y0"] + vy * t, "s": people["s"],
            "a": rng.uniform(0, 3, len(people)),
            "o": people["dir"] + rng.normal(0, 30, len(people)), "dir": people["dir"],
        })
        qb_x, qb_y = qb["x0"] + vx[0] * t, qb["y0"] + vy[0] * t
        ball = pd.DataFrame({"nflId": [pd.NA], "side": ["ball"], "pff_role": [None],
                             "position_group": [None], "x": [qb_x + 0.3], "y": [qb_y + 0.3],
                             "s": [qb["s"]], "a": [rng.uniform(0, 1)], "o": [np.nan],
                             "dir": [np.nan]})
        part = pd.concat([snap_rows, ball], ignore_index=True)
        part.insert(0, "offset", offset)
        part.insert(1, "frameId", frame)
        part.insert(2, "clamped", release - offset < snap)
        rows.append(part)
    c1 = pd.concat(rows, ignore_index=True)
    c1.insert(0, "gameId", play["gameId"])
    c1.insert(1, "playId", play["playId"])
    return c1


def fixture_c1c2(cfg):
    """Write synthetic C1/C2 (3 plays x 6 offsets x 23 rows) to out/fixtures/; return (c1, c2)."""
    rng = np.random.default_rng(20231009)
    c1 = pd.concat([_fixture_c1_play(p, rng) for p in _FIXTURE_PLAYS], ignore_index=True)

    c1["is_ball"] = c1["side"].eq("ball")
    c1["is_eligible"] = c1["position_group"].notna()
    for col in ("o", "dir"):
        c1[col] = c1[col].astype(float).round(2) % 360
    for col in ("x", "y", "s", "a"):
        c1[col] = c1[col].astype(float).round(2)
    c1 = c1.astype({"gameId": "int64", "playId": "int64", "offset": "int64",
                    "frameId": "int64", "clamped": bool, "nflId": "Int64"})
    c1 = c1[list(C1_SCHEMA)]

    plays = []
    for p in _FIXTURE_PLAYS:
        row = {k: p[k] for k in C2_SCHEMA if k in p}
        row["line_to_gain_x"] = p["los_x"] + p["yardsToGo"]
        row["time_to_throw_s"] = (p["release_frameId"] - p["snap_frameId"]) * 0.1
        row["qb_nflId"] = _nfl_id(p["possessionTeam"], "offense", 0)
        row["n_eligible"] = len(p["receivers"])
        row["target_nflId"] = (pd.NA if p["target_slot"] is None
                               else _nfl_id(p["possessionTeam"], "offense", p["target_slot"]))
        row["is_model_play"] = p["target_slot"] is not None
        plays.append(row)
    c2 = pd.DataFrame(plays)[list(C2_SCHEMA)]
    c2 = c2.astype({"qb_nflId": "Int64", "target_nflId": "Int64", "pressured": bool,
                    "is_model_play": bool})

    validate_c1(c1, "C1 fixture")
    validate_c2(c2, "C2 fixture")
    # Req 9.5 on the fixture: every Model_Play target is an eligible row of its play.
    targets = c2.loc[c2["is_model_play"], ["gameId", "playId", "target_nflId"]]
    eligible = c1.loc[c1["is_eligible"], ["gameId", "playId", "nflId"]].drop_duplicates()
    hits = targets.merge(eligible, left_on=["gameId", "playId", "target_nflId"],
                         right_on=["gameId", "playId", "nflId"])
    assert len(hits) == len(targets), "fixture Model_Play target missing from eligible C1 rows"

    out_dir = cfg.derived_dir / "fixtures"
    out_dir.mkdir(parents=True, exist_ok=True)
    c1.to_parquet(out_dir / C1_FILE, index=False)
    c2.to_parquet(out_dir / C2_FILE, index=False)
    return c1, c2
