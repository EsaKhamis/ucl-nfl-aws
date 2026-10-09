# Requirements Document

## Introduction

"Open but Ignored vs. Over-Targeted" is a Python data story built in 3 hours (10:00–13:00, Fri 9 Oct 2026) for the NFL Big Data Bowl London event. For every eligible WR, TE and RB route on every pass, the Pipeline measures openness just before the throw, estimates how likely each receiver was to be targeted, and compares that with who actually got the ball. The result is Targets Over Expected (TOE) per receiver, split by coverage (man vs. zone first, then coverage families), by offense and defense, plus a record of who got the ball when the most open receiver was ignored.

The submission is a public repo with code that runs end to end, a `requirements.txt`, a 3–5 sentence README stating the insight with a number, and one headline chart whose title states the finding.

Requirements are grouped by the three workstreams in plan.md. Each requirement belongs to exactly one workstream. The workstreams work in parallel against fixed handoff contracts (C1–C7, below): Metrics and Story start on synthetic fixtures at 10:20, switch to the one-game prototype as soon as Data publishes it, then move to the full 122-game run.

Priority tags: **P0** is needed for the submission. **P1** is supporting work, done only if P0 is on track (Story picks one P1 chart as the supporting chart). **Optional** is a stretch goal from plan.md, attempted only after P0 and P1 are done and before the 12:15 analysis freeze.

### Workstreams and ownership

| Workstream | Owner | Requirements | Produces | Consumes |
| --- | --- | --- | --- | --- |
| A. Data | Person A | 1–9; optional 10 | C1 Snapshot_Table, C2 Play_Table, Data_Report | Source CSVs; C7 (optional) |
| B. Metrics | Person B | 11–20; optional 21–24 | C3 Route_Features_Table, C4 Receiver_TOE_Table, C5 Team tables, C6 Instead_Table | C1, C2; C7 (optional) |
| C. Story | Person C | 25–32; optional 33–34 | Charts, leaderboards, Headline_Summary, README, repo hygiene; C7 (optional) | C1–C6, Data_Report |

### Timeline (context, not requirements)

| Time | A. Data | B. Metrics | C. Story |
| --- | --- | --- | --- |
| 10:00–10:20 | All: read the prompt and rubric, run the schema check (Req 1), lock the idea, create the public repo | | |
| 10:20–11:00 | Load, standardize, events, target matching; one-game C1/C2 | Separation, closing speed, openness on C1/C2 fixtures | Repo hygiene, Play_Plotter and chart skeletons on fixtures, optional nflverse pull |
| 11:00–11:45 | Full 122-game C1/C2, integrity checks | Features on real data, Most_Open, pressure | Plot sample plays with Data to sanity-check direction and targets |
| 11:45–12:15 | Support Metrics; optional nflverse fill | Model, TOE, splits, team and instead tables (C3–C6) | Find the headline with Metrics |
| 12:15 | **Analysis freeze** | | |
| 12:15–12:45 | Clean-clone test | Fix-ups only | Final charts, Headline_Summary, README |
| 12:45–13:00 | All: final push, check the repo, submit before 13:00 | | |

### Notes on plan.md

- **Team TOE sums to zero.** Each Model_Play has exactly one target and xTarget sums to 1 per play, so summing TOE over an offense's receivers always gives 0. The team view uses Team_Funnel_Index (positive TOE per Model_Play) to separate "funnel to a favourite" offenses from "spread by openness" offenses.
- **Open means Most_Open by default.** With exactly one Most_Open receiver and one target per Model_Play, Open_Rate and Target_Share are on the same scale, so the headline chart's diagonal is the fair-share line. A separation-threshold mode is kept as an option.
- **Pre-release openness is primary.** Openness 4 frames (0.4 s) before release feeds the model, to avoid defenders breaking on the ball. Release-frame openness is reported as a robustness check.
- **Target_Share is per route** (targets ÷ routes), not the conventional share of team targets.

## Glossary

**Components**

- **Pipeline**: The whole Python project, run end to end by one command, from source CSVs to Outputs_Dir.
- **Config**: The single set of run parameters (paths, game subset, Pre_Release_Offset, Open_Mode, Open_Threshold, Route_Minimum, Split_Route_Minimum, Team_Route_Minimum, optional-feature switches).
- **Data_Loader**: The component that loads and schema-checks the source CSVs.
- **Direction_Standardizer**: The component that converts tracking coordinates so the offense always moves toward increasing x.
- **Event_Locator**: The component that finds the Snap_Frame and Release_Frame of each play and classifies Throw_Plays.
- **Target_Matcher**: The component that recovers the targeted receiver from `playDescription`.
- **Snapshot_Builder**: The component that builds the Snapshot_Table (C1) and Play_Table (C2).
- **Contract_Validator**: The component that checks a table against its handoff contract.
- **Fixture_Generator**: The component that produces small synthetic tables matching a contract, so consumers can build before producers finish.
- **Openness_Calculator**: The component that computes Separation, Closing_Speed, Openness_Score, depth and QB distance per Route.
- **Pressure_Calculator**: The component that computes pressure features at the throw.
- **Expected_Target_Model**: The logistic model that estimates xTarget for each Route.
- **TOE_Aggregator**: The component that builds C3, C4 and C5.
- **Instead_Analyzer**: The component that builds the Instead_Table (C6).
- **Play_Plotter**: The Story component that draws a single play's snapshot for sanity checks.
- **Chart_Builder**: The Story component that produces charts, leaderboards and the Headline_Summary.
- **NFLverse_Fetcher**: The optional Story component that downloads and joins nflverse data (C7).
- **Repo**: The public git repository submitted to the event.
- **README**: The `README.md` at the Repo root.
- **Derived_Dir**: The git-ignored directory holding generated tables (C1–C7).
- **Outputs_Dir**: The committed directory holding charts, leaderboards, Data_Report and Headline_Summary.
- **Data_Report**: A small summary written by Data: source counts, exclusions with reasons, target match rate and integrity issues.
- **Headline_Summary**: A small file written by Story with every number quoted in the README and the headline chart title.

**Football and data terms**

- **Throw_Play**: A play with `passResult` "C", "I" or "IN" that has a Snap_Frame and a later Release_Frame.
- **Snap_Frame**: The first frame of a play with event "ball_snap" or "autoevent_ballsnap".
- **Release_Frame**: The first frame of a play with event "pass_forward" or "autoevent_passforward".
- **Snapshot_Offset**: A whole number of frames (0–5) before the Release_Frame; offset 0 is the Release_Frame.
- **Pre_Release_Offset**: The Snapshot_Offset used for primary openness. Allowed values 3, 4, 5; default 4 (0.4 s).
- **Standardized coordinates**: Coordinates where the offense moves toward increasing x. For `playDirection` "left": x → 120 − x, y → 53.3 − y, o → (o + 180) mod 360, dir → (dir + 180) mod 360.
- **LOS_x**: The line of scrimmage, `absoluteYardlineNumber` expressed in standardized coordinates.
- **Line_to_Gain_x**: LOS_x + `yardsToGo`.
- **Eligible_Receiver**: A player on a Throw_Play with `pff_role` "Pass Route", `officialPosition` WR, TE, RB or FB, on the `possessionTeam`.
- **Position_Group**: WR, TE or RB, with FB mapped to RB.
- **Route**: One Eligible_Receiver on one Throw_Play.
- **Target**: The Eligible_Receiver named as the pass recipient in `playDescription` (or, optionally, by nflverse).
- **Model_Play**: A Throw_Play with exactly one matched Target who is an Eligible_Receiver on that play.
- **Nearest_Defender**: The defensive player closest to an Eligible_Receiver at a given frame.
- **Separation**: The Euclidean distance in yards from an Eligible_Receiver to the Nearest_Defender.
- **Closing_Speed**: The rate in yards per second at which the distance between an Eligible_Receiver and the Nearest_Defender is shrinking. Positive means closing.
- **Openness_Score**: One number per Route combining Separation and Closing_Speed; higher means more open.
- **Most_Open**: The Eligible_Receiver with the highest Openness_Score on a Model_Play at the Pre_Release_Offset, ties broken by lowest `nflId`.
- **Open_Mode**: "most_open" (default) or "threshold".
- **Open_Threshold**: The Separation in yards above which a Route is open in "threshold" mode, chosen from the data on the day.
- **Open_Flag**: Whether a Route counts as open under the active Open_Mode.
- **Open_Rate**: The share of a receiver's Routes with Open_Flag true.
- **Target_Share**: The share of a receiver's Routes on which he was the Target.
- **xTarget**: The modelled probability that a Route was targeted, normalized within each Model_Play.
- **TOE (Targets Over Expected)**: Sum over a receiver's Routes of (1 if Target else 0) − xTarget. Positive means **over-targeted**; negative means **open but ignored**.
- **Coverage_Type**: `pff_passCoverageType`: "Man", "Zone" or "Other".
- **Coverage_Family**: `pff_passCoverage`, e.g. "Cover-1", "Cover-3", "Quarters", "Cover-2".
- **Split**: A subset of Routes used for aggregation: All, Man, Zone, one Coverage_Family, or (optional) Pressured/Clean.
- **Route_Minimum**: The minimum Routes in the All Split for a receiver to be ranked. Default 100.
- **Split_Route_Minimum**: The minimum Routes in any other Split for a receiver to be ranked. Default 40.
- **Team_Route_Minimum**: The minimum Routes for one team for a receiver to appear in the team view. Default 50.
- **Pressured**: True when any player on the play has `pff_hit`, `pff_hurry` or `pff_sack` equal to 1.
- **Rusher_Distance**: The distance in yards from the QB to the nearest `pff_role` "Pass Rush" player at the Release_Frame.
- **Ignored_Open_Event**: A Model_Play where the Most_Open receiver is not the Target.
- **Team_Funnel_Index**: The sum of positive TOE over an offense's receivers, divided by that offense's Model_Plays.
- **Ignored_Open_Rate**: Ignored_Open_Events divided by Model_Plays for a team or Split.

## Handoff Contracts

Each contract is owned by its producer, checked by the Contract_Validator and mirrored by a Fixture_Generator. Column names are fixed; consumers code against them from 10:20. Storage format and file paths are set in the design.

### C1 Snapshot_Table (Data → Metrics, Story)

One row per player or ball, per Throw_Play, per Snapshot_Offset 0–5. Key: (`gameId`, `playId`, `offset`, `nflId`), with exactly one ball row (`nflId` null) per (`gameId`, `playId`, `offset`).

| Column | Type | Rule |
| --- | --- | --- |
| gameId, playId | int | Exists in plays.csv |
| offset | int | 0–5 |
| frameId | int | Frame actually used |
| clamped | bool | True when Release_Frame − offset fell before the Snap_Frame |
| nflId | int, nullable | Null only for the ball |
| is_ball | bool | |
| side | str | "offense", "defense" or "ball" |
| pff_role | str, nullable | From pffScoutingData; null for the ball |
| position_group | str, nullable | WR, TE, RB for Eligible_Receivers; null otherwise |
| is_eligible | bool | |
| x, y | float | Standardized, yards |
| s, a | float | yd/s, yd/s² |
| o, dir | float, nullable | Standardized degrees [0, 360); null for the ball |

### C2 Play_Table (Data → Metrics, Story)

One row per Throw_Play. Key: (`gameId`, `playId`).

| Column | Type | Rule |
| --- | --- | --- |
| gameId, playId, week | int | |
| possessionTeam, defensiveTeam | str | Team abbreviation |
| quarter, down, yardsToGo | int | |
| gameClock | str | As in plays.csv |
| score_margin | int | Offense score − defense score, pre-snap |
| los_x, line_to_gain_x | float | Standardized yards |
| pff_passCoverage, pff_passCoverageType | str, nullable | As in plays.csv |
| pff_playAction | int | 0 or 1 |
| dropBackType, passResult | str | As in plays.csv |
| snap_frameId, release_frameId | int | |
| time_to_throw_s | float | (release − snap) × 0.1 |
| qb_nflId | int, nullable | Player with `pff_role` "Pass" |
| pressured | bool | |
| n_eligible | int | Eligible_Receivers on the play |
| target_nflId | int, nullable | Null when unmatched |
| target_source | str | "description", "nflverse" or "none" |
| is_model_play | bool | |

### C3 Route_Features_Table (Metrics → Story)

One row per Route on a Model_Play. Key: (`gameId`, `playId`, `nflId`).

| Column | Type | Rule |
| --- | --- | --- |
| gameId, playId, nflId, week | int | |
| displayName, position_group | str | |
| possessionTeam, defensiveTeam | str | |
| coverage_type, coverage_family | str, nullable | |
| down, yardsToGo | int | |
| separation_pre, closing_speed_pre, openness_pre | float | At Pre_Release_Offset |
| separation_rel, closing_speed_rel, openness_rel | float | At offset 0 |
| depth, depth_vs_sticks | float | x − los_x and x − line_to_gain_x at Pre_Release_Offset |
| dist_from_qb, rusher_distance | float | Yards |
| pressured | bool | |
| is_most_open, open_flag, is_target | bool | |
| xtarget | float | [0, 1], sums to 1 per play |
| xtarget_rel | float | Same, from release-frame openness (Req 19) |

### C4 Receiver_TOE_Table (Metrics → Story)

One row per receiver per Split. Key: (`nflId`, `split`).

| Column | Type | Rule |
| --- | --- | --- |
| nflId | int | |
| displayName, position_group | str | |
| team | str | The `possessionTeam` with the most Routes for the receiver |
| split | str | "All", "Man", "Zone", a Coverage_Family, or optional "Pressured"/"Clean" |
| routes, targets, open_routes | int | |
| x_targets, toe, toe_per_100_routes | float | |
| open_rate, target_share | float | [0, 1] |
| meets_minimum | bool | |

### C5 Team tables (Metrics → Story)

**C5a Offense_Team_Table**, key `team`: `team`, `model_plays`, `routes`, `funnel_index`, `top_over_nflId`, `top_over_name`, `top_over_toe`, `top_ignored_nflId`, `top_ignored_name`, `top_ignored_toe`.

**C5b Defense_Team_Table**, key `team`: `team`, `model_plays`, `ignored_open_events`, `ignored_open_rate`, `mean_most_open_separation`.

### C6 Instead_Table (Metrics → Story)

One row per Ignored_Open_Event. Key: (`gameId`, `playId`).

Columns: `gameId`, `playId`, `possessionTeam`, `defensiveTeam`, `coverage_type`, `coverage_family`, `down`, `ignored_nflId`, `ignored_name`, `ignored_position_group`, `ignored_separation`, `ignored_depth`, `ignored_openness`, `target_nflId`, `target_name`, `target_position_group`, `target_separation`, `target_depth`, `target_openness`, `openness_gap` (ignored_openness − target_openness).

### C7 External_PBP_Table (Story → Data, Metrics; optional)

One row per joined play. Key: (`gameId`, `playId`).

Columns: `gameId`, `playId`, `receiver_player_id`, `receiver_player_name`, `epa`, `air_yards`, `yards_after_catch`, `complete_pass`.

## Requirements

## Workstream A: Data (Person A)

### Requirement 1: [Data] [P0] Load and validate the event dataset

**User Story:** As the Data owner, I want the provided files loaded and checked against the expected schema, so that the team can confirm at 10:00 whether the event dataset matches our plan.

#### Acceptance Criteria

1. WHEN the Pipeline starts, THE Data_Loader SHALL load `games.csv`, `plays.csv`, `players.csv` and `pffScoutingData.csv` from the data directory set in Config.
2. WHEN a source file is loaded, THE Data_Loader SHALL verify that every column listed for that file in Appendix A is present.
3. IF a source file lacks a column listed in Appendix A, THEN THE Data_Loader SHALL stop the run and report the file name and every missing column name.
4. THE Data_Loader SHALL read the literal string "NA" as a missing value in every source file.
5. WHEN loading completes, THE Data_Loader SHALL record in the Data_Report the number of games, plays, players, scouting rows and tracking files found.
6. IF a recorded count differs from the reference copy (122 games, 8,557 plays, 1,679 players, 122 tracking files), THEN THE Data_Loader SHALL print a warning listing each differing count and continue the run.

### Requirement 2: [Data] [P0] Standardize play direction

**User Story:** As the Metrics owner, I want every play oriented the same way, so that depth, separation and orientation mean the same thing on every play.

#### Acceptance Criteria

1. WHEN a tracking row has `playDirection` "left", THE Direction_Standardizer SHALL set x to 120 − x, y to 53.3 − y, o to (o + 180) mod 360 and dir to (dir + 180) mod 360.
2. WHEN a tracking row has `playDirection` "right", THE Direction_Standardizer SHALL keep x, y, o and dir unchanged.
3. WHILE a tracking row is the ball (`team` "football"), THE Direction_Standardizer SHALL transform x and y and keep o and dir missing.
4. THE Direction_Standardizer SHALL express `absoluteYardlineNumber` in standardized coordinates as LOS_x.
5. FOR ALL tracking rows, applying the left-direction transform twice SHALL return the original x, y, o and dir within 1e-6 (involution property).
6. FOR ALL tracking rows, standardized o and dir SHALL lie in [0, 360).
7. WHEN standardization of all Throw_Plays completes, THE Direction_Standardizer SHALL record in the Data_Report the share of Throw_Plays where the ball's x at the Snap_Frame is within 2.5 yards of LOS_x, and this share SHALL be at least 99%. (On game 2021090900 the ball sits a median 0.44 yards behind LOS_x, and every play is within 3 yards.)
8. WHEN standardization of all Throw_Plays completes, THE Direction_Standardizer SHALL record in the Data_Report the share of Throw_Plays where, at the Snap_Frame, the mean offensive x is below LOS_x and the mean defensive x is above LOS_x, and this share SHALL be at least 99%.

### Requirement 3: [Data] [P0] Locate snap and release frames and classify Throw_Plays

**User Story:** As the Data owner, I want each play's snap and release frames identified, so that every snapshot is taken at the moment the QB decides.

#### Acceptance Criteria

1. THE Event_Locator SHALL set each play's Snap_Frame to the first `frameId` whose event is "ball_snap" or "autoevent_ballsnap".
2. THE Event_Locator SHALL set each play's Release_Frame to the first `frameId` whose event is "pass_forward" or "autoevent_passforward".
3. THE Event_Locator SHALL classify a play as a Throw_Play when `passResult` is "C", "I" or "IN" and the play has a Snap_Frame and a Release_Frame later than the Snap_Frame.
4. IF a play with `passResult` "C", "I" or "IN" has no Snap_Frame or no later Release_Frame, THEN THE Event_Locator SHALL exclude the play and record it in the Data_Report with the reason.
5. WHEN classification completes, THE Event_Locator SHALL record in the Data_Report the number of plays excluded for `passResult` "S" (sack) and "R" (scramble).
6. THE Event_Locator SHALL compute `time_to_throw_s` as (Release_Frame − Snap_Frame) × 0.1 seconds.

### Requirement 4: [Data] [P0] Identify Eligible_Receivers

**User Story:** As the Metrics owner, I want only real route runners in the receiver pool, so that blocking TEs and RBs do not count as ignored options.

#### Acceptance Criteria

1. THE Snapshot_Builder SHALL mark a player on a Throw_Play as an Eligible_Receiver when the player's `pff_role` is "Pass Route", `officialPosition` is WR, TE, RB or FB, and tracking `team` equals the play's `possessionTeam`.
2. THE Snapshot_Builder SHALL assign each Eligible_Receiver the Position_Group WR, TE or RB, mapping FB to RB.
3. IF a player has `pff_role` "Pass Route" and an `officialPosition` other than WR, TE, RB or FB, THEN THE Snapshot_Builder SHALL mark the player as not eligible and count the player in the Data_Report.
4. THE Snapshot_Builder SHALL record `n_eligible` for each Throw_Play.

### Requirement 5: [Data] [P0] Recover the targeted receiver

**User Story:** As the Metrics owner, I want the targeted receiver on each throw, so that actual targets can be compared with expected targets.

#### Acceptance Criteria

1. WHEN a Throw_Play's `playDescription` names a recipient with the phrase "to <name>" after the pass type or with the phrase "intended for <name>", THE Target_Matcher SHALL extract that recipient name.
2. WHEN a recipient name is extracted, THE Target_Matcher SHALL match the name to the offensive players on the same play by normalized first initial and normalized last name of `displayName`.
3. IF an extracted name matches zero or more than one offensive player on the play, THEN THE Target_Matcher SHALL leave `target_nflId` missing and set `target_source` to "none".
4. WHEN a recipient name matches exactly one offensive player, THE Target_Matcher SHALL set `target_nflId` to that player and `target_source` to "description".
5. THE Target_Matcher SHALL set `is_model_play` to true for a Throw_Play when the play has exactly one matched Target and that Target is an Eligible_Receiver on the play.
6. IF a matched Target is not an Eligible_Receiver on the play, THEN THE Target_Matcher SHALL set `is_model_play` to false and record the play in the Data_Report with the reason.
7. WHEN matching completes, THE Target_Matcher SHALL record in the Data_Report the match rate (Throw_Plays with a matched Target ÷ all Throw_Plays) and the Model_Play count.
8. IF the match rate is below 85%, THEN THE Target_Matcher SHALL print a warning with 20 sample unmatched `playDescription` values.
9. FOR ALL offensive players on a play whose normalized initial and last name are unique on that play, formatting the player's `displayName` in the `playDescription` style ("C.Godwin") and matching it SHALL return that player's `nflId` (round-trip property).

### Requirement 6: [Data] [P0] Build the Snapshot_Table (C1)

**User Story:** As the Metrics owner, I want every player's position at and just before the throw, so that openness can be computed for every option, not just the target.

#### Acceptance Criteria

1. WHEN a Throw_Play is processed, THE Snapshot_Builder SHALL extract the standardized tracking rows for all players and the ball at each Snapshot_Offset from 0 to 5.
2. IF Release_Frame − offset is earlier than the Snap_Frame, THEN THE Snapshot_Builder SHALL use the Snap_Frame for that offset and set `clamped` to true.
3. THE Snapshot_Builder SHALL build each play's rows only from tracking rows with the same `gameId` and `playId`.
4. THE Snapshot_Builder SHALL write the Snapshot_Table to Derived_Dir with the columns, types and key defined in Contract C1.
5. IF a snapshot frame has a player count other than 22 or a ball count other than 1, THEN THE Snapshot_Builder SHALL keep the play and record the play and the counts in the Data_Report.

### Requirement 7: [Data] [P0] Build the Play_Table (C2)

**User Story:** As the Metrics and Story owners, I want one row of context per throw, so that coverage, down and pressure splits share one source.

#### Acceptance Criteria

1. THE Snapshot_Builder SHALL write one Play_Table row per Throw_Play to Derived_Dir with the columns, types and key defined in Contract C2.
2. THE Snapshot_Builder SHALL set `pressured` to true when any player on the play has `pff_hit`, `pff_hurry` or `pff_sack` equal to 1 in `pffScoutingData.csv`.
3. THE Snapshot_Builder SHALL compute `score_margin` as the `possessionTeam` pre-snap score minus the `defensiveTeam` pre-snap score, using `homeTeamAbbr` from `games.csv` to assign `preSnapHomeScore` and `preSnapVisitorScore`.
4. THE Snapshot_Builder SHALL set `line_to_gain_x` to LOS_x + `yardsToGo`.
5. THE Snapshot_Builder SHALL set `qb_nflId` to the player with `pff_role` "Pass" on the play.

### Requirement 8: [Data] [P0] Process all games within the time box

**User Story:** As the team, I want to prototype on one game and then run all 122 quickly, so that the 811 MB of tracking does not eat the 3 hours.

#### Acceptance Criteria

1. WHERE a game subset is set in Config, THE Pipeline SHALL process only the listed `gameId` values.
2. THE Snapshot_Builder SHALL read tracking files one game at a time and keep only snapshot frames in memory between games.
3. WHEN all 122 tracking files are processed on the team's development laptop, THE Snapshot_Builder SHALL complete within 10 minutes.
4. WHILE a Snapshot_Table and Play_Table for the configured games exist in Derived_Dir, THE Pipeline SHALL reuse the existing tables unless Config requests a rebuild.
5. IF a tracking file fails to load, THEN THE Snapshot_Builder SHALL record the `gameId` and error in the Data_Report and continue with the remaining games.

### Requirement 9: [Data] [P0] Publish and validate the Data contracts

**User Story:** As the Metrics and Story owners, I want C1 and C2 checked and available as fixtures, so that I can build before the real tables exist.

#### Acceptance Criteria

1. THE Contract_Validator SHALL check a Snapshot_Table against C1 and a Play_Table against C2 for column names, types, allowed values, key uniqueness and nullability.
2. IF a table fails a contract check, THEN THE Contract_Validator SHALL raise an error listing every violated rule.
3. THE Fixture_Generator SHALL produce a synthetic Snapshot_Table and Play_Table of at least 3 plays that pass the Contract_Validator.
4. FOR ALL Play_Table rows, the (`gameId`, `playId`) pair SHALL exist in `plays.csv` and in the Snapshot_Table (referential integrity).
5. FOR ALL Model_Plays, `target_nflId` SHALL appear in the Snapshot_Table for that play with `is_eligible` true.
6. WHEN the Snapshot_Builder writes C1 or C2, THE Contract_Validator SHALL validate the written table before the Pipeline continues.

### Requirement 10: [Data] [Optional] Fill unmatched targets from nflverse

**User Story:** As the Data owner, I want to fill the ~9% of throws with no matched target, so that fewer plays are dropped.

#### Acceptance Criteria

1. WHERE the External_PBP_Table (C7) is available, THE Target_Matcher SHALL match `receiver_player_name` for Throw_Plays with `target_source` "none" using the rule in Requirement 5.2 and set `target_source` to "nflverse".
2. IF the description Target and the nflverse receiver disagree on a play, THEN THE Target_Matcher SHALL keep the description Target and count the disagreement in the Data_Report.
3. IF the External_PBP_Table is unavailable, THEN THE Target_Matcher SHALL continue with description targets only and print a notice.

## Workstream B: Metrics (Person B)

### Requirement 11: [Metrics] [P0] Separation and closing speed

**User Story:** As the Metrics owner, I want separation and the defender's closing speed for every route runner, so that openness reflects both space and how fast it is disappearing.

#### Acceptance Criteria

1. WHEN a Route is processed at a Snapshot_Offset, THE Openness_Calculator SHALL compute Separation as the Euclidean distance in yards from the Eligible_Receiver to the Nearest_Defender at that frame.
2. WHEN a Route is processed at a Snapshot_Offset, THE Openness_Calculator SHALL compute Closing_Speed from both players' `s` and `dir` as the rate at which their distance is shrinking, positive when closing.
3. THE Openness_Calculator SHALL compute Separation and Closing_Speed at offset 0 and at the Pre_Release_Offset.
4. FOR ALL Routes, Separation SHALL be non-negative and SHALL equal the minimum distance from the receiver to any defensive player on that frame.
5. FOR ALL Routes, Separation and Closing_Speed computed from standardized coordinates SHALL equal the values computed from raw coordinates within 1e-6 (invariance under the direction flip).
6. IF a snapshot frame has no defensive player, THEN THE Openness_Calculator SHALL set Separation and Closing_Speed to missing and count the Route.
7. WHEN all Model_Plays are processed, THE Openness_Calculator SHALL complete within 3 minutes on the team's development laptop.

### Requirement 12: [Metrics] [P0] Openness_Score and Most_Open

**User Story:** As the Metrics owner, I want one openness number per route and one most-open receiver per play, so that "open" is defined the same way everywhere.

#### Acceptance Criteria

1. THE Openness_Calculator SHALL compute an Openness_Score for each Route from the Separation and Closing_Speed at the same offset.
2. FOR ALL pairs of Routes with equal Closing_Speed, the Route with greater Separation SHALL have a greater Openness_Score.
3. FOR ALL pairs of Routes with equal Separation, the Route with greater Closing_Speed SHALL have an Openness_Score less than or equal to the other Route's.
4. THE Openness_Calculator SHALL read Pre_Release_Offset from Config, accepting 3, 4 or 5, with default 4.
5. IF Config sets Pre_Release_Offset outside 3–5, THEN THE Openness_Calculator SHALL stop the run and report the allowed values.
6. THE Openness_Calculator SHALL mark exactly one Eligible_Receiver per Model_Play as Most_Open, using the highest Openness_Score at the Pre_Release_Offset and the lowest `nflId` to break ties.
7. WHILE Open_Mode is "most_open", THE Openness_Calculator SHALL set Open_Flag equal to Most_Open.
8. WHERE Open_Mode is "threshold", THE Openness_Calculator SHALL set Open_Flag to true for each Route whose Separation at the Pre_Release_Offset is at least Open_Threshold yards.

### Requirement 13: [Metrics] [P0] Context and pressure features

**User Story:** As the Metrics owner, I want depth, QB distance and pressure for each route, so that the expected-target model accounts for routes that are still developing and for QBs under duress.

#### Acceptance Criteria

1. THE Openness_Calculator SHALL compute `depth` as the receiver's x minus LOS_x at the Pre_Release_Offset.
2. THE Openness_Calculator SHALL compute `depth_vs_sticks` as the receiver's x minus Line_to_Gain_x at the Pre_Release_Offset.
3. THE Openness_Calculator SHALL compute `dist_from_qb` as the Euclidean distance in yards from the receiver to the QB at the Pre_Release_Offset.
4. THE Pressure_Calculator SHALL compute Rusher_Distance for each Model_Play at the Release_Frame.
5. IF a Model_Play has no "Pass Rush" player in the snapshot, THEN THE Pressure_Calculator SHALL set Rusher_Distance to missing and count the play.
6. THE Pressure_Calculator SHALL copy `pressured` from the Play_Table onto each Route of the play.

### Requirement 14: [Metrics] [P0] Expected target model

**User Story:** As the Metrics owner, I want a probability of being targeted for every route, so that TOE separates real QB preference from receivers who were simply the obvious read.

#### Acceptance Criteria

1. THE Expected_Target_Model SHALL estimate xTarget for each Route on a Model_Play with a logistic model whose features are `openness_pre`, `depth`, `dist_from_qb`, Rusher_Distance × `depth` and Rusher_Distance × `dist_from_qb`. Rusher_Distance is the same for every Route on a play, so after within-play normalization it can only take effect through these interactions.
2. THE Expected_Target_Model SHALL fit on all Model_Plays in the configured games.
3. THE Expected_Target_Model SHALL normalize xTarget within each Model_Play so that the play's xTarget values sum to 1.
4. FOR ALL Model_Plays, each xTarget SHALL lie in [0, 1] and the play's xTarget values SHALL sum to 1 within 1e-6.
5. THE Expected_Target_Model SHALL use only the features in criterion 1, each computed from frames of the same play at or before the Release_Frame.
6. WHEN the model is evaluated, THE Expected_Target_Model SHALL use cross-validation folds grouped by `gameId` and report log loss and AUC per fold.
7. WHEN fitting completes, THE Expected_Target_Model SHALL report each feature's coefficient.
8. IF the `openness_pre` coefficient is not positive, THEN THE Expected_Target_Model SHALL print a warning.
9. IF a Route has a missing feature, THEN THE Expected_Target_Model SHALL fill the value with the median over all Routes and count the filled values.

### Requirement 15: [Metrics] [P0] Build the Route_Features_Table (C3)

**User Story:** As the Story owner, I want one row per route with openness, target and xTarget, so that I can chart plays and receivers without recomputing features.

#### Acceptance Criteria

1. THE TOE_Aggregator SHALL write one Route_Features_Table row per Route on a Model_Play to Derived_Dir with the columns, types and key defined in Contract C3.
2. FOR ALL Model_Plays, exactly one Route SHALL have `is_target` true and exactly one Route SHALL have `is_most_open` true.
3. FOR ALL Routes, `is_target` SHALL be true exactly when `nflId` equals the play's `target_nflId` in the Play_Table.

### Requirement 16: [Metrics] [P0] TOE by receiver and coverage (C4)

**User Story:** As a coach, I want each receiver's targets over expected, overall and by coverage, so that I can see who is over-fed and who is open but ignored against man and zone.

#### Acceptance Criteria

1. THE TOE_Aggregator SHALL compute, for each Eligible_Receiver and Split, `routes`, `targets`, `x_targets`, `toe` (targets − x_targets), `toe_per_100_routes`, `open_routes`, `open_rate` and `target_share`.
2. THE TOE_Aggregator SHALL produce the Splits All, Man, Zone and one Split per Coverage_Family, with Coverage_Type "Other" counted only in All.
3. WHERE the Split is a Coverage_Family, THE TOE_Aggregator SHALL also aggregate the Split by Position_Group.
4. THE TOE_Aggregator SHALL set `meets_minimum` to true when `routes` is at least Route_Minimum in the All Split or at least Split_Route_Minimum in any other Split.
5. WHEN aggregation runs, THE TOE_Aggregator SHALL report the minimum, quartiles and maximum of routes per receiver in the All Split, so the team can set Route_Minimum on the day.
6. THE TOE_Aggregator SHALL write the Receiver_TOE_Table to Derived_Dir with the columns, types and key defined in Contract C4.
7. FOR ALL Splits, the sum of `toe` over all receivers SHALL equal 0 within 1e-6.
8. FOR ALL rows, `open_rate` and `target_share` SHALL lie in [0, 1] and `targets` SHALL be at most `routes`.
9. FOR ALL receivers, Man `routes` plus Zone `routes` SHALL be at most All `routes`.

### Requirement 17: [Metrics] [P1] Team views (C5)

**User Story:** As a coach, I want each offense's and defense's profile, so that I can see which offenses funnel the ball to a favourite and which defenses leave receivers open that QBs then ignore.

#### Acceptance Criteria

1. THE TOE_Aggregator SHALL compute, for each offense, `model_plays`, `routes` and Team_Funnel_Index.
2. THE TOE_Aggregator SHALL name, for each offense, the receiver with the highest TOE and the receiver with the lowest TOE among receivers with at least Team_Route_Minimum Routes for that team.
3. THE TOE_Aggregator SHALL compute, for each defense, `model_plays`, `ignored_open_events`, Ignored_Open_Rate and the mean Separation of the Most_Open receiver at the Pre_Release_Offset.
4. THE TOE_Aggregator SHALL write the Offense_Team_Table and Defense_Team_Table to Derived_Dir as defined in Contract C5.
5. FOR ALL offenses, the sum of TOE over the offense's Routes SHALL equal 0 within 1e-6, and Team_Funnel_Index SHALL be non-negative.

### Requirement 18: [Metrics] [P1] Who gets the ball instead (C6)

**User Story:** As a coach, I want to know who got the ball when the most open receiver was ignored, so that I can spot patterns such as "open slot WR ignored, covered TE targeted."

#### Acceptance Criteria

1. WHEN a Model_Play's Most_Open receiver is not the Target, THE Instead_Analyzer SHALL record one Ignored_Open_Event.
2. THE Instead_Analyzer SHALL write the Instead_Table to Derived_Dir with the columns and key defined in Contract C6.
3. FOR ALL Ignored_Open_Events, `ignored_nflId` SHALL differ from `target_nflId` and both SHALL be Eligible_Receivers on the same play.
4. FOR ALL Ignored_Open_Events, `openness_gap` SHALL be greater than or equal to 0.
5. FOR ALL configured games, the number of Instead_Table rows SHALL equal the number of Model_Plays where the Most_Open Route is not the Target Route.

### Requirement 19: [Metrics] [P1] Release vs. pre-release robustness

**User Story:** As the Metrics owner, I want to show the result does not depend on defenders breaking on the ball, so that judges trust the openness measure.

#### Acceptance Criteria

1. THE Expected_Target_Model SHALL fit a second model using `openness_rel` in place of `openness_pre` and store the result as `xtarget_rel`.
2. WHEN both models are fitted, THE TOE_Aggregator SHALL report the Spearman correlation between release-based and pre-release-based TOE for receivers meeting Route_Minimum in the All Split.
3. WHEN both models are fitted, THE TOE_Aggregator SHALL report how many of the top-10 over-targeted and top-10 ignored receivers appear in both versions.

### Requirement 20: [Metrics] [P0] Publish and validate the Metrics contracts

**User Story:** As the Story owner, I want C3–C6 checked and available as fixtures, so that charts and the README are built before the final numbers land.

#### Acceptance Criteria

1. THE Contract_Validator SHALL check C3, C4, C5 and C6 for column names, types, allowed values, key uniqueness and nullability.
2. IF a table fails a contract check, THEN THE Contract_Validator SHALL raise an error listing every violated rule.
3. THE Fixture_Generator SHALL produce synthetic C3, C4, C5 and C6 tables of at least 20 receivers and 4 teams that pass the Contract_Validator and satisfy the invariants in Requirements 14.4, 16.7 and 17.5.
4. FOR ALL Receiver_TOE_Table rows, `nflId` SHALL exist in `players.csv`.
5. FOR ALL Instead_Table rows, the (`gameId`, `playId`) pair SHALL exist in the Route_Features_Table.

### Requirement 21: [Metrics] [Optional] Pressure split (stretch 1)

**User Story:** As a coach, I want to know whether open receivers are ignored more when the pocket collapses, so that I can tie the finding to protection.

#### Acceptance Criteria

1. WHERE the pressure split is enabled in Config, THE TOE_Aggregator SHALL add the Splits "Pressured" and "Clean" to the Receiver_TOE_Table.
2. WHERE the pressure split is enabled in Config, THE TOE_Aggregator SHALL report Ignored_Open_Rate separately for Pressured and Clean Model_Plays.
3. WHERE the pressure split is enabled in Config, THE TOE_Aggregator SHALL report Ignored_Open_Rate by Rusher_Distance band (under 2 yards, 2–4 yards, over 4 yards).

### Requirement 22: [Metrics] [Optional] Down-and-distance value (stretch 2)

**User Story:** As a coach, I want an ignored receiver to count only when a catch would have kept the drive on schedule, so that the headline reflects useful openness.

#### Acceptance Criteria

1. WHERE down-and-distance metrics are enabled, THE TOE_Aggregator SHALL set each Model_Play's required gain to 40% of `yardsToGo` on 1st down, 60% on 2nd down and 100% on 3rd and 4th down.
2. WHERE down-and-distance metrics are enabled, THE TOE_Aggregator SHALL mark a Route as at success depth when `depth` plus the Config YAC allowance (default 0 yards) is at least the required gain.
3. WHERE down-and-distance metrics are enabled, THE TOE_Aggregator SHALL compute per receiver the useful-open rate (Routes with Open_Flag and success depth ÷ Routes) and the ignored-useful rate (Routes with Open_Flag and success depth that were not targeted ÷ Routes).
4. WHERE down-and-distance metrics are enabled, THE TOE_Aggregator SHALL count, per QB and per offense, short-of-sticks throws: 3rd- and 4th-down Model_Plays where the Target's `depth_vs_sticks` is below 0 and a non-target Route has Separation of at least Open_Threshold and `depth_vs_sticks` of at least 0.
5. WHERE down-and-distance metrics are enabled, THE TOE_Aggregator SHALL label these outputs as "depth at the throw".
6. FOR ALL Model_Plays on 3rd or 4th down, the required gain SHALL equal `yardsToGo`, and FOR ALL downs, the required gain SHALL increase with `yardsToGo`.

### Requirement 23: [Metrics] [Optional] QB orientation toward the ignored receiver (stretch 3)

**User Story:** As a coach, I want to know whether the QB even faced the ignored receiver, so that I can tell a missed read from a deliberate choice.

#### Acceptance Criteria

1. WHERE orientation analysis is enabled, THE Openness_Calculator SHALL compute, for each Route, the angle in degrees between the QB's `o` at the Release_Frame and the bearing from the QB to the receiver.
2. FOR ALL Routes, the orientation angle SHALL lie in [0, 180] and SHALL be equal under raw and standardized coordinates within 1e-6.
3. WHERE orientation analysis is enabled, THE Instead_Analyzer SHALL report the share of Ignored_Open_Events where the orientation angle to the ignored receiver is 30° or less.
4. WHERE orientation analysis is enabled, THE Instead_Analyzer SHALL label the measure as body orientation, not eye direction.

### Requirement 24: [Metrics] [Optional] EPA value of the ignored option (stretch 4)

**User Story:** As a coach, I want the expected points left on the field by ignored receivers, so that the finding has a value attached.

#### Acceptance Criteria

1. WHERE the External_PBP_Table is available, THE Instead_Analyzer SHALL value each Ignored_Open_Event's ignored option at the mean `epa` of completions with the same down, `yardsToGo` band and depth band.
2. IF a down, `yardsToGo` band and depth band combination has fewer than 20 completions, THEN THE Instead_Analyzer SHALL set that event's option value to missing.
3. WHERE the External_PBP_Table is available, THE Instead_Analyzer SHALL sum (option value − actual play `epa`) per receiver, per offense and per QB.

## Workstream C: Story (Person C)

### Requirement 25: [Story] [P0] Repository and environment hygiene

**User Story:** As a judge, I want a public repo that runs from a clean clone, so that I can verify the result.

#### Acceptance Criteria

1. THE Repo SHALL be public and contain the Pipeline code, `requirements.txt`, the README and Outputs_Dir.
2. THE Repo SHALL list every third-party Python package the Pipeline imports in `requirements.txt` with an exact pinned version.
3. THE Repo SHALL list the raw data directory and Derived_Dir in `.gitignore`.
4. THE Repo SHALL keep every committed file under 10 MB.
5. THE Pipeline SHALL provide one command that runs from the source CSVs to Outputs_Dir.
6. WHEN the Repo is freshly cloned, the data is placed as the README describes and `requirements.txt` is installed, THE Pipeline SHALL complete the one command without errors.

### Requirement 26: [Story] [P0] Play_Plotter for sanity checks

**User Story:** As the team, I want to plot single plays, so that we can confirm direction, targets and openness look right before trusting any aggregate.

#### Acceptance Criteria

1. WHEN given a `gameId`, `playId` and Snapshot_Offset, THE Play_Plotter SHALL draw that play's Snapshot_Table positions in standardized coordinates with offense, defense and ball shown in distinct colors and marker shapes.
2. THE Play_Plotter SHALL draw LOS_x and Line_to_Gain_x as vertical lines.
3. THE Play_Plotter SHALL label the Target by `displayName`.
4. WHERE the Route_Features_Table is available, THE Play_Plotter SHALL label the Most_Open receiver by `displayName` and annotate each Eligible_Receiver with Separation in yards.
5. THE Play_Plotter SHALL run on the C1 and C2 fixtures from the Fixture_Generator.

### Requirement 27: [Story] [P0] Headline chart

**User Story:** As a judge, I want one chart whose title states the finding, so that I understand the insight in seconds.

#### Acceptance Criteria

1. THE Chart_Builder SHALL plot Open_Rate on the x-axis against Target_Share on the y-axis for each receiver with `meets_minimum` true, in side-by-side Man and Zone panels with shared axes.
2. THE Chart_Builder SHALL draw the y = x line on each panel and label the area above it "Over-targeted" and the area below it "Open but ignored".
3. THE Chart_Builder SHALL label by `displayName` the 5 receivers farthest above and the 5 receivers farthest below the y = x line in each panel.
4. THE Chart_Builder SHALL set the chart title to a sentence that states the finding and includes at least one number from the Headline_Summary.
5. THE Chart_Builder SHALL distinguish Position_Group by both a colorblind-safe color and a marker shape.
6. THE Chart_Builder SHALL label each axis with the metric name and "share of routes".
7. THE Chart_Builder SHALL save the headline chart to Outputs_Dir as a PNG at 200 dpi or higher.
8. WHERE Config sets the headline x-axis to "expected_share", THE Chart_Builder SHALL plot `x_targets` ÷ `routes` on the x-axis, so the y = x line marks TOE = 0.

### Requirement 28: [Story] [P0] Over-targeted and ignored leaderboards

**User Story:** As a coach, I want the 10 most over-targeted and 10 most ignored receivers by name, so that I can act on specific players.

#### Acceptance Criteria

1. THE Chart_Builder SHALL list the 10 receivers with the highest TOE and the 10 receivers with the lowest TOE in the All Split among receivers with `meets_minimum` true.
2. THE Chart_Builder SHALL show for each listed receiver `displayName`, `team`, Position_Group, `routes`, `targets`, `x_targets`, `toe` and `open_rate`.
3. THE Chart_Builder SHALL save both leaderboards to Outputs_Dir as CSV and as a Markdown table.
4. FOR ALL leaderboards, the over-targeted list SHALL be sorted by TOE descending, the ignored list SHALL be sorted by TOE ascending, and no receiver SHALL appear in both lists.

### Requirement 29: [Story] [P1] Team small multiples

**User Story:** As a coach, I want each offense's receivers side by side, so that I can see which offenses rely on one favourite.

#### Acceptance Criteria

1. THE Chart_Builder SHALL draw one panel per offense with a bar for each receiver with at least Team_Route_Minimum Routes for that team, sorted from highest to lowest TOE.
2. THE Chart_Builder SHALL order the panels by Team_Funnel_Index, highest first, and use one shared y-axis scale.
3. THE Chart_Builder SHALL title each panel with the team abbreviation and its Team_Funnel_Index.
4. THE Chart_Builder SHALL save the team chart to Outputs_Dir as a PNG at 200 dpi or higher.

### Requirement 30: [Story] [P1] Where the ball goes instead

**User Story:** As a coach, I want to see where the ball went when the most open receiver was ignored, so that I can see patterns like "WR open, RB checkdown."

#### Acceptance Criteria

1. THE Chart_Builder SHALL show counts of Ignored_Open_Events from the ignored receiver's Position_Group to the Target's Position_Group, in separate Man and Zone panels.
2. THE Chart_Builder SHALL annotate each position-to-position cell or flow with its count and its share of the panel's events.
3. THE Chart_Builder SHALL save the chart to Outputs_Dir as a PNG at 200 dpi or higher.

### Requirement 31: [Story] [P1] Coverage profile

**User Story:** As a coach, I want to see who gets open against man and who only against zone, so that I can plan matchups.

#### Acceptance Criteria

1. THE Chart_Builder SHALL plot man Open_Rate on the x-axis against zone Open_Rate on the y-axis for each receiver meeting Split_Route_Minimum in both Splits, with the y = x line drawn.
2. THE Chart_Builder SHALL label by `displayName` the 5 receivers with the largest positive and the 5 with the largest negative difference between man and zone Open_Rate.
3. THE Chart_Builder SHALL save the chart to Outputs_Dir as a PNG at 200 dpi or higher.

### Requirement 32: [Story] [P0] Headline_Summary and README

**User Story:** As a judge, I want a short README with the question, method and finding, so that I can assess the insight quickly.

#### Acceptance Criteria

1. THE Chart_Builder SHALL write the Headline_Summary to Outputs_Dir with every number quoted in the README insight summary and the headline chart title.
2. THE README SHALL open with an insight summary of 3 to 5 sentences that states the question, the method in one sentence, and the finding with at least one number and at least one named player.
3. THE README SHALL state the data source and the directory where the Pipeline expects the data.
4. THE README SHALL state the one command that runs the Pipeline.
5. THE README SHALL embed the headline chart from Outputs_Dir.
6. WHERE nflverse data is used, THE README SHALL cite nflverse.
7. WHERE FTN charting data is used, THE README SHALL credit FTN as its attribution licence requires.
8. FOR ALL numbers in the README insight summary, each number SHALL equal the corresponding Headline_Summary value at the stated precision.

### Requirement 33: [Story] [Optional] Fetch nflverse play-by-play (C7)

**User Story:** As the team, I want nflverse play-by-play joined to our plays, so that Data can fill missing targets and Metrics can value outcomes in EPA.

#### Acceptance Criteria

1. WHERE nflverse integration is enabled in Config, THE NFLverse_Fetcher SHALL download play-by-play for the dataset's season and cache the download in Derived_Dir.
2. WHERE nflverse integration is enabled in Config, THE NFLverse_Fetcher SHALL join on `gameId` = `old_game_id` and `playId` = `play_id` and write the External_PBP_Table as defined in Contract C7.
3. WHEN the join completes, THE NFLverse_Fetcher SHALL report the share of Throw_Plays with a joined row.
4. IF the download fails, THEN THE Pipeline SHALL continue without nflverse data and print a notice.

### Requirement 34: [Story] [Optional] Recent-games proxy (stretch 5)

**User Story:** As a coach, I want a current-season version of the idea, so that the insight applies to this week's games.

#### Acceptance Criteria

1. WHERE the recent-games proxy is enabled, THE NFLverse_Fetcher SHALL download the current-season play-by-play and Next Gen Stats weekly receiving data and record each source's last-updated date.
2. WHERE the recent-games proxy is enabled, THE Chart_Builder SHALL plot each receiver's NGS average separation against his share of team targets, joining NGS `player_gsis_id` to play-by-play `receiver_player_id`.
3. WHERE the recent-games proxy is enabled, THE Chart_Builder SHALL label the chart as a weekly-average proxy, not frame-level openness, and state the data's through-date.
4. WHERE FTN charting data is used, THE Chart_Builder SHALL report the share of each receiver's targets by `read_thrown` value.
5. IF a recent-games source is unavailable, THEN THE Pipeline SHALL skip the proxy and print a notice.

## Appendix A: Expected Source Columns

Checked against our copy of the data. The Data_Loader requires these columns; other columns may be present.

| File | Required columns |
| --- | --- |
| `games.csv` | gameId, season, week, homeTeamAbbr, visitorTeamAbbr |
| `plays.csv` | gameId, playId, playDescription, quarter, down, yardsToGo, possessionTeam, defensiveTeam, gameClock, preSnapHomeScore, preSnapVisitorScore, passResult, playResult, absoluteYardlineNumber, dropBackType, pff_playAction, pff_passCoverage, pff_passCoverageType |
| `players.csv` | nflId, officialPosition, displayName |
| `pffScoutingData.csv` | gameId, playId, nflId, pff_role, pff_positionLinedUp, pff_hit, pff_hurry, pff_sack |
| `tracking/tracking_<gameId>.csv` | gameId, playId, nflId, frameId, team, playDirection, x, y, s, a, o, dir, event |

Reference values in our copy: `passResult` C 4,620, I 2,755, IN 190, S 543, R 449 (7,565 candidate throws). `pff_passCoverageType` Zone 5,588, Man 2,481, Other 488. Release events seen: "pass_forward", "autoevent_passforward". Snap events: "ball_snap", "autoevent_ballsnap". The ball has `team` "football" and missing `nflId`, `o` and `dir`. About 94% of throw descriptions use "to <name>" and 2.5% use "intended for <name>".
