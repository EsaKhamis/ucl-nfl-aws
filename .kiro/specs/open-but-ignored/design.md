# Design Document: Open but Ignored vs. Over-Targeted

Written 10:30, 9 Oct. This document settles what the requirements leave open: files, owners, paths, formats, formulas and interfaces. Dev 1 = Person A (Data), Dev 2 = Person B (Metrics), Dev 3 = Person C (Story).

## Environment

- Use `/Users/esakhamis/anaconda3/bin/python3.12`, or a venv built from it. The system `python3` is 3.9.6 and has no pandas.
- Installed and verified at 10:30. Pin exactly these in `requirements.txt`: `pandas==2.2.2`, `numpy==1.26.4`, `matplotlib==3.9.2`, `scikit-learn==1.5.1`, `pyarrow==16.1.0`.
- Don't use `nfl_data_py`. Read nflverse straight from the release parquet with pandas (see C7), so there's no extra dependency.
- Don't use `DataFrame.to_markdown()`, because it needs `tabulate`, which isn't installed. Write Markdown tables with a small helper.

## Layout and ownership

Flat modules at the repo root, matching the existing `load.py`. Each file has exactly one owner. To change someone else's file, ask them.

| File | Owner | Contents | Reqs |
| --- | --- | --- | --- |
| `config.py` | Dev 1 | The `Config` dataclass below, pushed once by 10:40 with every field. Others ask for changes; they don't edit it | all |
| `run.py` | Dev 1 | CLI that calls each stage's `build(cfg)` | 8, 25.5 |
| `load.py` | Dev 1 | Exists: loaders and `standardize()`. Add the Appendix A schema check and Data_Report counts | 1, 2 |
| `snapshot.py` | Dev 1 | Events, eligibility, C1, C2, `build(cfg)` | 3, 4, 6, 7, 8 |
| `targets.py` | Dev 1 | Description parsing, name matching, optional nflverse fill | 5, 10 |
| `contracts_data.py` | Dev 1 | Shared `validate()`, C1/C2 schemas, `fixture_c1c2()` | 9 |
| `features.py` | Dev 2 | Separation, closing speed, openness, depth, pressure | 11–13, 23 |
| `model.py` | Dev 2 | Expected-target model and CV | 14, 19 |
| `aggregate.py` | Dev 2 | C3–C6, `build(cfg)` | 15–18, 21, 22, 24 |
| `contracts_metrics.py` | Dev 2 | C3–C6 schemas, `fixture_c3c6()` (imports `validate` from `contracts_data`) | 20 |
| `plots.py` | Dev 3 | `plot_play(game_id, play_id, offset, c1, c2, c3=None)` | 26 |
| `charts.py` | Dev 3 | All charts, leaderboards, Headline_Summary, `build(cfg)` | 27–32, 34 |
| `nflverse.py` | Dev 3 | C7 fetch and join | 33 |
| `README.md`, `.gitignore`, `requirements.txt` | Dev 3 | | 25, 32 |

## Directories and files

| Dir | Git | Contents |
| --- | --- | --- |
| `data/` | ignored (already) | Raw CSVs as distributed |
| `out/` | ignored (already) | **Derived_Dir.** `c1_snapshot.parquet`, `c2_plays.parquet`, `c3_routes.parquet`, `c4_receiver_toe.parquet`, `c5a_offense.parquet`, `c5b_defense.parquet`, `c6_instead.parquet`, `c7_pbp.parquet`; `out/fixtures/` (same names); `out/cache/` (downloads) |
| `results/` | committed | **Outputs_Dir.** `data_report.json` (Dev 1), `model_report.json` (Dev 2), `headline_summary.json` (Dev 3), `headline.png`, `team_toe.png`, `instead.png`, `coverage_profile.png`, `leaderboard_over.{csv,md}`, `leaderboard_ignored.{csv,md}` |

`plan.md` was written before the event and must not be in the submission, so add it to `.gitignore`. `.kiro/specs/` was written on-site and stays in, since it shows the Kiro workflow.

## Config

```python
# config.py (Dev 1 owns; push by 10:40)
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Config:
    data_dir: Path = Path("data")
    derived_dir: Path = Path("out")
    outputs_dir: Path = Path("results")
    games: list[int] | None = None      # None = every tracking file
    rebuild: bool = False
    fixtures: bool = False              # stages read out/fixtures/ instead of out/
    pre_release_offset: int = 4         # 3, 4 or 5 (Req 12.4)
    open_mode: str = "most_open"        # or "threshold"
    open_threshold: float = 3.0         # yards; set from the data on the day
    closing_horizon_s: float = 0.5      # Openness_Score horizon
    route_minimum: int = 100
    split_route_minimum: int = 40
    team_route_minimum: int = 50
    headline_x: str = "open_rate"       # or "expected_share" (Req 27.8)
    use_nflverse: bool = False
    pressure_split: bool = False
    down_distance: bool = False
    yac_allowance: float = 0.0
    orientation: bool = False
    recent_proxy: bool = False
```

## Run command and stage interface

`python run.py` runs data, then metrics, then story, on all games.

| Flag | Effect |
| --- | --- |
| `--games 2021090900 ...` | Subset (Req 8.1) |
| `--rebuild` | Ignore cached `out/` tables (Req 8.4) |
| `--stage data\|metrics\|story` | Run one stage only, reading the previous stage's tables from `out/` |
| `--fixtures` | Write fixtures to `out/fixtures/`, then have metrics and story read from there |

Each stage exposes `build(cfg: Config) -> None`: `snapshot.build`, `aggregate.build`, `charts.build`. A stage reads its inputs from disk and validates them. It then writes its outputs, validates them, and runs its invariant asserts. Dev 1 pushes `run.py` with all three stages stubbed by 10:40, so nobody else has to edit it.

## Data stage (Dev 1)

- **LOS_x** is `absoluteYardlineNumber` when `playDirection` is "right" and `120 − absoluteYardlineNumber` when it's "left". Line_to_Gain_x = LOS_x + `yardsToGo`.
  - Checked on game 2021090900 (97 plays). At the snap, the ball sits a median 0.44 yd behind LOS_x. 95.9% of plays are within 1.5 yd and 100% within 3 yd. Req 2.7's tolerance is therefore 2.5 yd, amended in requirements.md.
- **Tracking:** read each game with `usecols` set to the Appendix A columns. Standardize, find the snap and release frames, and keep only the snapshot frames of Throw_Plays. Concatenate at the end. If all 122 games take more than 10 min, map games over a `concurrent.futures.ProcessPoolExecutor`.
- **Snapshot frame:** `frameId = max(release − offset, snap)` and `clamped = (release − offset < snap)`.
- **Eligibility:** join tracking × scouting on (`gameId`, `playId`, `nflId`), then × players on `nflId`.
- **Target parsing:**
  - Take the name after "to" or "intended for" that follows the pass phrase ("pass short left to C.Godwin to TB 24", "pass incomplete deep right to M.Evans.").
  - Normalized key: first initial + last name, lowercased, with spaces, dots, apostrophes and hyphens removed, and Jr/Sr/II/III/IV dropped. "A.St. Brown" gives (a, stbrown).
  - For `displayName`, the initial is the first character and the last name is everything after the first token. "Amon-Ra St. Brown" also gives (a, stbrown).
  - Fallback: match on the last name alone when it's unique among the play's offensive players.
  - Test on 20 random descriptions before running all games.
- **Data_Report:** write it to `results/data_report.json` with the counts, exclusions and reasons, the match rate, Model_Play count, and the integrity shares (Req 2.7, 2.8).

## Metrics stage (Dev 2)

- **Velocity:** `vx = s·sin(dir°)`, `vy = s·cos(dir°)`. Confirm on one frame that a player running toward +x has `dir` ≈ 90.
- **Separation:** `min over defenders ‖p_d − p_r‖`. Vectorize per frame with numpy broadcasting.
- **Closing_Speed:** `−(p_d − p_r)·(v_d − v_r) / ‖p_d − p_r‖` for the Nearest_Defender. Positive means closing.
- **Openness_Score:** `separation − closing_horizon_s × closing_speed`, the projected separation 0.5 s later.
  - It increases with separation and decreases with closing speed, which satisfies Req 12.2 and 12.3.
  - Distances and dot products survive the 180° flip, which satisfies Req 11.5.
- **Depth, depth_vs_sticks, dist_from_qb:** at the Pre_Release_Offset, as in Req 13. The QB is the `qb_nflId` row in C1.
- **Rusher_Distance:** the minimum distance from the QB to any `pff_role` "Pass Rush" row at offset 0.
- **Model:** sklearn `make_pipeline(StandardScaler(), LogisticRegression())`.
  - Features: `openness_pre`, `depth`, `dist_from_qb`, `rusher_distance × depth`, `rusher_distance × dist_from_qb`. Req 14.1 is amended: Rusher_Distance is the same for every route on a play, so after within-play normalization it can only act through interactions.
  - Fill missing values with the median before building the interactions.
  - `xtarget = p / Σp` within each play.
  - Fit on all Model_Plays to produce TOE.
  - Evaluate with `GroupKFold(5)` on `gameId`, using out-of-fold normalized xTarget. Report log loss, AUC and top-1 accuracy (argmax xTarget = target).
  - Write coefficients and fold metrics to `results/model_report.json`.
- **Aggregation:** follows Req 16–18. A receiver's `team` is the `possessionTeam` where he has the most Routes. `xtarget_rel` (Req 19) is nullable until the P1 work is done.

## Story stage (Dev 3)

- **Headline chart:** matplotlib with two panels (Man, Zone) and `sharex=True, sharey=True`.
  - Okabe-Ito colors with distinct markers: WR `#0072B2` circle, TE `#E69F00` square, RB `#009E73` triangle.
  - Label the 5 receivers with the highest and the 5 with the lowest `target_share − open_rate` in each panel.
  - Read the title from `headline_summary.json`.
  - Save `results/headline.png` at 200 dpi.
- **Headline_Summary:** written by Dev 3 at 12:15, after Dev 2 and Dev 3 pick the finding from C4 and C5 at 12:00. Every number in the README and the title comes from this file.
- **nflverse (C7):**
  - Load with `pd.read_parquet("https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2021.parquet")` and cache it to `out/cache/`.
  - Cast `old_game_id` to int and join it to `gameId`; join `play_id` to `playId`.
  - Use the season of the event dataset.
- **Play_Plotter:** used for the 11:00–11:45 sanity checks on 5 plays. Save the images to `out/` (not committed).

## Contracts, validation, fixtures

- Dev 1 writes `validate(df, schema, key, name)` in `contracts_data.py` by 10:45.
  - A schema is `{column: (kind, nullable, allowed_values_or_None)}`, where `kind` is one of "int", "float", "str" or "bool".
  - The function collects every violation, including key uniqueness, and raises once with the full list.
- Invariants are plain `assert`s at the end of the producer's `build()`: Req 9.4–9.5, 14.4, 15.2–15.3, 16.7–16.9, 17.5 and 18.3–18.5.
- There's no separate test suite within the time box. The fixtures, validators and asserts serve as the tests.
- Fixtures are seeded numpy random tables that pass validation and the invariants:
  - C1/C2: 3 plays × 6 offsets × 23 rows.
  - C3–C6: 20 or more receivers on 4 teams.
- `python run.py --fixtures --stage story` must work by 11:00.

## Scope rule

- **Until 11:45:** P0 only.
- **P1:**
  - Dev 2 builds C5 and C6 only if C4 is done on all games by 12:00.
  - Dev 3 builds one P1 chart (team small multiples first), and only once the headline and leaderboards are working.
- **Optional items:** only after P0 and P1 are done and before 12:15.

## Checkpoints

| Time | Gate |
| --- | --- |
| 10:40 | `config.py`, `run.py` stubs, `.gitignore`, `requirements.txt` pushed. Repo public |
| 10:45 | `validate()` and both fixture functions pushed (signatures and columns at minimum) |
| 11:00 | One-game C1/C2 in `out/`. Story runs on fixtures |
| 11:30 | All-game C1/C2 and Data_Report |
| 11:45 | C3/C4 on all games. Route quartiles reported, Route_Minimum set |
| 12:15 | Analysis freeze. Headline_Summary written |
| 12:45 | Clean clone runs `python run.py` end to end |
