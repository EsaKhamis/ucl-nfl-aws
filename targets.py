"""Recover the targeted receiver from playDescription (Requirement 5).

Plain functions only; nothing runs at import time.

    parsed = parse_targets(plays)                  # target_name_raw per play
    cands = offense_candidates(scouting, players)  # offensive players per play
    matched = match_targets(parsed, cands)         # target_nflId, match_status

Run `python targets.py [--game 2021090900]` to write
out/play_events_targets.parquet, out/eligible_receivers.parquet and
out/data_report_events_targets.json.
"""

import argparse
import json
import re
import time

import numpy as np
import pandas as pd

import load
import snapshot

KEYS = ["gameId", "playId"]
SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}

# Description names: "C.Godwin", "Aa.Rodgers", "Dj.Moore", "A.St. Brown",
# "D.Smith-Schuster", "J.O'Shaughnessy" (optionally followed by a suffix).
NAME = (r"[A-Z][A-Za-z']*\.\s?(?:St\.\s?)?[A-Z][A-Za-z'\-]*"
        r"(?:\s(?:Jr|Sr|II|III|IV)\b\.?)?")
# Only a "to"/"intended for" that directly follows the pass phrase counts, so
# "to TB 45", tacklers in parentheses and "INTERCEPTED by X" are never taken.
PASS_TARGET_RE = re.compile(
    r"\bpass(?: incomplete)?(?: (?:short|deep))?(?: (?:left|middle|right))?"
    r" (?:to|intended for) (?P<name>" + NAME + ")"
)
_STRIP_RE = re.compile(r"[\s.'\-]")


# ---------------------------------------------------------------- name keys

def _norm_last(text):
    """Lowercase, drop Jr/Sr/II/III/IV tokens, remove spaces, dots, apostrophes, hyphens."""
    tokens = [t for t in str(text).split() if t.lower().strip(".,") not in SUFFIXES]
    return _STRIP_RE.sub("", " ".join(tokens).lower())


def description_key(name):
    """(initial, last) for a description name: 'A.St. Brown' -> ('a', 'stbrown')."""
    if not isinstance(name, str) or "." not in name:
        return (None, None)
    prefix, last = name.split(".", 1)
    return (prefix[:1].lower(), _norm_last(last))


def display_key(display_name):
    """(initial, last) for players.displayName: 'Amon-Ra St. Brown' -> ('a', 'stbrown')."""
    tokens = str(display_name).split()
    last = " ".join(tokens[1:]) if len(tokens) > 1 else tokens[0]
    return (tokens[0][:1].lower(), _norm_last(last))


def description_style(display_name):
    """displayName in playDescription style: 'Chris Godwin' -> 'C.Godwin', suffix dropped."""
    tokens = str(display_name).split()
    last = [t for t in tokens[1:] if t.lower().strip(".,") not in SUFFIXES] or tokens[:1]
    return f"{tokens[0][:1].upper()}.{' '.join(last)}"


# ---------------------------------------------------------------- parsing

def extract_target_name(description):
    """(name, n_occurrences): the last 'pass ... to/intended for <name>' in the text.

    The last occurrence is the final, accepted play when a play was reversed
    or re-described. 'pass incomplete' with no name gives (None, 0).
    """
    if not isinstance(description, str):
        return (None, 0)
    names = [m.group("name") for m in PASS_TARGET_RE.finditer(description)]
    return (names[-1] if names else None, len(names))


def parse_targets(plays):
    """gameId, playId, playDescription, target_name_raw, n_name_phrases, distinct_names."""
    out = plays[KEYS + ["playDescription"]].copy()
    all_names = [[m.group("name") for m in PASS_TARGET_RE.finditer(d)] if isinstance(d, str)
                 else [] for d in out["playDescription"]]
    out["target_name_raw"] = [n[-1] if n else None for n in all_names]
    out["n_name_phrases"] = [len(n) for n in all_names]
    out["distinct_names"] = [len(set(n)) for n in all_names]
    keys = [description_key(n) for n in out["target_name_raw"]]
    out["key_initial"] = [k[0] for k in keys]
    out["key_last"] = [k[1] for k in keys]
    return out


# ---------------------------------------------------------------- matching

def offense_candidates(scouting, players):
    """Offensive players per play (pff_role Pass / Pass Route / Pass Block) with name keys."""
    off = scouting.loc[scouting["pff_role"].isin(snapshot.OFFENSE_ROLES),
                       KEYS + ["nflId", "pff_role"]]
    names = players[["nflId", "displayName", "officialPosition"]].copy()
    keys = [display_key(n) for n in names["displayName"]]
    names["key_initial"] = [k[0] for k in keys]
    names["key_last"] = [k[1] for k in keys]
    return off.merge(names, on="nflId", how="left")


def match_targets(parsed, cands):
    """One row per parsed play: target_nflId and match_status.

    Initial + last name first. If that finds nobody, fall back to the last
    name alone when it is unique among the play's offensive players.
    match_status: matched, matched_last_name, no_name, no_match, ambiguous.
    """
    p = parsed[KEYS + ["key_initial", "key_last"]]
    full = p.merge(cands[KEYS + ["key_initial", "key_last", "nflId"]],
                   on=KEYS + ["key_initial", "key_last"])
    full_n = full.groupby(KEYS)["nflId"].agg(["size", "first"])
    last = p.merge(cands[KEYS + ["key_last", "nflId"]], on=KEYS + ["key_last"])
    last_n = last.groupby(KEYS)["nflId"].agg(["size", "first"])

    out = parsed[KEYS].copy()
    idx = pd.MultiIndex.from_frame(out[KEYS])
    n_full = full_n["size"].reindex(idx).fillna(0).to_numpy()
    n_last = last_n["size"].reindex(idx).fillna(0).to_numpy()
    id_full = full_n["first"].reindex(idx).to_numpy()
    id_last = last_n["first"].reindex(idx).to_numpy()
    has_name = parsed["target_name_raw"].notna().to_numpy()

    status = np.select(
        [~has_name, n_full == 1, n_full > 1, n_last == 1, n_last > 1],
        ["no_name", "matched", "ambiguous", "matched_last_name", "ambiguous"],
        default="no_match",
    )
    nfl = np.where(status == "matched", id_full,
                   np.where(status == "matched_last_name", id_last, pd.NA))
    out["target_nflId"] = pd.array(nfl, dtype="Int64")
    out["match_status"] = status
    return out


def model_play_flags(events, matched, cands, elig):
    """is_model_play and model_play_reason (NA on Model_Plays), aligned to `events`."""
    m = events[KEYS + ["is_throw_play"]].merge(matched, on=KEYS, how="left")
    is_elig = m[KEYS + ["target_nflId"]].merge(
        elig[KEYS + ["nflId"]].assign(_e=True),
        left_on=KEYS + ["target_nflId"], right_on=KEYS + ["nflId"], how="left")["_e"]
    is_elig = is_elig.eq(True).to_numpy()
    info = m[KEYS + ["target_nflId"]].merge(
        cands[KEYS + ["nflId", "pff_role", "officialPosition"]],
        left_on=KEYS + ["target_nflId"], right_on=KEYS + ["nflId"], how="left")
    has_target = m["target_nflId"].notna().to_numpy()
    model = m["is_throw_play"].to_numpy() & has_target & is_elig
    not_elig = ("target_not_eligible: pff_role=" + info["pff_role"].fillna("NA")
                + ", officialPosition=" + info["officialPosition"].fillna("NA")).to_numpy()
    reason = np.select(
        [model, ~m["is_throw_play"].to_numpy(), m["match_status"].eq("no_name").to_numpy(),
         m["match_status"].eq("no_match").to_numpy(),
         m["match_status"].eq("ambiguous").to_numpy(), has_target & ~is_elig],
        [None, "not_throw_play", "no_target_name", "target_no_match", "target_ambiguous",
         not_elig],
        default="unknown",
    )
    return (pd.Series(model, index=events.index),
            pd.Series(reason, index=events.index, dtype="object"))


# ---------------------------------------------------------------- round trip

def round_trip(cands, throw_keys):
    """Req 5.9: format each uniquely-keyed offensive player as 'F.Lastname', parse, match."""
    c = cands.merge(throw_keys, on=KEYS)
    dup = c.duplicated(KEYS + ["key_initial", "key_last"], keep=False)
    u = c[~dup].copy()
    u["playDescription"] = ("(1:00) Q.Back pass short left to "
                            + u["displayName"].map(description_style)
                            + " to XX 30 for 5 yards (D.Fender).")
    u = u.reset_index(drop=True)
    u["_row"] = np.arange(len(u))
    parsed = parse_targets(u.assign(playId=u["_row"])[["gameId", "playId", "playDescription"]])
    cand_rt = c[KEYS + ["key_initial", "key_last", "nflId"]]
    # Match each synthetic row against its own play's offensive players.
    p = parsed[["playId", "key_initial", "key_last", "target_name_raw"]].rename(
        columns={"playId": "_row"}).merge(u[["_row"] + KEYS + ["nflId", "displayName"]],
                                          on="_row")
    hits = p.merge(cand_rt.rename(columns={"nflId": "hit"}),
                   on=KEYS + ["key_initial", "key_last"], how="left")
    n = hits.groupby("_row")["hit"].agg(["count", "first"])
    p["ok"] = (n["count"].reindex(p["_row"]).to_numpy() == 1) & (
        n["first"].reindex(p["_row"]).to_numpy() == p["nflId"].to_numpy())
    fails = p[~p["ok"]]
    return {
        "checked": int(len(p)),
        "passed": int(p["ok"].sum()),
        "pass_rate": round(float(p["ok"].mean()), 6) if len(p) else None,
        "skipped_non_unique_key": int(dup.sum()),
        "failures": fails[["gameId", "playId", "nflId", "displayName", "target_name_raw"]]
        .drop_duplicates(["nflId"]).head(50).astype(object).where(fails.notna(), None)
        .to_dict("records") if len(fails) else [],
    }


# ---------------------------------------------------------------- build

PLAY_COLUMNS = KEYS + [
    "passResult", "snap_frameId", "release_frameId", "time_to_throw_s", "is_throw_play",
    "is_sack", "is_scramble", "exclusion_reason", "n_eligible", "target_name_raw",
    "target_nflId", "target_source", "match_status", "is_model_play", "model_play_reason",
]


def build_play_table(plays, scouting, players, game_ids=None):
    """Return (play_table, eligible_receivers, report) for the plays in `plays`.

    Narrow path: events from gameId/playId/frameId/event only, eligibility from
    scouting role + position (snapshot.build adds the tracking team check).
    """
    frames, errors = snapshot.collect_event_frames(game_ids)
    events = snapshot.classify_plays(plays, frames)
    runners = snapshot.route_runners(plays, scouting, players)
    elig = snapshot.eligible_receivers(runners, events)
    tbl, req5 = assign_targets(events, plays, scouting, players, elig)
    report = {
        "games": "all" if game_ids is None else [int(g) for g in game_ids],
        "req_3": snapshot.events_report(events, errors),
        "req_4": snapshot.eligibility_report(runners, events, elig),
        "req_5": req5,
    }
    return tbl, elig, report


def assign_targets(events, plays, scouting, players, elig):
    """Play-level table (PLAY_COLUMNS + debug columns) and the Req 5 report fragment."""
    cands = offense_candidates(scouting, players)
    parsed = parse_targets(plays)
    matched = match_targets(parsed, cands)
    throw = events["is_throw_play"].to_numpy()
    tbl = events.merge(parsed[KEYS + ["target_name_raw", "n_name_phrases", "distinct_names"]],
                       on=KEYS, how="left").merge(matched, on=KEYS, how="left")
    # Targets are defined on Throw_Plays only; keep the raw name everywhere for debugging.
    tbl.loc[~throw, "target_nflId"] = pd.NA
    tbl.loc[~throw, "match_status"] = "not_throw_play"
    tbl["target_source"] = np.where(tbl["target_nflId"].notna(), "description", "none")
    tbl["n_eligible"] = snapshot.n_eligible(events, elig).to_numpy()
    model, reason = model_play_flags(events, tbl[KEYS + ["target_nflId", "match_status"]],
                                     cands, elig)
    tbl["is_model_play"] = model.to_numpy()
    tbl["model_play_reason"] = reason.to_numpy()
    req5 = targets_report(tbl, plays, cands)
    req5["round_trip"] = round_trip(cands, events.loc[throw, KEYS])
    return tbl, req5


def _samples(tbl, plays, cands, status, n=15, seed=0):
    rows = tbl[tbl["match_status"].eq(status)]
    rows = rows.sample(min(n, len(rows)), random_state=seed)
    desc = plays.set_index(KEYS)["playDescription"]
    out = []
    for r in rows.itertuples():
        names = cands.loc[cands["gameId"].eq(r.gameId) & cands["playId"].eq(r.playId),
                          "displayName"].tolist()
        out.append({"gameId": int(r.gameId), "playId": int(r.playId),
                    "target_name_raw": r.target_name_raw,
                    "playDescription": desc.loc[(r.gameId, r.playId)],
                    "offense": names})
    return out


def targets_report(tbl, plays, cands):
    """Data_Report fragment for Requirements 5.6 and 5.7 (+ debugging samples)."""
    th = tbl[tbl["is_throw_play"]]
    n_matched = int(th["target_nflId"].notna().sum())
    rate = n_matched / len(th) if len(th) else float("nan")
    not_elig = th[th["target_nflId"].notna() & ~th["is_model_play"]]
    multi = th[th["n_name_phrases"] > 1]
    rep = {
        "throw_plays": int(len(th)),
        "matched_targets": n_matched,
        "match_rate": round(rate, 4),
        "match_status_counts": {k: int(v) for k, v in th["match_status"].value_counts().items()},
        "model_plays": int(th["is_model_play"].sum()),
        "not_model_play_reasons": {k: int(v) for k, v in
                                   th["model_play_reason"].value_counts().items()},
        "matched_target_not_eligible": [
            {"gameId": int(r.gameId), "playId": int(r.playId),
             "target_nflId": int(r.target_nflId), "reason": r.model_play_reason}
            for r in not_elig.itertuples()],
        "multiple_pass_phrases": {"plays": int(len(multi)),
                                  "names_disagree": int((multi["distinct_names"] > 1).sum())},
        "samples_no_match": _samples(tbl, plays, cands, "no_match"),
        "samples_ambiguous": _samples(tbl, plays, cands, "ambiguous"),
        "samples_matched_last_name": _samples(tbl, plays, cands, "matched_last_name"),
    }
    if rate < 0.85:
        unmatched = th[th["target_nflId"].isna()].merge(plays[KEYS + ["playDescription"]],
                                                        on=KEYS)
        print(f"WARNING: target match rate {rate:.1%} < 85%. 20 unmatched descriptions:")
        for d in unmatched["playDescription"].sample(min(20, len(unmatched)), random_state=0):
            print("  ", d)
    return rep


def main():
    ap = argparse.ArgumentParser(description="Events, eligibility and targets (Req 3-5).")
    ap.add_argument("--game", type=int, help="one gameId for the prototype run")
    args = ap.parse_args()

    t0 = time.time()
    plays = load.load_plays()
    game_ids = None
    if args.game:
        plays = plays[plays["gameId"].eq(args.game)].reset_index(drop=True)
        game_ids = [args.game]
    tbl, elig, report = build_play_table(plays, load.load_scouting(), load.load_players(),
                                         game_ids)
    if args.game:
        report["req_4"]["team_cross_check"] = snapshot.team_cross_check(
            args.game, plays, load.load_scouting())
    report["runtime_s"] = round(time.time() - t0, 1)

    load.OUT_DIR.mkdir(parents=True, exist_ok=True)
    tbl[PLAY_COLUMNS].to_parquet(load.OUT_DIR / "play_events_targets.parquet", index=False)
    elig.to_parquet(load.OUT_DIR / "eligible_receivers.parquet", index=False)
    path = load.OUT_DIR / "data_report_events_targets.json"
    path.write_text(json.dumps(report, indent=2, default=str) + "\n")
    r3, r5 = report["req_3"], report["req_5"]
    print(f"plays {r3['plays']}  throw_plays {r3['throw_plays']}  "
          f"exclusions {r3['exclusion_reasons']}")
    print(f"match_rate {r5['match_rate']:.2%}  model_plays {r5['model_plays']}  "
          f"round_trip {r5['round_trip']['pass_rate']}")
    print(f"wrote out/play_events_targets.parquet, out/eligible_receivers.parquet, {path.name} "
          f"in {report['runtime_s']}s")


if __name__ == "__main__":
    main()
