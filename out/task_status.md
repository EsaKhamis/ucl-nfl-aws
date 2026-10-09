# Task status board

Reconciled at 10:53 BST, Fri 9 Oct, against the local working tree and `origin/main` @ 7ffdf2b "pre load". Nothing from Dev 2 or Dev 3 is visible on origin. No branches, no worktrees.

Ticked this pass: task 3. No task was ticked by anyone else before this pass.

| # | Task | Owner | Status | Evidence / gap | Deadline | LATE |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Scaffold config.py + run.py, push, confirm repo public | Dev 1 (Agent C) | in progress | `config.py` appeared locally at 10:53 (not pushed). No `run.py` yet. Repo is public (verified). | 10:40 | LATE |
| 2 | contracts_data.py: validate, C1/C2 schemas, fixture_c1c2 | Dev 1 (Agent C) | in progress | No `contracts_data.py` and no `out/fixtures/`. | 10:45 | LATE |
| 3 | load.py schema check, NA, source counts | Dev 1 (Agent A) | done | Missing cols raise "games.csv is missing required columns: fakeA, fakeB". `na_values=["NA"]` on every source including tracking. Counts are 122/8557/1679/188254/122 with no diffs, and the warning fires on a forced mismatch. The edits are uncommitted (`M load.py`). | 11:00 (Dev 1 block) | |
| 4 | snapshot.py events, Throw_Play, LOS/LTG, eligibility | Dev 1 (Agent B) | in progress | No `snapshot.py` and no `out/play_events_targets.parquet` or `out/eligible_receivers.parquet` yet. `load.snap_frames`/`add_los_x` exist. | 11:00 (feeds task 6) | |
| 5 | targets.py parser, name key, match rate | Dev 1 (Agent B) | in progress | No `targets.py` and no `out/data_report_events_targets.json` yet. | 11:00 (feeds task 6) | |
| 6 | One-game C1/C2 parquet, validated, tell Dev 2/3 | Dev 1 | not started | No `out/c1_snapshot.parquet` or `out/c2_plays.parquet`. Blocked on tasks 2, 4 and 5. | 11:00 | at risk |
| 7 | All 122 games + Data_Report | Dev 1 (Agent A partial) | in progress | `results/data_report.json` exists but covers only game 2021090900 (Req 2.7 share 1.0, 2.8 share 1.0). There are no 9.4/9.5 asserts and no all-game C1/C2. | 11:30 | |
| 8 | 11:30 checkpoint: plot 5 plays with Dev 3 | Dev 1 + Dev 3 | not started | Only `out/check_standardize.png` (one game, standardize check). | 11:30 | |
| 9 | Clean-clone test | Dev 1 | not started | Needs `run.py` and the pinned requirements on origin. | 12:45 | |
| 10 | [Opt] Fill targets from C7 | Dev 1 | not started | Needs Dev 3 `nflverse.py`. | 11:45 | |
| 11 | contracts_metrics.py C3–C6 schemas + fixture | Dev 2 | not started (not visible) | Not on origin/main. | 10:45 | LATE |
| 12 | features.py separation/closing/openness | Dev 2 | not started (not visible) | Not on origin/main. `standardize()` is on origin, so Dev 2 can start. | 11:45 (C3) | |
| 13 | Context + pressure features | Dev 2 | not started (not visible) | Not on origin/main. | 11:45 | |
| 14 | model.py xTarget + CV, model_report.json | Dev 2 | not started (not visible) | Not on origin/main. | 11:45 | |
| 15 | C3/C4 all games, asserts, route quartiles | Dev 2 | not started | Blocked on task 7 (all-game C1/C2). | 11:45 | |
| 16 | 11:45 checkpoint: TOE top/bottom 10, Route_Minimum | Dev 2 + Dev 3 | not started | | 11:45 | |
| 17 | [P1] C5/C6 | Dev 2 | not started | Only if C4 is done by 12:00. | 12:00 | |
| 18 | [P1] Release-frame robustness | Dev 2 | not started | | 12:15 | |
| 19 | Analysis freeze | Dev 2 | not started | | 12:15 | |
| 20 | [Opt] Pressure, D&D, orientation, EPA | Dev 2 | not started | | 12:15 | |
| 21 | Repo hygiene: public, plan.md ignored, pins, results/ pushed | Dev 3 | in progress (1 of 4) | Public: yes. `plan.md` is not in `.gitignore` and is tracked on origin. sklearn/pyarrow pins are local only (uncommitted). `results/` exists locally, untracked, not pushed. | 10:40 | LATE |
| 22 | plots.py Play_Plotter on C1/C2 fixtures | Dev 3 | not started (not visible) | No `plots.py` on origin. Needs the C1/C2 fixtures (task 2). | 11:00 | at risk |
| 23 | charts.py headline + leaderboards on C4 fixture | Dev 3 | not started (not visible) | Needs the C4 fixture (task 11). The design wants `run.py --fixtures --stage story` working by 11:00. | 11:00 (story on fixtures) | at risk |
| 24 | Sanity-check 5 plays with Dev 1 | Dev 3 | not started | Needs one-game C1/C2 (task 6) and plots.py (task 22). | 11:00–11:45 | |
| 25 | [Opt] nflverse.py C7 | Dev 3 | not started | Not before task 23. | 12:15 | |
| 26 | [P1] Supporting chart | Dev 3 | not started | | 12:15 | |
| 27 | Headline summary + README | Dev 3 | not started | No `README.md`. | 12:45 | |
| 28 | Final push + submit | Dev 3 | blocked | `data/` (127 files) and `out/check_standardize.png` are tracked. `data/pffScoutingData.csv` is 13.0 MB (over the 10 MB limit). `.gitignore` is fully commented out. | 13:00 | |

## Critical path to 11:00 (7 minutes away)

- Dev 2 can start on `standardize()`/`add_los_x()` from origin/main now. What blocks them is the C3–C6 fixture (their own task 11, LATE) and a pushed `config.py`/`contracts_data.validate` (tasks 1 and 2, LATE). `contracts_metrics.py` imports `validate` from `contracts_data`.
- Dev 3 is blocked on `fixture_c1c2` (task 2) for plots.py and on `fixture_c3c6` (task 11) for charts.py. `run.py --fixtures --stage story` can't run until `run.py` exists (task 1).
- The one-game C1/C2 (task 6) needs `snapshot.py` + `targets.py` (tasks 4 and 5) and `contracts_data.py` (task 2). None of them are on disk yet. The 11:00 gate will slip. Agree a new time (around 11:15) and tell Dev 2 and Dev 3.

## Critical path to 11:30

- All-game C1/C2 + full Data_Report (task 7) depends on task 6 being correct on one game first. Task 15 (Dev 2's C3/C4 on all games, due 11:45) depends on task 7.
- The 11:30 plot check (tasks 8 and 24) needs plots.py from Dev 3 and C1/C2 from Dev 1. It should include at least one left-direction play.
- Every Dev 1 change is local and uncommitted (load.py edits, requirements.txt, results/). Nothing from Agents B and C is pushed. Dev 2 and Dev 3 can only see origin, so push as soon as each piece passes its check.

## Issues

1. Raw data in git history. Commit 67790a2 "push data" put `data/` (127 files) on origin/main, and the tree totals about 866 MB uncompressed. `data/pffScoutingData.csv` is 13.0 MB, which breaks Req 25.4 and task 28. `git rm --cached` fixes the tree but leaves the data in history. Removing it from history needs a rewrite and force-push. The team needs to decide.
2. `.gitignore` is entirely commented out. `git check-ignore` matches nothing for `data/`, `out/`, `plan.md` or `__pycache__/`. design.md says data/ and out/ are "ignored (already)", which is false. `out/check_standardize.png` was committed and pushed in 7ffdf2b, which breaks Req 25.3. This board (`out/task_status.md`) will show as untracked. Don't `git add .`.
3. `plan.md` is tracked and pushed (860f7c1). Adding it to `.gitignore` won't remove it. It also needs `git rm --cached plan.md`, and it stays in history unless rewritten.
4. Repo visibility: public. The GitHub API returned 200 with `"private": false`. `gh` is installed but not authenticated.
5. requirements.txt pins: the local working copy has all 5 design pins (pandas 2.2.2, numpy 1.26.4, matplotlib 3.9.2, scikit-learn 1.5.1, pyarrow 16.1.0). origin has only the first 3. The file is Dev 3's, but it was edited locally here, so agree who commits it.
6. Data_Report path: now `results/data_report.json`, which matches the design. An earlier stale copy in `out/` was removed. `results/` is untracked and must be pushed (task 21, Req 25.1). It currently covers only one game.
7. Code vs design: `load.py` reads paths from module-level `DATA_DIR`/`OUT_DIR`/`RESULTS_DIR` (env vars), not from `Config.data_dir`/`derived_dir`/`outputs_dir`. Once `config.py` lands, `run.py` must wire cfg paths into load.py, or `--data-dir`-style overrides and the clean-clone test (task 9) may read the wrong place.
8. Task 1 deviation (agreed): `run.py` will lazy-import stage modules instead of creating stubs for other owners' files. That's fine, but `--stage story --fixtures` must fail with a clear message, not an ImportError, while `charts.py` is missing.
