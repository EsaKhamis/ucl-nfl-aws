# Implementation Plan

Every task has one owner. Run only your own tasks, in order, and stop at each checkpoint to sync. File owners, paths, formulas and interfaces are in `design.md`. P0 comes first; P1 and Optional tasks follow the scope rule in `design.md`.

## Dev 1: Data

- [ ] 1. Scaffold the shared files (by 10:40)
  - Write `config.py` with the full `Config` dataclass from `design.md`.
  - Write `run.py` with the `--games`, `--rebuild`, `--stage` and `--fixtures` flags. Have it call `snapshot.build`, `aggregate.build` and `charts.build`, and create stubs for any module that doesn't exist yet.
  - Push both files. Confirm with Dev 3 that the repo is public.
  - _Requirements: 8.1, 8.4, 25.5_

- [ ] 2. Write the contract tooling (by 10:45)
  - In `contracts_data.py`, write `validate(df, schema, key, name)`, plus the C1 and C2 schemas and `fixture_c1c2(cfg)`. The fixture covers 3 plays, each with 6 offsets and 23 rows.
  - Running `python run.py --fixtures --stage data` writes the fixtures to `out/fixtures/`, and they pass validation.
  - _Requirements: 9.1, 9.2, 9.3_

- [ ] 3. Add the schema check and source counts to `load.py`
  - Add the Appendix A column check, which stops the run and lists every missing column.
  - Read "NA" as missing.
  - Count the source rows and warn on any difference from the reference copy.
  - _Requirements: 1.1–1.6_

- [ ] 4. Find events and eligible receivers in `snapshot.py`
  - Find the snap and release frames and classify Throw_Plays. Record the excluded plays and their reasons.
  - Compute LOS_x and Line_to_Gain_x using the transform in `design.md`.
  - Mark Eligible_Receivers and their Position_Group, mapping FB to RB.
  - _Requirements: 2.4, 3.1–3.6, 4.1–4.4_

- [ ] 5. Match targets in `targets.py`
  - Write the parser and the normalized name key from `design.md`, with the last-name-only fallback.
  - Before wiring it in, check it by hand on 20 random descriptions.
  - Set `target_nflId`, `target_source` and `is_model_play`. Report the match rate and warn if it's below 85%.
  - _Requirements: 5.1–5.9_

- [ ] 6. Build C1 and C2 on one game (by 11:00)
  - Take snapshots at offsets 0–5 with clamping.
  - Add the C2 context: score margin, pressured, QB, `n_eligible` and time to throw.
  - Write `out/c1_snapshot.parquet` and `out/c2_plays.parquet`, and validate both.
  - Tell Dev 2 and Dev 3 when the files are ready.
  - _Requirements: 6.1–6.5, 7.1–7.5, 9.6_

- [ ] 7. Run all 122 games and write the Data_Report (by 11:30)
  - Process the games one at a time. Use a process pool if the run takes over 10 minutes.
  - Catch tracking files that fail to load, and continue with the rest.
  - Write the integrity shares (Req 2.7, 2.8), the referential-integrity asserts (Req 9.4, 9.5) and `results/data_report.json`.
  - _Requirements: 2.7, 2.8, 8.2, 8.3, 8.5, 9.4, 9.5_

- [ ] 8. Checkpoint at 11:30. Plot 5 plays with Dev 3 and confirm the direction, LOS and targets look right. Fix anything wrong before Dev 2 builds on the full tables.

- [ ] 9. Clean-clone test (12:15–12:45)
  - Clone the repo into a fresh directory, set up a venv from the pinned `requirements.txt`, and link `data/`.
  - Run `python run.py` from start to finish.
  - _Requirements: 25.6_

- [ ] 10. [Optional] Fill unmatched targets from C7 if Dev 3 has it by 11:45.
  - _Requirements: 10.1–10.3_

## Dev 2: Metrics

- [ ] 11. Write the C3–C6 schemas and `fixture_c3c6(cfg)` in `contracts_metrics.py` (by 10:45)
  - The fixture covers 20 or more receivers on 4 teams, with xTarget summing to 1 per play and TOE summing to 0. Push it early so Dev 3 can build charts against it.
  - _Requirements: 20.1–20.3_

- [ ] 12. Compute separation, closing speed and openness in `features.py` (on fixtures, then one game)
  - Compute the vectorized nearest defender at offset 0 and at the Pre_Release_Offset, plus Closing_Speed and Openness_Score, using the formulas in `design.md`.
  - Confirm that `dir` ≈ 90 means moving toward +x.
  - Mark Most_Open (ties go to the lowest `nflId`) and set Open_Flag. Check the Pre_Release_Offset config value.
  - _Requirements: 11.1–11.7, 12.1–12.8_

- [ ] 13. Add context and pressure features
  - Compute `depth`, `depth_vs_sticks`, `dist_from_qb` and Rusher_Distance, and copy `pressured` from C2.
  - _Requirements: 13.1–13.6_

- [ ] 14. Build the expected-target model in `model.py`
  - Fit a logistic model on the features listed in amended Req 14.1, filling missing values with the median.
  - Normalize xTarget within each play.
  - Run 5-fold grouped cross-validation by game and report log loss, AUC and top-1 accuracy.
  - Write the coefficients to `results/model_report.json`, and warn if the `openness_pre` coefficient is 0 or below.
  - _Requirements: 14.1–14.9_

- [ ] 15. Build C3 and C4 on all games (by 11:45)
  - Write the route table with the Req 15.2 and 15.3 asserts.
  - Write the receiver splits (All, Man, Zone and coverage families) with the Req 16.7–16.9 asserts.
  - Report the route quartiles so the team can set Route_Minimum together.
  - _Requirements: 15.1–15.3, 16.1–16.9_

- [ ] 16. Checkpoint at 11:45. Share the top and bottom 10 TOE with Dev 3. Agree Route_Minimum and the candidate headline.

- [ ] 17. [P1] Build the team tables (C5) and the instead table (C6), only if C4 is done by 12:00.
  - _Requirements: 17.1–17.5, 18.1–18.5_

- [ ] 18. [P1] Fit the release-frame robustness model. Report the Spearman correlation and the overlap between the two top-10 lists.
  - _Requirements: 19.1–19.3_

- [ ] 19. Analysis freeze at 12:15. After that, fix bugs only.

- [ ] 20. [Optional, in this order] Pressure split, down and distance, QB orientation, EPA.
  - _Requirements: 21, 22, 23, 24_

## Dev 3: Story

- [ ] 21. Repo hygiene (by 10:40)
  - Make the GitHub repo public.
  - Add `plan.md` to `.gitignore`.
  - Pin `scikit-learn==1.5.1` and `pyarrow==16.1.0` in `requirements.txt`, alongside the existing pins.
  - Create `results/` and push.
  - _Requirements: 25.1–25.4_

- [ ] 22. Write the Play_Plotter in `plots.py` and test it on the C1/C2 fixtures (by 11:00)
  - Draw offense, defense and the ball in distinct colors and markers.
  - Draw lines at LOS and the line to gain.
  - Label the target. When C3 is available, also label Most_Open and annotate each receiver's separation.
  - _Requirements: 26.1–26.5_

- [ ] 23. Build the headline chart and leaderboards in `charts.py` on the C4 fixture
  - Draw two panels, Man and Zone, with the y = x line and region labels.
  - Label the top 5 and bottom 5 receivers in each panel by name.
  - Use the Okabe-Ito colors with distinct markers, and save at 200 dpi.
  - Write `leaderboard_over` and `leaderboard_ignored` as both CSV and Markdown.
  - _Requirements: 27.1–27.8, 28.1–28.4_

- [ ] 24. Sanity-check plays with Dev 1 (11:00–11:45)
  - Plot 5 real plays, at least one of them a left-direction play.
  - Report any problems with direction, LOS or targets to Dev 1 straight away.

- [ ] 25. [Optional] Fetch nflverse in `nflverse.py`
  - Read the 2021 play-by-play parquet from the URL, cache it to `out/cache/` and join it into C7.
  - Report the join rate.
  - If the download fails, print a notice and continue.
  - Don't start before task 23 is done.
  - _Requirements: 33.1–33.4_

- [ ] 26. [P1] Draw one supporting chart once the headline is working
  - Draw the team small multiples first (needs C5). If C5 isn't ready, draw the instead chart (C6) or the coverage profile (C4) instead.
  - _Requirements: 29 or 30 or 31_

- [ ] 27. Write the headline summary and README (12:00–12:45)
  - At 12:00, pick the finding with Dev 2.
  - Write `results/headline_summary.json` and set the chart title from it.
  - Write a 3 to 5 sentence README that names a player and includes a number, plus the data source, the data path, the run command and the embedded chart.
  - Cite nflverse and FTN if their data is used.
  - Check every number in the README against `headline_summary.json`.
  - _Requirements: 27.4, 32.1–32.8_

- [ ] 28. Final push and submit (12:45–13:00)
  - Check that no committed file is over 10 MB and that `data/` and `out/` aren't tracked.
  - Submit before 13:00.
  - _Requirements: 25.3, 25.4_
