"""All-game Data_Report from play-level logic only (Requirements 1-5 + receiver counts).

Does not wait for the C1 snapshot table: one narrow, parallel pass over the
tracking files gives event frames, the direction check and the tracking
roster; everything else is plays/scouting/players.

    report = build_full_report()        # all 122 games
    write_full_report(report)           # merge into results/data_report.json

Run `python report.py` to do both and also write
out/play_events_targets_all.parquet and out/eligible_receivers_all.parquet.
"""

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

import load
import snapshot
import targets

KEYS = ["gameId", "playId"]
SCAN_COLUMNS = ["gameId", "playId", "nflId", "frameId", "team", "playDirection", "x", "event"]
MATCH_RATE_WARN = 0.85
ROUTE_MINIMUMS = {"Route_Minimum": 100, "Split_Route_Minimum": 40, "Team_Route_Minimum": 50}
LIST_CAP = 20
WORKERS = min(6, os.cpu_count() or 1)


# ---------------------------------------------------------------- tracking pass

def _scan_game(game_id, game_plays):
    """One game: event frames, direction check per play and roster from one narrow read."""
    try:
        trk = pd.read_csv(load.DATA_DIR / "tracking" / f"tracking_{int(game_id)}.csv",
                          usecols=SCAN_COLUMNS,
                          dtype={"gameId": "int64", "playId": "int64", "nflId": "Int64",
                                 "frameId": "int64", "event": "object"},
                          na_values=["NA"])
        trk = load.standardize(trk)
        frames = snapshot.event_frames(trk)
        per_play = load.direction_check(trk, load.add_los_x(game_plays, trk))
        roster = (trk.loc[trk["team"].ne("football"), KEYS + ["nflId", "team"]]
                  .drop_duplicates())
        return frames, per_play, roster, None
    except Exception as exc:  # Req 8.5: record and continue
        return None, None, None, {"gameId": int(game_id), "error": f"{type(exc).__name__}: {exc}"}


def scan_all(plays, game_ids, workers=WORKERS):
    """Parallel _scan_game over game_ids; returns (frames, per_play, roster, errors)."""
    by_game = {g: p for g, p in plays.groupby("gameId")}
    empty = plays.iloc[0:0]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_scan_game, game_ids,
                                [by_game.get(g, empty) for g in game_ids]))
    cat = lambda i: pd.concat([r[i] for r in results if r[i] is not None],  # noqa: E731
                              ignore_index=True)
    return cat(0), cat(1), cat(2), [r[3] for r in results if r[3] is not None]


# ---------------------------------------------------------------- sections

def _quantiles(s, qs=(0.25, 0.5, 0.75, 0.9)):
    out = {f"p{int(q * 100)}": round(float(s.quantile(q)), 2) for q in qs} if len(s) else {}
    out["max"] = int(s.max()) if len(s) else None
    return out


def direction_section(per_play, frames, game_ids):
    """R2.7/2.8 across all games, plus how many tracked plays have no snap event."""
    return {"games": len(game_ids),
            **load.direction_summary(per_play),
            "ball_los_tolerance_yd": load.BALL_LOS_TOLERANCE,
            "info_tolerance_yd": load.BALL_LOS_INFO_TOLERANCE,
            "min_share": load.DIRECTION_MIN_SHARE,
            "tracked_plays": int(len(frames)),
            "tracked_plays_without_snap": int(frames["snap_frameId"].isna().sum())}


def events_section(events, errors):
    """R3.4/3.5: passResult counts, Throw_Plays, exclusions by reason, time_to_throw_s."""
    rep = snapshot.events_report(events, errors)
    excluded = events[events["exclusion_reason"].notna()]
    by_reason = {}
    for reason, grp in excluded.groupby("exclusion_reason"):
        by_reason[reason] = {
            "count": int(len(grp)),
            "plays": [{"gameId": int(r.gameId), "playId": int(r.playId),
                       "passResult": r.passResult} for r in grp.head(LIST_CAP).itertuples()]}
    ttt = events.loc[events["is_throw_play"], "time_to_throw_s"]
    return {
        "plays": rep["plays"],
        "passResult_counts": rep["passResult_counts"],
        "candidates_C_I_IN": rep["candidates_C_I_IN"],
        "throw_plays": rep["throw_plays"],
        "exclusions": by_reason,
        "sack_plays_excluded": rep["sack_plays_excluded"],
        "scramble_plays_excluded": rep["scramble_plays_excluded"],
        "time_to_throw_s": {"min": float(ttt.min()), "p25": float(ttt.quantile(0.25)),
                            "median": float(ttt.median()), "p75": float(ttt.quantile(0.75)),
                            "max": float(ttt.max()),
                            "n_under_0_5": int((ttt < 0.5).sum()),
                            "n_over_10": int((ttt > 10).sum())},
        "tracking_load_errors": rep["tracking_load_errors"],
    }


def eligibility_section(runners, events, elig):
    """R4.3/4.4, plus Pass Route rows dropped by the tracking team check."""
    rep = snapshot.eligibility_report(runners, events, elig)
    off_team = runners["position_ok"] & ~runners["is_eligible"]
    rep["pass_route_not_on_possession_team_all_plays"] = int(off_team.sum())
    return rep


def targets_section(tbl, plays, req5):
    """R5.6/5.7/5.9 with lists capped, and 10 sample unmatched descriptions."""
    th = tbl[tbl["is_throw_play"]]
    not_elig = req5["matched_target_not_eligible"]
    unmatched = th[th["target_nflId"].isna()].merge(plays[KEYS + ["playDescription"]], on=KEYS)
    sample = unmatched.sample(min(10, len(unmatched)), random_state=0)
    rate = req5["match_rate"]
    if rate < MATCH_RATE_WARN:
        print(f"WARNING: target match rate {rate:.1%} < {MATCH_RATE_WARN:.0%}")
    rt = req5["round_trip"]
    return {
        "throw_plays": req5["throw_plays"],
        "matched_targets": req5["matched_targets"],
        "match_rate": rate,
        "match_rate_below_85pct": bool(rate < MATCH_RATE_WARN),
        "match_status_counts": req5["match_status_counts"],
        "model_plays": req5["model_plays"],
        "not_model_play_reasons": req5["not_model_play_reasons"],
        "matched_target_not_eligible": {
            "count": len(not_elig),
            "by_reason": pd.Series([r["reason"] for r in not_elig], dtype="object")
            .value_counts().astype(int).to_dict(),
            "plays": not_elig[:LIST_CAP]},
        "multiple_pass_phrases": req5["multiple_pass_phrases"],
        "round_trip": {**{k: rt[k] for k in ("checked", "passed", "pass_rate",
                                              "skipped_non_unique_key")},
                       "failures": rt["failures"][:LIST_CAP]},
        "samples_unmatched": [{"gameId": int(r.gameId), "playId": int(r.playId),
                               "match_status": r.match_status,
                               "playDescription": r.playDescription}
                              for r in sample.itertuples()],
    }


def _per_receiver(rows):
    return rows.groupby(["nflId", "position_group"]).size().rename("routes").reset_index()


def _route_stats(per):
    out = {"distinct_receivers": int(len(per)), "routes": int(per["routes"].sum()),
           "routes_per_receiver": _quantiles(per["routes"])}
    for name, n in ROUTE_MINIMUMS.items():
        out[f"receivers_ge_{n}_routes"] = int((per["routes"] >= n).sum())
    return out


def players_section(elig, tbl, plays, top_n=15):
    """Routes per Eligible_Receiver on Model_Plays (and all Throw_Plays) for Route_Minimum."""
    model_keys = tbl.loc[tbl["is_model_play"], KEYS]
    routes = elig.merge(model_keys, on=KEYS)
    out = {"route_definition": "Eligible_Receiver on a Model_Play",
           "route_minimum_defaults": ROUTE_MINIMUMS}
    for label, rows in (("model_plays", routes), ("throw_plays", elig)):
        per = _per_receiver(rows)
        out[label] = {"overall": _route_stats(per),
                      "by_position_group": {g: _route_stats(p) for g, p in
                                            per.groupby("position_group")}}

    per = _per_receiver(routes)
    tgt = (tbl[tbl["is_model_play"]].groupby("target_nflId").size().rename("targets"))
    team = (routes.merge(plays[KEYS + ["possessionTeam"]], on=KEYS)
            .groupby(["nflId", "possessionTeam"]).size().rename("n").reset_index()
            .sort_values(["nflId", "n"], ascending=[True, False])
            .drop_duplicates("nflId").set_index("nflId")["possessionTeam"])
    names = elig.drop_duplicates("nflId").set_index("nflId")["displayName"]
    thr = elig.groupby("nflId").size()
    top = per.sort_values(["routes", "nflId"], ascending=[False, True]).head(top_n)
    out["top_receivers"] = [
        {"nflId": int(r.nflId), "displayName": names.get(r.nflId),
         "position_group": r.position_group, "team": team.get(r.nflId),
         "routes": int(r.routes), "targets": int(tgt.get(r.nflId, 0)),
         "throw_play_routes": int(thr.get(r.nflId, 0))}
        for r in top.itertuples()]
    return out


# ---------------------------------------------------------------- checks

def consistency_checks(report, tbl, elig):
    """Internal consistency of the counts; returns {check: bool}."""
    ev, tg, pl = report["events"], report["targets"], report["players"]
    n_excl = sum(v["count"] for v in ev["exclusions"].values())
    model_routes = int(elig.merge(tbl.loc[tbl["is_model_play"], KEYS], on=KEYS).shape[0])
    by_group = pl["model_plays"]["by_position_group"]
    return {
        "throw_plays_plus_exclusions_eq_plays":
            ev["throw_plays"] + n_excl == report["counts"]["plays"],
        "model_le_matched_le_throw":
            tg["model_plays"] <= tg["matched_targets"] <= tg["throw_plays"],
        "events_throw_plays_eq_targets_throw_plays": ev["throw_plays"] == tg["throw_plays"],
        "model_routes_eq_elig_rows_on_model_plays":
            pl["model_plays"]["overall"]["routes"] == model_routes,
        "group_routes_sum_eq_overall":
            sum(g["routes"] for g in by_group.values()) == pl["model_plays"]["overall"]["routes"],
        "throw_routes_eq_elig_rows":
            pl["throw_plays"]["overall"]["routes"] == len(elig),
        "passResult_matches_reference":
            ev["passResult_counts"] == {"C": 4620, "I": 2755, "IN": 190, "S": 543, "R": 449},
        "direction_C_I_IN_ge_99pct": all(
            report["direction_check"]["passResult_C_I_IN"][k] >= load.DIRECTION_MIN_SHARE
            for k in ("ball_near_los_share", "sides_split_share")),
        "match_rate_ge_85pct": tg["match_rate"] >= MATCH_RATE_WARN,
        "no_tracking_load_errors": not ev["tracking_load_errors"],
    }


# ---------------------------------------------------------------- build / write

def build_full_report(game_ids=None, return_tables=False):
    """Data_Report dict for `game_ids` (None = every tracking file).

    With return_tables=True, returns (report, play_table, eligible_receivers).
    """
    t0 = time.time()
    games, plays_all = load.load_games(), load.load_plays()
    players, scouting = load.load_players(), load.load_scouting()
    report = load.build_data_report(games, plays_all, players, scouting)

    if game_ids is None:
        game_ids = [int(p.stem.split("_")[1]) for p in load.tracking_files()]
    plays = plays_all[plays_all["gameId"].isin(game_ids)].reset_index(drop=True)

    frames, per_play, roster, errors = scan_all(plays, game_ids)
    report["direction_check"] = direction_section(per_play, frames, game_ids)
    t_scan = time.time() - t0

    events = snapshot.classify_plays(plays, frames)
    runners = snapshot.route_runners(plays, scouting, players, roster=roster)
    elig = snapshot.eligible_receivers(runners, events)
    tbl, req5 = targets.assign_targets(events, plays, scouting, players, elig)

    report["events"] = events_section(events, errors)
    report["eligibility"] = eligibility_section(runners, events, elig)
    report["targets"] = targets_section(tbl, plays, req5)
    report["players"] = players_section(elig, tbl, plays)
    report["checks"] = consistency_checks(report, tbl, elig)
    report["full_report_runtime_s"] = {"tracking_scan": round(t_scan, 1),
                                       "total": round(time.time() - t0, 1),
                                       "workers": WORKERS}
    failed = [k for k, ok in report["checks"].items() if not ok]
    if failed:
        print("WARNING: failed checks: " + ", ".join(failed))
    return (report, tbl, elig) if return_tables else report


def write_full_report(report, path=None):
    """Merge `report` into the existing Data_Report JSON (its keys win) and write it."""
    path = Path(path) if path else load.RESULTS_DIR / "data_report.json"
    merged = json.loads(path.read_text()) if path.exists() else {}
    merged.update(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2, default=str) + "\n")
    return path


if __name__ == "__main__":
    report, tbl, elig = build_full_report(return_tables=True)
    load.OUT_DIR.mkdir(parents=True, exist_ok=True)
    tbl[targets.PLAY_COLUMNS].to_parquet(load.OUT_DIR / "play_events_targets_all.parquet",
                                         index=False)
    elig.to_parquet(load.OUT_DIR / "eligible_receivers_all.parquet", index=False)
    path = write_full_report(report)

    ev, tg, pl = report["events"], report["targets"], report["players"]["model_plays"]
    print(f"throw_plays {ev['throw_plays']}  match_rate {tg['match_rate']:.2%}  "
          f"model_plays {tg['model_plays']}")
    print("receivers by group:", {g: v["distinct_receivers"]
                                  for g, v in pl["by_position_group"].items()},
          f"100+: {pl['overall']['receivers_ge_100_routes']}  "
          f"40+: {pl['overall']['receivers_ge_40_routes']}")
    print("checks:", {k: v for k, v in report["checks"].items()})
    print(f"wrote {path}, out/play_events_targets_all.parquet ({len(tbl)} rows), "
          f"out/eligible_receivers_all.parquet ({len(elig)} rows) "
          f"in {report['full_report_runtime_s']['total']}s")
