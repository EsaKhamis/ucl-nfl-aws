"""Export the pipeline's contract tables to the dashboard's single data file.

    python visualisation/scripts/export_data.py              # out/          -> public/data/dashboard.json
    python visualisation/scripts/export_data.py --fixtures   # out/fixtures/ -> same path, fixtures: true

Reads C1/C2 (Dev 1) and, when present, C3/C4/C5a/C6 (Dev 2) from the derived dir
using the design.md file names. Nothing is modelled here:
  - receivers: C4 rows (split All/Man/Zone). Without C4 they are aggregated from the
    route table for the xTarget-free metrics only (open_rate, target_share, counts);
    x_targets / toe / toe_per_100_routes stay null and status.toe is "pending".
  - offense: C5a rows, or [] with status "pending" (Team_Funnel_Index needs TOE).
  - instead flows: C6 events, or derived from the route table (Most_Open != target
    on a Model_Play, the C6 definition) with status "provisional".
Only pandas / numpy / pyarrow (requirements.txt); the pipeline modules are imported
read-only. The only file written is --out.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import contracts_data  # noqa: E402
import contracts_metrics as cm  # noqa: E402
import features  # noqa: E402
import load  # noqa: E402
from config import Config  # noqa: E402

SCHEMA_VERSION = "2.0.0"
SPLITS = ("All", "Man", "Zone")
PANELS = ("All", "Man", "Zone")  # instead-flow panels; All includes coverage "Other"
DEFAULT_OUT = REPO_ROOT / "visualisation" / "public" / "data" / "dashboard.json"
MAX_BYTES = 5_000_000
PLAY_KEY = ["gameId", "playId"]

ROUTE_COLS = [
    "gameId", "playId", "nflId", "displayName", "position_group", "possessionTeam",
    "coverage_type", "separation_pre", "openness_pre", "is_target", "is_most_open",
    "open_flag",
]
RECEIVER_COLS = [
    "nflId", "displayName", "position_group", "team", "split", "routes", "targets",
    "open_routes", "open_rate", "target_share", "x_targets", "toe",
    "toe_per_100_routes", "meets_minimum",
]
OFFENSE_COLS = list(cm.C5A_SCHEMA)
INSTEAD_COLS = ["coverage_type", "ignored_position_group", "target_position_group"]

NOTE_OPEN = {
    "most_open": ("Open Rate = share of routes where the receiver was the Most_Open option "
                  "(composite openness at {offset_s:.1f} s pre-release)."),
    "threshold": ("Open Rate = share of routes with separation of at least {threshold:g} yd "
                  "at {offset_s:.1f} s pre-release (Open_Mode threshold)."),
}
NOTE_TARGET = ("Target Share = share of routes on which he was targeted "
               "(per route, not share of team targets).")
NOTE_TOE = "TOE = targets - sum of xTarget over his routes (Dev 2's C4)."
NOTE_TOE_PENDING = "TOE = targets - sum of xTarget; pending until Dev 2 publishes C4."


def _rel(path: Path) -> str:
    """Repo-relative path string for the `sources` block."""
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Route table (C3, or features.py on C1/C2).

def load_routes(derived_dir: Path, cfg: Config) -> tuple[pd.DataFrame, str]:
    """One row per Route on a Model_Play with the columns in ROUTE_COLS."""
    c3_path = derived_dir / cm.C3_FILE
    if c3_path.exists():
        c3 = cm.validate_c3(pd.read_parquet(c3_path))
        return c3[ROUTE_COLS].copy(), _rel(c3_path)

    c1_path, c2_path = derived_dir / contracts_data.C1_FILE, derived_dir / contracts_data.C2_FILE
    c1 = contracts_data.validate_c1(pd.read_parquet(c1_path))
    c2 = contracts_data.validate_c2(pd.read_parquet(c2_path))
    feats = features.build_route_features(c1, c2, cfg)

    elig = c1[(c1["offset"] == cfg.pre_release_offset) & c1["is_eligible"].astype(bool)]
    pg = elig[PLAY_KEY + ["nflId", "position_group"]].dropna(subset=["nflId"]).copy()
    pg["nflId"] = pg["nflId"].astype("int64")
    ctx = c2[PLAY_KEY + ["possessionTeam", "pff_passCoverageType"]].rename(
        columns={"pff_passCoverageType": "coverage_type"})

    routes = feats.copy()
    routes["nflId"] = routes["nflId"].astype("int64")
    routes = routes.merge(pg.drop_duplicates(PLAY_KEY + ["nflId"]),
                          on=PLAY_KEY + ["nflId"], how="left")
    routes = routes.merge(ctx, on=PLAY_KEY, how="left")
    try:
        names = load.load_players()[["nflId", "displayName"]].copy()
        names["nflId"] = names["nflId"].astype("int64")
        routes = routes.merge(names.drop_duplicates("nflId"), on="nflId", how="left")
    except FileNotFoundError:
        routes["displayName"] = None
    missing = routes["displayName"].isna()
    routes.loc[missing, "displayName"] = "Player " + routes.loc[missing, "nflId"].astype(str)
    for col in ("is_target", "is_most_open", "open_flag"):
        routes[col] = routes[col].astype(bool)
    src = (f"features.build_route_features({_rel(c1_path)}, {_rel(c2_path)})")
    return routes[ROUTE_COLS].reset_index(drop=True), src


# ---------------------------------------------------------------------------
# Receivers (C4, or xTarget-free aggregation of the route table).

def receivers_from_c4(c4: pd.DataFrame) -> pd.DataFrame:
    rows = c4[c4["split"].isin(SPLITS)][RECEIVER_COLS].copy()
    rows = rows.astype({"nflId": "int64", "routes": "int64", "targets": "int64",
                        "open_routes": "int64", "meets_minimum": bool})
    return rows.sort_values(["split", "nflId"]).reset_index(drop=True)


def receivers_from_routes(routes: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    counts = routes.groupby(["nflId", "possessionTeam"]).size().reset_index(name="n")
    counts = counts.sort_values(["nflId", "n", "possessionTeam"], ascending=[True, False, True])
    team = counts.groupby("nflId").head(1)[["nflId", "possessionTeam"]].rename(
        columns={"possessionTeam": "team"})
    ident = (routes.groupby("nflId")[["displayName", "position_group"]]
             .agg(lambda s: s.mode().iloc[0] if s.notna().any() else None).reset_index())

    parts = []
    for split in SPLITS:
        sub = routes if split == "All" else routes[routes["coverage_type"] == split]
        if sub.empty:
            continue
        agg = sub.groupby("nflId").agg(routes=("is_target", "size"),
                                       targets=("is_target", "sum"),
                                       open_routes=("open_flag", "sum")).reset_index()
        agg["split"] = split
        minimum = cfg.route_minimum if split == "All" else cfg.split_route_minimum
        agg["meets_minimum"] = agg["routes"] >= minimum
        parts.append(agg)
    rows = pd.concat(parts, ignore_index=True)
    rows = rows.merge(ident, on="nflId", how="left").merge(team, on="nflId", how="left")
    rows["open_rate"] = rows["open_routes"] / rows["routes"]
    rows["target_share"] = rows["targets"] / rows["routes"]
    for col in ("x_targets", "toe", "toe_per_100_routes"):
        rows[col] = None  # needs xTarget: only ever taken from Dev 2's C4
    rows = rows.astype({"nflId": "int64", "routes": "int64", "targets": "int64",
                        "open_routes": "int64", "meets_minimum": bool})
    return rows[RECEIVER_COLS].sort_values(["split", "nflId"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Offense (C5a) and instead flows (C6, or derived from routes).

def offense_from_c5a(path: Path) -> list[dict]:
    if not path.exists():
        return []
    c5a = cm.validate_c5a(pd.read_parquet(path))
    c5a = c5a[OFFENSE_COLS].sort_values(["funnel_index", "team"], ascending=[False, True])
    return _records(c5a)


def instead_events(routes: pd.DataFrame) -> pd.DataFrame:
    """Ignored_Open_Events: Model_Plays whose Most_Open route is not the target route."""
    most_open = routes[routes["is_most_open"]][PLAY_KEY + ["nflId", "position_group", "coverage_type"]]
    target = routes[routes["is_target"]][PLAY_KEY + ["nflId", "position_group"]]
    ev = most_open.merge(target, on=PLAY_KEY, suffixes=("_open", "_target"))
    ev = ev[ev["nflId_open"] != ev["nflId_target"]]
    return ev.rename(columns={"position_group_open": "ignored_position_group",
                              "position_group_target": "target_position_group"})[INSTEAD_COLS]


def flows(events: pd.DataFrame) -> list[dict]:
    out = []
    for panel in PANELS:
        sub = events if panel == "All" else events[events["coverage_type"] == panel]
        sub = sub.dropna(subset=["ignored_position_group", "target_position_group"])
        if sub.empty:
            continue
        grp = (sub.groupby(["ignored_position_group", "target_position_group"])
               .size().reset_index(name="count"))
        grp["share"] = grp["count"] / grp["count"].sum()
        grp.insert(0, "coverage_type", panel)
        out.append(grp)
    if not out:
        return []
    df = pd.concat(out, ignore_index=True).sort_values(
        ["coverage_type", "ignored_position_group", "target_position_group"])
    return _records(df)


# ---------------------------------------------------------------------------
# Payload assembly, checks and writing.

def _clean(value):
    """JSON-safe scalar: NaN/NA -> None, numpy -> python, floats rounded to 4 dp."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return None if math.isnan(value) or math.isinf(value) else round(float(value), 4)
    return value


def _records(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in row.items()}
            for row in df.astype(object).to_dict(orient="records")]


def build_payload(derived_dir: Path, cfg: Config, fixtures: bool = False) -> dict:
    derived_dir = Path(derived_dir)
    routes, routes_src = load_routes(derived_dir, cfg)

    c4_path = derived_dir / cm.C4_FILE
    if c4_path.exists():
        receivers = receivers_from_c4(cm.validate_c4(pd.read_parquet(c4_path)))
        receivers_src, receivers_status = _rel(c4_path), "c4"
    else:
        receivers = receivers_from_routes(routes, cfg)
        receivers_src, receivers_status = "routes", "provisional"

    c5a_path = derived_dir / cm.C5A_FILE
    offense = offense_from_c5a(c5a_path)

    c6_path = derived_dir / cm.C6_FILE
    if c6_path.exists():
        events = cm.validate_c6(pd.read_parquet(c6_path))[INSTEAD_COLS]
        instead_src, instead_status = _rel(c6_path), "c6"
    else:
        events = instead_events(routes)
        instead_src, instead_status = "routes", "provisional"

    toe_available = receivers_status == "c4"
    open_note = NOTE_OPEN[cfg.open_mode].format(offset_s=cfg.pre_release_offset / 10,
                                                threshold=cfg.open_threshold)
    notes = [open_note, NOTE_TARGET,
             NOTE_TOE if toe_available else NOTE_TOE_PENDING]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fixtures": bool(fixtures),
        "config": {
            "route_minimum": cfg.route_minimum,
            "split_route_minimum": cfg.split_route_minimum,
            "team_route_minimum": cfg.team_route_minimum,
            "open_mode": cfg.open_mode,
            "pre_release_offset": cfg.pre_release_offset,
        },
        "sources": {
            "routes": routes_src,
            "receivers": receivers_src,
            "offense": _rel(c5a_path) if offense else None,
            "instead": instead_src,
        },
        "status": {
            "receivers": receivers_status,
            "toe": "available" if toe_available else "pending",
            "offense": "available" if offense else "pending",
            "instead": instead_status,
        },
        "counts": {
            "model_plays": int(routes[PLAY_KEY].drop_duplicates().shape[0]),
            "routes": int(len(routes)),
            "receivers": int(routes["nflId"].nunique()),
            "ignored_open_events": int(len(events)),
        },
        "receivers": _records(receivers),
        "offense": offense,
        "instead_flows": flows(events),
        "notes": notes,
    }


def check_payload(payload: dict) -> None:
    """Raise AssertionError listing every violated invariant."""
    errors = []
    rows = pd.DataFrame(payload["receivers"], columns=RECEIVER_COLS)
    if rows.empty:
        errors.append("receivers: no rows for splits All/Man/Zone")
    else:
        for col in ("open_rate", "target_share"):
            bad = rows[(rows[col] < 0) | (rows[col] > 1)]
            if len(bad):
                errors.append(f"{col}: {len(bad)} value(s) outside [0, 1]")
        if (rows["targets"] > rows["routes"]).any():
            errors.append("targets > routes on some row")
        if (rows["open_routes"] > rows["routes"]).any():
            errors.append("open_routes > routes on some row")
        wide = rows.pivot_table(index="nflId", columns="split", values="routes",
                                aggfunc="sum", fill_value=0)
        for sp in SPLITS:
            if sp not in wide.columns:
                wide[sp] = 0
        if ((wide["Man"] + wide["Zone"]) > wide["All"]).any():
            errors.append("Man + Zone routes exceed All routes for some receiver")
        toe_null = rows["toe"].isna()
        if payload["status"]["toe"] == "pending" and not toe_null.all():
            errors.append("status.toe is pending but some toe values are set")
        if payload["status"]["toe"] == "available":
            if toe_null.any():
                errors.append("status.toe is available but some toe values are null")
            total = rows.loc[rows["split"] == "All", "toe"].astype(float).sum()
            if abs(total) >= 0.05:
                errors.append(f"sum of All-split toe is {total:.4f}, expected ~0")
    flow_df = pd.DataFrame(payload["instead_flows"])
    if not flow_df.empty:
        for panel, share in flow_df.groupby("coverage_type")["share"].sum().items():
            if abs(share - 1) > 1e-3:
                errors.append(f"instead flow shares in panel {panel} sum to {share:.4f}")
    if errors:
        raise AssertionError("dashboard payload failed checks:\n  - " + "\n  - ".join(errors))


def write_payload(payload: dict, out_path: Path) -> int:
    """Strict JSON (no NaN), size-capped, atomic write. Returns the byte size."""
    text = json.dumps(payload, allow_nan=False, separators=(",", ":"))
    data = text.encode("utf-8")
    if len(data) > MAX_BYTES:
        raise ValueError(f"dashboard.json would be {len(data):,} bytes (> {MAX_BYTES:,})")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out_path.parent, prefix=".dashboard-", suffix=".json")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, out_path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return len(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixtures", action="store_true",
                        help="read out/fixtures/ (synthetic) instead of out/")
    parser.add_argument("--derived-dir", type=Path, default=None,
                        help="directory holding the contract parquet files")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    cfg = Config()
    derived_dir = args.derived_dir or (cfg.derived_dir / "fixtures" if args.fixtures
                                       else cfg.derived_dir)
    payload = build_payload(derived_dir, cfg, fixtures=args.fixtures)
    check_payload(payload)
    size = write_payload(payload, args.out)

    src, status, counts = payload["sources"], payload["status"], payload["counts"]
    print(f"routes:    {src['routes']} ({counts['routes']} routes, "
          f"{counts['model_plays']} model plays, {counts['receivers']} receivers)")
    print(f"receivers: {status['receivers']} from {src['receivers']} "
          f"({len(payload['receivers'])} rows); toe: {status['toe']}")
    print(f"offense:   {status['offense']} from {src['offense']} ({len(payload['offense'])} teams)")
    print(f"instead:   {status['instead']} from {src['instead']} "
          f"({counts['ignored_open_events']} events, {len(payload['instead_flows'])} flows)")
    print(f"wrote {_rel(args.out)} ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
