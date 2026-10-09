"""Export tracking-based receiver metrics (Contract C3) to the dashboard JSON.

Reads out/c3_routes.parquet (one row per Route on a Model_Play) plus
plays.csv (passResult, playResult) and games.csv (week), and writes the
envelope the Next.js dashboard loads:

    visualisation/public/data/receivers.json           (the file the UI loads)
    visualisation/public/data/receivers.tracking.json  (identical copy)

One row per receiver per week. Rates are per route, so routes-weighted means
of the week rows and plain sums of the counts reproduce the C4 Receiver_TOE
"All" split:
    sum(routesRun)                         == C4 routes
    sum(targets)                           == C4 targets
    sum(expectedTargetShare * routesRun)   == C4 x_targets   (within rounding)
    sum(openRate * routesRun)              == C4 open_routes (within rounding)

Usage:
    python export_dashboard.py [--c3 PATH] [--out-dir DIR]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import load
from config import Config

C3_FILE = "c3_routes.parquet"
OUT_DIR = Path(__file__).resolve().parent / "visualisation" / "public" / "data"
OUT_FILES = ("receivers.json", "receivers.tracking.json")
SCHEMA_VERSION = "2.0.0-tracking"
TEAM_MAP = {"LA": "LAR"}   # dashboard expects LAR for the Rams (as the proxy did)
POSITIONS = ("WR", "TE", "RB")

C3_COLUMNS = ["gameId", "playId", "nflId", "week", "displayName", "position_group",
              "possessionTeam", "defensiveTeam", "coverage_type",
              "open_flag", "is_target", "xtarget"]

FORMULA = (
    "Per row: expectedTargetShare = sum(xTarget) / routesRun, where xTarget is a "
    "logistic expected-target model on pre-release (0.4 s) tracking features "
    "(openness_pre, depth, dist_from_qb, rusher_distance x depth, "
    "rusher_distance x dist_from_qb), normalized to sum to 1 within each play. "
    "openRate = share of routes where the receiver was the most open on the play; "
    "targetShare = targets / routesRun. a/b: routes-weighted least-squares line "
    "expectedTargetShare ~ a + b*openRate over the receiver-week rows, an "
    "approximation used only for the chart's reference line."
)


def _r4(x):
    return round(float(x), 4)


def _mode(s: pd.Series) -> str:
    """Most common value; ties go to the alphabetically first."""
    counts = s.value_counts()
    return sorted(counts[counts == counts.max()].index)[0]


def _split_rates(g: pd.DataFrame, coverage: str):
    sub = g[g["coverage_type"] == coverage]
    n = len(sub)
    if n == 0:
        return 0.0, 0.0
    return sub["open_flag"].mean(), sub["is_target"].sum() / n


def build_rows(c3: pd.DataFrame, plays: pd.DataFrame, games: pd.DataFrame) -> list[dict]:
    key = ["gameId", "playId"]
    df = c3[C3_COLUMNS].copy()
    df["open_flag"] = df["open_flag"].astype(bool)
    df["is_target"] = df["is_target"].astype(bool)
    df["xtarget"] = df["xtarget"].astype(float)

    # Week comes from games.csv (authoritative); C3's week must agree.
    gw = games[["gameId", "week"]].rename(columns={"week": "week_g"})
    df = df.merge(gw, on="gameId", how="left", validate="many_to_one")
    if df["week_g"].isna().any() or (df["week_g"] != df["week"]).any():
        raise ValueError("C3 week disagrees with games.csv")
    df["week"] = df["week_g"].astype(int)

    pr = plays[key + ["passResult", "playResult"]]
    df = df.merge(pr, on=key, how="left", validate="many_to_one")
    df["is_rec"] = df["is_target"] & (df["passResult"] == "C")
    df["rec_yards"] = np.where(df["is_rec"], df["playResult"].fillna(0), 0).astype(int)

    for col in ("possessionTeam", "defensiveTeam"):
        df[col] = df[col].replace(TEAM_MAP)

    rows = []
    for (nfl_id, week), g in df.groupby(["nflId", "week"], sort=True):
        routes = len(g)
        targets = int(g["is_target"].sum())
        ts = _r4(targets / routes)
        ets = _r4(g["xtarget"].sum() / routes)
        game_routes = g.groupby("gameId").size()
        game_id = sorted(game_routes[game_routes == game_routes.max()].index)[0]
        or_man, ts_man = _split_rates(g, "Man")
        or_zone, ts_zone = _split_rates(g, "Zone")
        rows.append({
            "playerId": str(int(nfl_id)),
            "playerName": str(g["displayName"].iloc[0]),
            "team": _mode(g["possessionTeam"]),
            "position": _mode(g["position_group"]),
            "week": int(week),
            "opponent": _mode(g["defensiveTeam"]),
            "gameId": str(int(game_id)),
            "openRate": _r4(g["open_flag"].mean()),
            "targetShare": ts,
            "expectedTargetShare": ets,
            "toe": _r4(ts - ets),
            "openRateVsMan": _r4(or_man),
            "openRateVsZone": _r4(or_zone),
            "targetShareVsMan": _r4(ts_man),
            "targetShareVsZone": _r4(ts_zone),
            "routesRun": routes,
            "targets": targets,
            "receptions": int(g["is_rec"].sum()),
            "yards": int(g["rec_yards"].sum()),
        })
    rows.sort(key=lambda r: (r["week"], r["team"], -r["toe"]))
    return rows


def fit_line(rows: list[dict]) -> tuple[float, float]:
    """Routes-weighted least squares: expectedTargetShare ~ a + b*openRate."""
    x = np.array([r["openRate"] for r in rows])
    y = np.array([r["expectedTargetShare"] for r in rows])
    w = np.array([r["routesRun"] for r in rows], dtype=float)
    xm, ym = np.average(x, weights=w), np.average(y, weights=w)
    sxx = np.sum(w * (x - xm) ** 2)
    b = np.sum(w * (x - xm) * (y - ym)) / sxx if sxx > 0 else 0.0
    a = ym - b * xm
    return round(float(a), 6), round(float(b), 6)


def check_rows(rows: list[dict]) -> None:
    """The same per-row rules scripts/check-data.mjs enforces."""
    rate_fields = ("openRate", "targetShare", "expectedTargetShare", "openRateVsMan",
                   "openRateVsZone", "targetShareVsMan", "targetShareVsZone")
    for r in rows:
        if not r["receptions"] <= r["targets"] <= r["routesRun"]:
            raise ValueError(f"count order violated: {r}")
        if any(not 0.0 <= r[f] <= 1.0 for f in rate_fields):
            raise ValueError(f"rate outside [0, 1]: {r}")
        if abs(r["toe"] - (r["targetShare"] - r["expectedTargetShare"])) > 5e-4:
            raise ValueError(f"toe mismatch: {r}")
        if r["position"] not in POSITIONS:
            raise ValueError(f"bad position: {r}")


def main(argv=None):
    cfg = Config()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--c3", type=Path, default=cfg.derived_dir / C3_FILE)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)

    c3 = pd.read_parquet(args.c3)
    missing = [c for c in C3_COLUMNS if c not in c3.columns]
    if missing:
        raise ValueError(f"{args.c3} is missing C3 columns: {', '.join(missing)}")

    rows = build_rows(c3, load.load_plays(), load.load_games())
    check_rows(rows)
    a, b = fit_line(rows)
    envelope = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "expectationModel": {"formula": FORMULA, "a": a, "b": b},
        "receivers": rows,
    }
    text = json.dumps(envelope, indent=2) + "\n"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name in OUT_FILES:
        (args.out_dir / name).write_text(text, encoding="utf-8")

    players = {r["playerId"] for r in rows}
    teams = {r["team"] for r in rows}
    print(f"export_dashboard: {len(rows)} rows, {len(players)} players, {len(teams)} teams, "
          f"weeks {sorted({r['week'] for r in rows})}; a={a}, b={b} -> "
          + ", ".join(str(args.out_dir / n) for n in OUT_FILES))


if __name__ == "__main__":
    main()
