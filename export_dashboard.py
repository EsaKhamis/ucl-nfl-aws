"""Bridge the Metrics-stage C3 parquet to the Next.js dashboard's JSON input.

The dashboard (visualisation/) loads public/data/receivers.json and validates it
against the ReceiversFile shape (src/lib/types.ts, DashboardProvider validateFile):
a top-level object with an expectationModel{a,b} and a receivers[] array of weekly
rows. This module re-aggregates the per-route C3 Route_Features_Table to WEEKLY
grain -- one row per (nflId, week) -- so Target Over Expectation (TOE) is accurate
at the grain the dashboard draws, rather than being read from the season-level C4
table. The real logistic model's xtarget is used for expectedTargetShare, so this
is the tracking-based metric (schemaVersion '2.0-tracking'), not the earlier proxy.

    from config import Config
    from export_dashboard import build_dashboard_json
    build_dashboard_json(Config())

Writes receivers.json (+ a receivers.tracking.json backup) under
visualisation/public/data/, after copying any existing receivers.json aside to
receivers.proxy-backup.json so the team can diff/revert to the old proxy data.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from config import Config
from contracts_metrics import C3_FILE

SCHEMA_VERSION = "2.0-tracking"

# Dashboard team-abbreviation convention: the source uses 'LA' for the LA Rams,
# but the dashboard expects 'LAR'. All other abbreviations are already standard.
TEAM_ABBR_MAP = {"LA": "LAR"}


def _norm_team(abbr: str) -> str:
    return TEAM_ABBR_MAP.get(abbr, abbr)


def _mode(series: pd.Series):
    """Most frequent value in a non-empty series (first on ties)."""
    return series.mode().iloc[0]


def _rate(numer: float, denom: float) -> float:
    """Safe rate rounded to 4 dp; 0.0 when the denominator is empty."""
    if denom <= 0:
        return 0.0
    return round(float(numer) / float(denom), 4)


def _load_play_results(cfg: Config) -> pd.DataFrame:
    """plays.csv keyed on (gameId, playId) with passResult and playResult yards."""
    plays = pd.read_csv(
        cfg.data_dir / "plays.csv",
        usecols=["gameId", "playId", "passResult", "playResult"],
    )
    plays["gameId"] = plays["gameId"].astype("int64")
    plays["playId"] = plays["playId"].astype("int64")
    return plays


def build_dashboard_json(cfg: Config) -> dict:
    """Re-aggregate C3 to weekly grain and write the dashboard receivers.json.

    Returns the envelope dict that was written.
    """
    c3_path = cfg.derived_dir / C3_FILE
    c3 = pd.read_parquet(c3_path)

    plays = _load_play_results(cfg)
    # Per-play completion flag and play yardage, used only for box-score add-ons.
    plays["is_completion"] = plays["passResult"].astype("string") == "C"
    plays["play_yards"] = pd.to_numeric(plays["playResult"], errors="coerce")

    # Join play-level completion/yards onto each C3 route (one row per route).
    c3 = c3.merge(
        plays[["gameId", "playId", "is_completion", "play_yards"]],
        on=["gameId", "playId"],
        how="left",
    )

    rows: list[dict] = []
    for (nfl_id, week), g in c3.groupby(["nflId", "week"], sort=True):
        routes_run = int(len(g))
        targets = int(g["is_target"].sum())
        open_routes = int(g["open_flag"].sum())
        x_targets_sum = float(g["xtarget"].sum())

        open_rate = _rate(open_routes, routes_run)
        target_share = min(_rate(targets, routes_run), 1.0)
        expected_target_share = min(_rate(x_targets_sum, routes_run), 1.0)
        toe = round(target_share - expected_target_share, 4)

        # Coverage subsets (nullable coverage_type; 'Other'/NaN excluded).
        man = g[g["coverage_type"] == "Man"]
        zone = g[g["coverage_type"] == "Zone"]
        assert len(man) + len(zone) <= routes_run, (
            f"man+zone subset routes exceed routesRun for {int(nfl_id)} wk{int(week)}"
        )
        open_rate_man = _rate(int(man["open_flag"].sum()), len(man))
        open_rate_zone = _rate(int(zone["open_flag"].sum()), len(zone))
        target_share_man = _rate(int(man["is_target"].sum()), len(man))
        target_share_zone = _rate(int(zone["is_target"].sum()), len(zone))

        # Box-score add-ons: this player's targeted plays this week.
        targeted = g[g["is_target"]]
        completions = targeted[targeted["is_completion"] == True]  # noqa: E712
        receptions = int(len(completions))
        yards = int(completions["play_yards"].fillna(0).sum())

        # team / opponent / gameId by where the player ran the most routes.
        team = _norm_team(_mode(g["possessionTeam"]))
        opponent = _norm_team(_mode(g["defensiveTeam"]))
        game_id = str(int(_mode(g["gameId"])))

        rows.append(
            {
                "playerId": str(int(nfl_id)),
                "playerName": str(g["displayName"].iloc[0]),
                "team": team,
                "position": str(g["position_group"].iloc[0]),
                "week": int(week),
                "opponent": opponent,
                "gameId": game_id,
                "openRate": open_rate,
                "targetShare": target_share,
                "expectedTargetShare": expected_target_share,
                "toe": toe,
                "openRateVsMan": open_rate_man,
                "openRateVsZone": open_rate_zone,
                "targetShareVsMan": target_share_man,
                "targetShareVsZone": target_share_zone,
                "routesRun": routes_run,
                "targets": targets,
                "receptions": receptions,
                "yards": yards,
            }
        )

    _assert_accuracy_guards(rows)

    # Fit the scatter reference line expectedTargetShare ~ a + b*openRate by
    # numpy least squares over the emitted rows (display only; per-row toe is
    # read directly from targetShare - expectedTargetShare by the dashboard).
    open_rates = np.array([r["openRate"] for r in rows], dtype=float)
    exp_shares = np.array([r["expectedTargetShare"] for r in rows], dtype=float)
    design = np.column_stack([np.ones_like(open_rates), open_rates])
    (a, b), *_ = np.linalg.lstsq(design, exp_shares, rcond=None)
    a = round(float(a), 6)
    b = round(float(b), 6)

    envelope = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expectationModel": {
            "formula": "clamp(a + b*openRate, 0, 1)",
            "a": a,
            "b": b,
        },
        "receivers": rows,
    }

    data_dir = cfg.derived_dir.parent / "visualisation" / "public" / "data"
    receivers_path = data_dir / "receivers.json"
    tracking_path = data_dir / "receivers.tracking.json"
    proxy_backup_path = data_dir / "receivers.proxy-backup.json"

    # Preserve the old proxy data so the team can diff / revert.
    if receivers_path.exists():
        shutil.copyfile(receivers_path, proxy_backup_path)
        print(f"backed up existing proxy data -> {proxy_backup_path}")

    text = json.dumps(envelope, indent=2)
    receivers_path.write_text(text)
    tracking_path.write_text(text)

    print(f"wrote {receivers_path}")
    print(f"wrote {tracking_path}")
    print(f"rows: {len(rows)}  fitted a={a}  b={b}")
    return envelope


def _assert_accuracy_guards(rows: list[dict]) -> None:
    """Assert the metric invariants hold before writing (prints each check)."""
    assert rows, "no weekly rows produced"

    for r in rows:
        for field in ("openRate", "targetShare", "expectedTargetShare"):
            v = r[field]
            assert 0.0 <= v <= 1.0, f"{field}={v} out of [0,1] for {r['playerId']} wk{r['week']}"
        assert abs(r["toe"] - (r["targetShare"] - r["expectedTargetShare"])) < 1e-9, (
            f"toe mismatch for {r['playerId']} wk{r['week']}"
        )
        assert r["targets"] <= r["routesRun"], (
            f"targets>{r['routesRun']} routes for {r['playerId']} wk{r['week']}"
        )
        assert 1 <= r["week"] <= 8, f"week {r['week']} out of 1..8"
        assert r["position"] in {"WR", "TE", "RB"}, f"bad position {r['position']}"
        for field in (
            "openRate", "targetShare", "expectedTargetShare", "toe",
            "openRateVsMan", "openRateVsZone", "targetShareVsMan", "targetShareVsZone",
            "routesRun", "targets", "receptions", "yards", "week",
        ):
            v = r[field]
            assert not (isinstance(v, float) and np.isnan(v)), (
                f"NaN in {field} for {r['playerId']} wk{r['week']}"
            )
    print(f"guard ok: {len(rows)} rows -- openRate/targetShare/expectedTargetShare in [0,1]")
    print("guard ok: toe == targetShare - expectedTargetShare (<1e-9)")
    print("guard ok: targets <= routesRun")
    print("guard ok: no NaN in numeric fields; week in 1..8; position in {WR,TE,RB}")


if __name__ == "__main__":
    build_dashboard_json(Config())
