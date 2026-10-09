# Task status (11:23, 9 Oct)

Reconciled against the repo at origin/main = d137591 (11:16, "push output for all plays"). Working tree is clean apart from tasks.md checkboxes. I only checked what's in the repo, so Dev 2/Dev 3 work that hasn't been pushed isn't counted.

Ticked this pass: 21 (by me). Between my read and my edit, someone else ticked 1, 2, 4, 5 and 6. I verified 2, 4, 5 and 6 as done. Task 1 still has a gap (see its row), but I left the tick because the rule is never to untick.

Previous board: out/task_status.md didn't exist, so this is a fresh board.

| # | Owner | Status | Evidence or gap | Deadline | LATE |
| --- | --- | --- | --- | --- | --- |
| 1 | Dev 1 | [x], with a gap | `run.py` has `--games`, `--rebuild`, `--stage` and `--fixtures`, and lazily imports `snapshot`, `aggregate` and `charts` (agreed deviation). Both files are pushed (config 10:56, run 11:06). Repo is public: GitHub API returns `"visibility": "public"`. Gap 1: `config.py` is missing `lambda_lane=0.5` and `lane_cushion=2.0`, which Dev 2 added to the design.md Config at 11:03 (5a81f8c). Gap 2 (Req 8.4): `cfg.rebuild` is parsed but never used, so nothing reuses cached tables | 10:40 | LATE (done 11:06) |
| 2 | Dev 1 | [x] | `validate(df, schema, key, name)`, C1/C2 schemas and `fixture_c1c2(cfg)` are in `contracts_data.py`. `python run.py --fixtures --stage data` reran in 1 s and printed "C1 414 rows, C2 3 plays". Fixture output matches the committed copies byte for byte | 10:45 | LATE (pushed 11:06) |
| 3 | Dev 1 | [x] | Ticked before this pass | n/a | |
| 4 | Dev 1 | [x] | `classify_plays` covers snap/release, Throw_Play and 7 exclusion reasons, written to the report's `events.exclusions`. `add_line_to_gain_x` and `load.add_los_x` are present, and C2's `line_to_gain_x == los_x + yardsToGo` passes validation. `ELIGIBLE_POSITIONS` maps FB to RB, and the tracking team check runs in the `snapshot.build` path | before 6 | |
| 5 | Dev 1 | [x] | Parser, normalized key and last-name fallback are in `match_targets` (the fallback fires 0 times on all games). The run sets `target_nflId`, `target_source` and `is_model_play`. Match rate is 96.34%, and the code warns below 85% with 20 samples. Round trip passes 82,679 of 82,923 (99.71%). Hand check: I spot-checked 20 random C2 targets against `playDescription`, and all 20 were correct, including "D.Chark" → D.J. Chark | before 6 | |
| 6 | Dev 1 | [x] | Built for all games: `out/c1_snapshot.parquet` has 1,040,658 rows (7,541 plays × 6 × 23, every frame exactly 23 rows) and `out/c2_plays.parquet` has 7,541 rows and 7,257 Model_Plays. Both pass `validate_c1`/`validate_c2` (I reran them). C1 and C2 have identical play keys across 122 games. Clamping is in code, but 0 rows are clamped because the shortest time to throw is 1.0 s. The C2 context columns (score margin, pressured, QB, n_eligible, time to throw) are present. Dev 2 and Dev 3 were told via the pushed 396de56 | 11:00 | LATE (pushed 11:13), but covers all games |
| 7 | Dev 1 | [ ] open | Done: `results/data_report.json` has counts, exclusions, match rate, Model_Plays, R2.7 (0.9923 on C/I/IN), R2.8 (0.9999), players, and 10 checks, all true. Load errors are caught per game in `snapshot.scan_tracking` and `report._scan_game`. Missing: (a) there are no Req 9.4/9.5 asserts in `snapshot.build` or `play_table` (only in `fixture_c1c2`), although I confirmed both hold on the current parquets; (b) `snapshot.build` drops `parts["errors"]`, so Req 8.5 errors are not recorded in the Data_Report on the `run.py` path; (c) `data_report.json` comes only from a standalone `python report.py`, so `python run.py` doesn't write it; (d) `frame_counts` (Req 6.5) is computed but not written, though 0 frames are flagged | 11:30 | at risk |
| 8 | Dev 1 + Dev 3 | [ ] open | No evidence. `plots.py` isn't in the repo, and `out/review_data_c1.md` hasn't been written yet (as of 11:23) | 11:30 | at risk |
| 9 | Dev 1 | [ ] | Not started. Needs 7(c) fixed so a clean `python run.py` reproduces the Data_Report | 12:15–12:45 | |
| 10 | Dev 1 | [ ] Optional | No C7 or `nflverse.py` exists | 11:45 | |
| 11 | Dev 2 | [ ] | `contracts_metrics.py` isn't in the repo | 10:45 | LATE |
| 12 | Dev 2 | [ ] | `features.py` isn't in the repo (only `metrics/metrics_plan.md` and `explainer.md`) | fixtures, then 1 game | |
| 13 | Dev 2 | [ ] | Not in the repo | | |
| 14 | Dev 2 | [ ] | `model.py` isn't in the repo | | |
| 15 | Dev 2 | [ ] | `aggregate.py` isn't in the repo | 11:45 | at risk |
| 16 | Dev 2 | [ ] | Checkpoint | 11:45 | at risk |
| 17 | Dev 2 | [ ] P1 | Gated on C4 by 12:00 | 12:00 | |
| 18 | Dev 2 | [ ] P1 | | | |
| 19 | Dev 2 | [ ] | Freeze | 12:15 | |
| 20 | Dev 2 | [ ] Optional | | | |
| 21 | Dev 3 | [x] | Repo is public (API check). `.gitignore` lists `plan.md` and `plan.md` isn't tracked. `requirements.txt` pins all 5 versions from design.md. `results/` is pushed | 10:40 | LATE (`plan.md` ignore pushed 10:56, `results/` 11:06) |
| 22 | Dev 3 | [ ] | `plots.py` isn't in the repo | 11:00 | LATE |
| 23 | Dev 3 | [ ] | `charts.py` isn't in the repo. Blocked on the C4 fixture (task 11) | | |
| 24 | Dev 3 | [ ] | No evidence. Needs `plots.py` | 11:00–11:45 | at risk |
| 25 | Dev 3 | [ ] Optional | | after 23 | |
| 26 | Dev 3 | [ ] P1 | | | |
| 27 | Dev 3 | [ ] | | 12:00–12:45 | |
| 28 | Dev 3 | [ ] | Not started. The file-size and tracking checks are listed under Cleanup | 12:45–13:00 | |

## Next for Dev 1 (11:15-12:15)

1. Now (2 min): add `lambda_lane: float = 0.5` and `lane_cushion: float = 2.0` to `config.py`, then push. This unblocks Dev 2's `features.py`.
2. By 11:30, close task 7:
   - At the end of `snapshot.build`, add asserts that C2 keys are in `plays.csv` and C1 (Req 9.4) and that every Model_Play target is eligible in C1 (Req 9.5). Both already hold on the current data.
   - Record `parts["errors"]` and `frame_counts` in the Data_Report.
   - Have the data stage call `report.build_full_report`/`write_full_report`, so `python run.py` writes `results/data_report.json`.
   - Rerun the data stage once to confirm. Its runtime isn't recorded anywhere, so log it (Req 8.3).
3. At 11:30, run the 5-play checkpoint with Dev 3 (task 8), including at least one left-direction play. If `plots.py` isn't pushed, a quick scatter of C1 with the LOS and line-to-gain lines from C2 is enough.
4. Make `--rebuild` do something (Req 8.4): skip the build when both parquets exist, unless `--rebuild` is set.
5. Change `snapshot.build` so a broken `play_table` fails the run. Today it catches ImportError/TypeError, prints "C2 NOT BUILT" and still exits 0, which could leave a stale C2 in place.
6. At 12:15, run the clean-clone test (task 9). Skip task 10 unless Dev 3 has C7 by 11:45.

## Blockers for Dev 2/Dev 3

- Dev 2: `cfg.lambda_lane` and `cfg.lane_cushion` raise AttributeError until Dev 1 pushes step 1. Workaround: `getattr(cfg, "lambda_lane", 0.5)`.
- Dev 2: there's no data blocker. All-game C1/C2 and the fixtures are on origin/main, so a pull gets them.
- Dev 3: the C4 fixture doesn't exist because `contracts_metrics.fixture_c3c6` (task 11, Dev 2) isn't pushed, so the headline chart (task 23) can't start on fixtures.
- Dev 3: `python run.py --fixtures --stage story` (due 11:00) will fail until `charts.build` exists.

## Issues

- Task 1 is ticked, but `config.py` doesn't match the current design.md Config (missing `lambda_lane` and `lane_cushion`), and `--rebuild` is a no-op.
- Deviation from design.md: C2 is built in the new `play_table.py` instead of `snapshot.py`. It's called from `snapshot.build`, so the interface is unchanged.
- The Data_Report runs a separate parallel tracking pass (`report.py`, 6 workers), while the C1 build is serial per game. They agree today: 7,541 Throw_Plays in both, and the consistency checks pass.
- R2.7/R2.8 are computed on C/I/IN candidates (7,544 plays), not on the 7,541 Throw_Plays. The difference is negligible but doesn't follow the letter of the requirement.
- Real data has 0 clamped rows (shortest time to throw is 1.0 s), so only fixture play 2 exercises the clamp.
- 24 tracked plays have no snap event. They're excluded with the reason `no_snap`.
- Data review: `out/review_data_c1.md` doesn't exist yet (as of 11:23), so there's no verdict.

## Cleanup (end, nice-to-have)

These are not risks or blockers. Leave them until the end.

- `data/` is still tracked in origin/main (127 files, including 122 tracking CSVs), even though `.gitignore` ignores `data/`. `data/pffScoutingData.csv` is 13.0 MB, over task 28's 10 MB limit.
- `out/c1_snapshot.parquet` (12.3 MB) is committed on purpose for Dev 2 (`#out/` is commented out in `.gitignore`). It's over task 28's 10 MB limit.
- The interim files `out/*_all.parquet`, `out/eligible_receivers.parquet`, `out/play_events_targets.parquet` and `out/data_report_events_targets.json` were committed in d137591 (11:16).
- `plan.md` is in the history (860f7c1, "add plan"). It's ignored and untracked now.
