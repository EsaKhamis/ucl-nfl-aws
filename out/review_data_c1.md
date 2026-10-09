**Verdict: PASS** (no HIGH or MEDIUM findings; 6 LOW)

# Data stage review: C1 snapshot table, eligibility and target matching

The Data stage reads each game's tracking, standardizes direction, finds the first snap and first release events, and writes C1: 23 rows (22 players + ball) per Throw_Play at offsets 0-5 before release. Eligibility comes from scouting role + players position + a tracking team check, and targets are parsed from `playDescription` and matched to the play's offensive players. I reviewed load.py, snapshot.py, targets.py, contracts_data.py and config.py, and ran data checks on `out/c1_snapshot.parquet`, `out/c2_plays.parquet` and `out/play_events_targets_all.parquet`. I found no metric-corrupting bugs in frame selection, standardization, side/eligibility or play isolation, either in the code or in the output. The 96.34% target match rate holds up: I found no false positives.

Watch for: the validator can't see a (play, offset) group that's missing entirely (confirmed gap, no current impact); two recoverable target losses, Aa./Am. Rodgers ambiguity and D.Harris → "Deonte Harty" (confirmed, 20 plays, recall only); three plays with a ball-tracking glitch about 30 yd from the QB (confirmed, data only).

**Verdict**: APPROVED

## High-level view

The snapshot frame is `max(release − offset, snap)`, where release and snap are each the first matching event per play. Offset 0 equals release_frameId on every play, and consecutive offsets are exactly one frame apart. Zero clamped rows is expected: the shortest release − snap gap in the data is 10 frames, and clamping needs fewer than 5.

C1 is built only from `read_tracking`, which standardizes before any other step. On every play, the `dir` values agree with frame-to-frame displacement after the flip. Side is `team == possessionTeam`, and every snapshot has exactly 11 offense, 11 defense and 1 ball. Eligibility adds the tracking team check that Req 4.1 requires, and C2 reuses the same eligible-receiver table, so C1 `is_eligible`, C2 `n_eligible` and the Model_Play targets agree on every play. All joins are keyed on (gameId, playId[, frameId, nflId]). players.csv and scouting are unique on their keys, so no join can multiply rows or leak them across plays.

Target matching takes the name right after the pass phrase and only considers offensive-role players, so tacklers, interceptors and defenders can't be picked up. The last-name fallback never fires in the data. The remaining gaps are recall losses and checks that would only matter if a future input changed.

## Data checks (a)-(e)

(a) Ball-to-QB distance at offset 0 (QB = pff_role 'Pass'): median 0.56 yd, p95 1.08 yd, p99 2.19 yd, over 7,541 plays. PASS. 27 plays are over 3 yd. Three of those are ball-tracking glitches about 30-33 yd off at every offset (see Issues 6).

(b) Mean x of eligible receivers rises from 63.07 at offset 5 to 64.95 at offset 0. The per-route mean gain is +1.88 yd, and 93.4% of routes move toward +x. PASS.

(c) `o` and `dir` are all within [0, 360). They are NaN on all 45,246 ball rows and on 0 player rows. Extra check: across 150,970 player rows with s > 1, the velocity derived from `dir` correlates with frame-to-frame displacement at 0.998 (vx) and 0.997 (vy), and no play shows a flipped sign. PASS.

(d) Exactly 1 QB in each of the 45,246 (play, offset) groups. PASS.

(e) Each (play, offset) group has exactly one frameId. All 37,705 consecutive-offset pairs step by −1. Offset 0 always equals release_frameId and offset 5 always equals release − 5. Clamped rows: 0. min(release − snap) = 10 frames (p1 = 15), so 0 clamped is plausible. PASS.

Also checked: 30 'Pass Route' rows per offset are correctly not eligible (26 QB, 3 C, 1 T). position_group holds only WR/TE/RB. No offense role appears on the defense side, and no defense role on the offense side. Every C2 key is in plays.csv and in C1. All 7,257 Model_Play targets are eligible in C1 (Req 9.5).

## Target match rate audit (96.34% vs ~91% expected)

Conclusion: the matches are real and I found no false positives. Of the 7,541 Throw_Plays, 7,285 (96.6%) name a receiver in the pass phrase, so that is the ceiling for any description-based matcher. The 96.34% (7,265) sits just under it: only 18 no_match and 2 ambiguous plays are lost. Status counts: matched 7,265, no_name 256, no_match 18, ambiguous 2. The ~91% expectation isn't in requirements.md or design.md; it probably came from a different denominator or a different source.

The last-name-only fallback produced 0 matches (no `matched_last_name` rows), so I can't show 10 fallback samples. All 7,265 matches come from initial + last name, and for every one the description key equals the matched player's displayName key.

10 random primary matches (seed 1), all correct:
- 2021091213/3224 "pass incomplete short middle to T.Higbee" → Tyler Higbee (TE)
- 2021103109/75 "pass short right to J.Agnew to JAX 35" → Jamal Agnew (WR)
- 2021100302/2054 "pass incomplete deep left to A.St. Brown" → Amon-Ra St. Brown (WR)
- 2021091300/3712 "pass incomplete short middle to D.Waller [C.Campbell]" → Darren Waller (TE)
- 2021100306/2111 "pass short right to K.Golladay to NO 40" → Kenny Golladay (WR)
- 2021092606/814 "pass incomplete short middle to O.Zaccheaus" → Olamide Zaccheaus (WR)
- 2021103100/3769 "pass incomplete short right to T.Sharpe (R.Melvin)" → Tajae Sharpe (WR)
- 2021092603/3209 "pass short right to C.Edmonds to ARI 49" → Chase Edmonds (RB)
- 2021101100/2365 "pass short right to M.Brown to IND 12" → Marquise Brown (WR)
- 2021101800/2117 "pass deep right to C.Beasley for 29 yards, TOUCHDOWN" → Cole Beasley (WR)

No matched target is a defender. The candidates are limited to Pass, Pass Route and Pass Block roles, and the matched roles are Pass Route 7,262, Pass Block 2 and Pass 1. Six targets are QBs, and all six are named correctly in the description: T.Heinicke caught his own batted pass (2021092600/3516, the only 'Pass' role match), and five are Taysom Hill on 'Pass Route'. The two Pass Block matches are A.Hooper and H.Vaitai (Vaitai's play was an illegal-touch No Play). None of these 8 is a Model_Play, so Model_Plays = 7,257.

'pass incomplete' with no name: 181 such descriptions among Throw_Plays, 0 counted as matched.

38 plays (reversed or challenged) contain more than one pass phrase, and the names never disagree, so the last-occurrence rule doesn't change any result.

Independent cross-check: BDB 2023 tracking usually ends soon after the throw, so only 399 matched throws have an arrival or outcome frame. On those, the target is the offensive player nearest the ball on 96.9% of completions (313/323). The 10 misses are short throws where a lineman, QB or RB was closer and the named target was 2-6 yd away. None of them looks like a wrong name.

<details>
<summary>Issues (6)</summary>

1. **Missing (play, offset) groups invisible** (LOW, confirmed): if a snapshot frame is missing from tracking, the inner merge drops the whole group. Neither `frame_count_issues` nor `validate_c1` would notice. In `build_c1`, assert that the number of (gameId, playId, offset) groups equals 6 × Throw_Plays.
2. **C1 validator missing three rules** (LOW, confirmed): `c1_extra_checks` doesn't check that `is_eligible` implies side 'offense' and pff_role 'Pass Route', doesn't check frameId stepping/`clamped` consistency across offsets, and doesn't check that player-row o/dir are non-null. Add these three checks; today's data passes all of them.
3. **Req 9.4/9.5 not asserted** (LOW, confirmed): `snapshot.build` writes C1 and C2 without the referential-integrity and Model_Play-target-eligible asserts the design calls for. Add both after `build_c2`; both hold today.
4. **Aa./Am. Rodgers collapse** (LOW, confirmed): `description_key` keeps only the first letter, so "Am.Rodgers" (WR) and Aaron Rodgers (QB) both key to (a, rodgers) and 2 GB throws end up ambiguous. When a match is ambiguous, break the tie by checking whether the displayName's first name starts with the full prefix.
5. **D.Harris → "Deonte Harty"** (LOW, confirmed): players.csv uses his new name, so all 18 no_match throws are this player. Add a one-entry alias for (d, harris) → (d, harty), applied only within the play's offensive players.
6. **Ball-tracking glitches** (LOW, confirmed, data not code): on 2021091212/912, 2021091203/1041 and 2021091905/876 the ball is 30-33 yd from the QB at every offset. Flag these in the Data_Report, and drop them if any metric ever uses the ball position (the current design uses the QB row).

</details>

<details>
<summary>Details</summary>

### Silent group loss in snapshot_rows

`snapshot_rows` (snapshot.py:281) inner-merges the wanted frames with tracking. If a wanted frame doesn't exist in a play's tracking, that (play, offset) group disappears. `frame_count_issues` (snapshot.py:321) only groups rows that exist, and `validate_c1` has no completeness rule, so the loss would be silent: Metrics would get a play that has, say, no offset 4 rows. This is a confirmed code gap, but it doesn't occur in the current output (1,040,658 = 7,541 × 6 × 23), so it only matters for future reruns (Issue 1).

### Non-obvious choices in standardization and joins

On right plays, `standardize` (load.py:173) maps a raw 360.0 to 0.0. That departs from Req 2.2's "unchanged", on purpose, to keep the [0, 360) contract, and it changes nothing physically. In `finish_c1` (snapshot.py:310), ball rows join scouting and the eligible-receiver table on a null nflId, and pandas matches null merge keys to each other. Neither table has null nflIds today. If one ever did, the ball row would pick up a pff_role or be duplicated, and the validator's ball-row and key-uniqueness checks would fail the write, so this fails closed.

### Name-key truncation in targets.py

`description_key` (targets.py:54) keeps only the first letter of the description prefix. The play-by-play writer uses two-letter prefixes such as "Aa."/"Am."/"Jon." precisely to tell apart teammates who share an initial, so truncating them turns that disambiguation into an ambiguous match (Issue 4; fail-closed: target left null). Separately, the NAME pattern (targets.py:30) allows a space in a last name only after "St.", so a name like "X.Vander Laan" would be cut to "Vander". This is confirmed regex behavior, but none of the current 18 no_match plays comes from it.

### Gaps in the C1 validator

`c1_extra_checks` (contracts_data.py:150-190) doesn't enforce the three rules in Issue 2. Each guards against a real class of upstream regression: an eligible row on the defense (team-check regression), an offset off-by-one (frameId not stepping by −1 unless clamped), and NaN player angles reaching the Closing_Speed calculation. The current data passes all three (checks c and e, plus the side checks).

</details>

<details>
<summary>File map</summary>

- load.py: source loaders with Appendix A column checks; `standardize`, `add_los_x`, `snap_frames`, direction checks and the Data_Report counts.
- snapshot.py: event frames, Throw_Play classification, route runners and eligibility, and the C1 build (`read_tracking` → `snapshot_frames` → `snapshot_rows` → `finish_c1`), validation and write.
- targets.py: pass-phrase regex, name keys, matching with a last-name fallback, Model_Play flags, the round-trip test and the Req 5 report.
- contracts_data.py: C1/C2 schemas, `validate`, C1/C2 extra checks and the seeded fixtures.
- config.py: the Config dataclass with path resolution and offset/open-mode validation.

These are uncommitted working-tree files, so there is no diff; I reviewed the files directly.

</details>
