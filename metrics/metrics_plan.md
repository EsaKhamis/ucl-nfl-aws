# Metrics Plan (Dev 2) — Open but Ignored vs. Over-Targeted

Owner: Dev 2 (Person B). Workstream B, Requirements 11–20 (P0/P1), 21–24 (optional).
Authoritative sources: `.kiro/specs/open-but-ignored/{requirements.md, design.md, tasks.md}`.

**AUTHORITATIVE on the openness metric:** this file now defines the composite
Openness_Score as the standard (see "Openness_Score — composite (authoritative)" below).
`design.md` and `requirements.md` have been updated to match. If any older
single-term openness definition survives elsewhere, the composite here wins and that
other text is stale — fix it. For everything else (contracts, data stage, story stage),
the spec wins.

## My job in one line

For every eligible WR/TE/RB route on every Model_Play, measure openness just before
the throw, model how likely each route was to be targeted, and aggregate Targets Over
Expected (TOE) by receiver, coverage, and team.

## Boundaries (what I own vs. consume)

- **Consume (from Dev 1):** C1 Snapshot_Table, C2 Play_Table in `out/` (parquet).
  Keys and columns are fixed in requirements.md. I code against the column names from
  10:20 using the C1/C2 fixtures, swap to the one-game prototype at ~11:00, then the
  full 122-game tables at ~11:30.
- **Produce (to Dev 3):** C3 Route_Features_Table, C4 Receiver_TOE_Table,
  C5a/C5b Team tables, C6 Instead_Table. Plus `results/model_report.json`.
- **Do NOT edit** `config.py`, `run.py`, `contracts_data.py` (Dev 1) or any Dev 3 file.
  Ask the owner for changes.

## My files

| File | Contents | Reqs |
| --- | --- | --- |
| `features.py` | Separation, closing speed, openness, Most_Open, depth, pressure | 11–13, 23 |
| `model.py` | Expected-target logistic model + grouped CV | 14, 19 |
| `aggregate.py` | C3–C6, `build(cfg)` | 15–18, 21, 22, 24 |
| `contracts_metrics.py` | C3–C6 schemas + `fixture_c3c6(cfg)` (imports `validate` from `contracts_data`) | 20 |

`aggregate.build(cfg)` is the stage entry point called by `run.py`.

## Decisions locked with the team (do not relitigate on the clock)

- **Nearest defender = all 11 defenders**, not only `pff_role == "Coverage"`. (Confirmed.)
- **Write outputs to `out/`** even if not yet `.gitignore`'d. Flag Dev 3 only if a
  commit would actually include `out/` or a file > 10 MB. (Confirmed.)
- **Openness stays pure "opportunity to complete."** Value (down/distance, EPA) lives in
  the model and the optional stretch goals, never baked into Openness_Score. Keeps the
  headline ("open rate vs. target share") interpretable.
- **Open = Most_Open per play** by default (`open_mode = "most_open"`). Threshold mode is
  a config option only.
- **Pre-release openness (offset 4, 0.4 s) is primary;** release-frame (offset 0) is a
  robustness check. This is the "defenders break on the ball" mitigation.

## Verify-before-trust checks (read-only, run first, report numbers)

These guard against silently corrupting every spatial number. Do them before coding
features, against `data/tracking/tracking_2021090900.csv` and C1:

1. **Event vocabulary & frequency** — confirm which `event` values exist
   (`ball_snap`/`autoevent_ballsnap`, `pass_forward`/`autoevent_passforward`,
   `qb_sack`, `run`). Confirms release-frame detection (Dev 1 owns, but I depend on it).
2. **Direction flip sanity** — take one `playDirection == "left"` play, apply the
   standardize transform, confirm offense moves toward +x like a `right` play. Dev 1
   owns `standardize()`; until it's pushed I use a local flip
   (`x→120−x, y→53.3−y, o→(o+180)%360, dir→(dir+180)%360`).
3. **Velocity convention** — confirm a player moving toward +x has `dir ≈ 90`, i.e.
   `vx = s·sin(dir°)`, `vy = s·cos(dir°)` (design.md). One frame is enough.
4. **Frame shape** — 23 rows per (game, play, offset): 22 players + 1 ball (`nflId`
   null). Confirms how I isolate defenders and the QB (`qb_nflId` from C2).

## Feature formulas (authoritative — from design.md)

All computed at offset 0 (release) and at `pre_release_offset` (default 4).

- **Velocity:** `vx = s·sin(dir°)`, `vy = s·cos(dir°)`.
- **Separation:** `min over all defenders ‖p_d − p_r‖`. Vectorize per frame with numpy
  broadcasting. Non-negative; equals min distance to any defensive player (Req 11.4).
- **Closing_Speed:** `−(p_d − p_r)·(v_d − v_r) / ‖p_d − p_r‖` for the Nearest_Defender.
  Positive = closing. This is the honest projected version we agreed on.
- **Lane_Penalty (new, composite input):** how much the nearest defender sits *in the
  throwing lane*. Let `perp_dist` = the perpendicular distance (yards) from the
  Nearest_Defender to the straight line from the receiver to the QB. Then
  `lane_penalty = max(0, lane_cushion − perp_dist)`. A defender directly in the lane
  (`perp_dist ≈ 0`) gives the full penalty `lane_cushion`; a defender off to the side
  (`perp_dist ≥ lane_cushion`) gives 0. New Config params: `lambda_lane` (default 0.5),
  `lane_cushion` (default 2.0 yd). The receiver→QB line is used for the lane; validating
  it against the actual ball-flight path stays an optional check (see below).

### Openness_Score — composite (authoritative)

```
openness = separation
         − closing_horizon_s × closing_speed      # space about to vanish
         − lambda_lane × lane_penalty             # a defender sitting in the throwing lane
```

with `closing_horizon_s = 0.5`, `lambda_lane = 0.5`, `lane_cushion = 2.0`.

Three honest signals combine into one "how catchable is a throw here right now" number,
in yards:
- **separation** — raw space from the nearest defender (more = better).
- **closing_speed** — how fast that space is disappearing (penalized, so separation that
  is about to evaporate counts for less).
- **lane_penalty** — whether a defender is parked between the receiver and the QB, able
  to break on the ball even without being the closest body (penalized).

Monotonicity (holds the other two inputs fixed): openness increases with separation
(Req 12.2), decreases with closing speed (Req 12.3), and decreases as a defender moves
into the throwing lane (new Req 12.9). All three inputs are distances / projected
distances / dot products, so the composite is unchanged by the 180° direction flip
(Req 11.5). `openness_pre` at offset 4, `openness_rel` at offset 0.

**Why NOT z-score within position group here:** standardizing openness across the whole
dataset would break "exactly one Most_Open per Model_Play on one comparable scale," which
is what makes the headline chart's y = x diagonal a fair-share line. Position fairness is
handled instead by `depth` in the model and by the per-Position_Group splits in C4. The
within-position view stays a reported robustness check only (see optional section).

- **Most_Open:** exactly one per Model_Play = highest composite `openness_pre`, ties to
  lowest `nflId` (Req 12.6). `open_flag` = Most_Open in most_open mode; `separation ≥
  open_threshold` in threshold mode.
- **depth:** `x − los_x` at pre-release. **depth_vs_sticks:** `x − line_to_gain_x` at
  pre-release. **dist_from_qb:** distance to the `qb_nflId` row at pre-release.
- **Rusher_Distance:** min distance from QB to any `pff_role == "Pass Rush"` row at
  offset 0. Missing (counted) if no rusher present (Req 13.5).
- **pressured:** copied from C2 onto each route.
- Missing separation/closing speed when a frame has no defender (counted, Req 11.6).

## Expected-target model (model.py — authoritative)

- `make_pipeline(StandardScaler(), LogisticRegression())`.
- Features (amended Req 14.1): `openness_pre` (the composite above), `depth`,
  `dist_from_qb`, `rusher_distance × depth`, `rusher_distance × dist_from_qb`.
  (Rusher_Distance is constant within a play, so after per-play normalization it only
  acts via interactions.)
- Fill missing features with the median; count fills (Req 14.9).
- `xtarget = p / Σp` within each Model_Play (sums to 1, Req 14.3/14.4).
- Fit on all Model_Plays to produce TOE.
- Evaluate with `GroupKFold(5)` on `gameId` (no leakage); report log loss, AUC, top-1
  accuracy (argmax xTarget == target). Write coefficients + fold metrics to
  `results/model_report.json`. Warn if `openness_pre` coefficient ≤ 0 (Req 14.8).

**Accuracy-first with a time-bounded fallback (our agreement):** `aggregate` reads an
`xtarget` column that is normally filled by the fitted model. If model fitting slips past
the 12:15 freeze, a baseline (equal share = `1 / n_eligible`, i.e. mean target rate)
fills `xtarget` so the full pipeline still produces valid C3–C6. One flag switches it.
Build the real model first; only fall back if actually out of time.

## Aggregation (aggregate.py — Reqs 15–18)

- **C3 Route_Features_Table:** one row per Route on a Model_Play. The `openness_pre` /
  `openness_rel` columns now hold the composite score. Two new diagnostic columns expose
  its lane input: `lane_penalty_pre`, `lane_penalty_rel` (float, yards). Asserts: exactly
  one `is_target` and one `is_most_open` per play (Req 15.2); `is_target` ⇔ `nflId ==
  target_nflId` (Req 15.3).
- **C4 Receiver_TOE_Table:** per receiver × Split. Splits = All, Man, Zone, each
  Coverage_Family (Coverage_Type "Other" only in All); Coverage_Family also by
  Position_Group. Columns: routes, targets, x_targets, toe, toe_per_100_routes,
  open_routes, open_rate, target_share, meets_minimum. `team` = possessionTeam with most
  routes. Asserts: Σ toe == 0 per split (Req 16.7); open_rate, target_share ∈ [0,1],
  targets ≤ routes (16.8); Man+Zone routes ≤ All routes (16.9).
  **Report route quartiles so the team sets Route_Minimum together at the 11:45 gate.**
- **C5 (P1):** C5a offense (model_plays, routes, funnel_index = Σ positive TOE /
  model_plays, top over/ignored receiver with ≥ team_route_minimum routes); C5b defense
  (model_plays, ignored_open_events, ignored_open_rate, mean Most_Open separation).
  Note: team TOE sums to 0, so the team story uses Team_Funnel_Index, not Σ TOE.
- **C6 (P1):** one row per Ignored_Open_Event (Most_Open ≠ Target). `openness_gap =
  ignored_openness − target_openness ≥ 0` (Req 18.4). Both ids eligible on the play.
- **C4/C5/C6 validated** via `contracts_metrics.validate(...)` before the stage returns.

## Contracts & fixtures (contracts_metrics.py — Req 20, Task 11, by 10:45)

- C3–C6 schemas `{column: (kind, nullable, allowed_values)}`; import `validate` from
  `contracts_data`.
- `fixture_c3c6(cfg)`: ≥ 20 receivers, 4 teams, xTarget sums to 1 per play, Σ TOE == 0.
  **Push early** so Dev 3 builds charts against it before real numbers land.
- `python run.py --fixtures --stage story` must work by 11:00 (depends on this fixture).

## OPTIONAL experiments (post-freeze only, no schema change)

Attempt only after P0+P1 are done and before 12:15, and only if they do not change the
C3 schema or the Most_Open definition Dev 3 depends on:

- **Ball-flight vs. receiver→QB line** for the lane term. The composite uses the
  receiver→QB line. As a check, compute `perp_dist` against the actual ball-flight path
  on a subset and report the distribution of the difference; switch the lane basis to the
  flight path only if it is materially different. (At release the ball ≈ the QB, so
  expect little divergence except on rollouts / off-platform throws.)
- **Within-position / within-depth standardization** of openness as an alternative
  "open" definition — reported as a robustness view only, never replacing the composite
  Most_Open in C3 (z-scoring across the dataset breaks "one Most_Open per play").

## Composite tuning note (do on the day, before 11:45)

`lambda_lane` and `lane_cushion` are defaults, not gospel. Quick sanity pass once
features run on one game: eyeball ~5 plays in the plotter where the composite and plain
separation disagree, confirm the lane penalty is firing on defenders actually in the
throwing lane and not on trailing/side defenders. If `lambda_lane` is swinging Most_Open
in ways that look wrong, lower it toward 0 (0 reduces the composite to the old
separation − closing-speed score, a safe fallback). Don't over-tune on the clock.

## Timeline & gates (my lane)

| Time | Task |
| --- | --- |
| 10:20–10:45 | Run verify-before-trust checks. Write `contracts_metrics.py` + `fixture_c3c6`. Push. |
| 10:45–11:00 | `features.py` on C1/C2 fixtures: separation, closing speed, openness, Most_Open. |
| 11:00–11:30 | Swap to one-game C1/C2, then full tables. Add depth/sticks/dist_from_qb/rusher. Sanity-check ~5 plays with Dev 3's plotter (incl. one left-direction play). |
| 11:30–11:45 | `model.py`: fit logistic, grouped CV, model_report.json. C3 + C4 on all games. Report route quartiles. |
| 11:45 (gate) | Share top/bottom-10 TOE with Dev 3. Agree Route_Minimum and candidate headline. |
| 11:45–12:00 | If C4 done on all games by 12:00 → build C5 + C6 (P1). Else keep hardening C4. |
| 12:00–12:15 | Release-frame robustness (Req 19): Spearman corr + top-10 overlap. Optional items only if ahead. |
| 12:15 | **Analysis freeze. Bug fixes only.** |

## Ship-first ordering (if the clock collapses)

1. features (separation + openness_pre + Most_Open) → gives a defensible metric alone.
2. C3 + C4 All split with baseline `xtarget` → full pipeline produces output.
3. Real logistic model swapped into `xtarget`.
4. Man/Zone splits.
5. C5/C6 (P1). 6. Robustness + optional (post-freeze gated).

Stop adding analysis at 12:15 no matter what. A correct simple metric beats an
unfinished ambitious one.
