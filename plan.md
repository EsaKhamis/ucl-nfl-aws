# NFL Big Data Bowl London — Team Brief

Oct 8, 2026 · @esa

## Event and rules

We get 3 hours (10:00 AM to 1:00 PM, Friday 9 October 2026, BaseKX London) to build a data story about **skill-position players (WR/TE/RB)**, using Python and Kiro. Our idea about QB decisions has to be framed around the receivers.

**Rules that shape our plan**

- **Ideas only before the event.** No code, visualizations or written analysis may be prepared in advance. This doc is a planning brief: none of it goes into the submission, and all code is written on-site.
- **The provided dataset is mandatory.** The organizers distribute the dataset and challenge prompt at the start, and they may differ from the copy we have. External data is allowed if it is publicly available.
- **Open-source libraries are fine.** We may not build a library for the event in advance.
- **Teams of up to 3.** Everyone must be present and contribute.
- **Submissions close at 1:00 PM sharp.** We submit a public repo containing:
  - working code
  - a 3 to 5 sentence README describing the insight
  - the visualization or metric output
- **Media rights:** by taking part we grant AWS and the NFL the right to publish our code and presentation.

## Judging

We are judged on four criteria, so the project should be a simple, correct metric with one strong chart, not a complex model. The full rubric is handed out at the start of the event.

| Criterion | What it means for us |
| --- | --- |
| Football Insight | One finding a coach would act on, e.g. "these receivers are open but ignored under pressure." Name real players. |
| Technical Execution | Code that runs end to end in the repo. Sound joins, play direction standardized, no leakage between plays. |
| Communication | One headline chart plus a clear README. Its title states the finding, not the topic. |
| Originality | Use tracking data in a way that box-score stats cannot: openness at the throw, where the QB is facing, coverage disguise. |

## Data structure

Our copy is the Big Data Bowl 2023 dataset: **8,557 pass plays from 122 games, 2021 Weeks 1 to 8**. Its theme is pass rush and protection. Every file joins on `gameId`, `playId` and `nflId`.

| File | One row = | Size | Key fields |
| --- | --- | --- | --- |
| `games.csv` | a game | 122 rows | `gameId`, week, home and away teams |
| `plays.csv` | a pass play | 8,557 rows | down, distance, field position, score, clock, formation, personnel, defenders in box, coverage (`pff_passCoverage`, man or zone), play action, `passResult`, `playResult` (yards) |
| `players.csv` | a player | 1,679 rows | `nflId`, position, height, weight, birth date, name |
| `pffScoutingData.csv` | a player on a play | 188,254 rows | role (Pass Route, Pass Block, Pass Rush, Coverage, Pass), where he lined up, hit, hurry or sack, who blocked whom, block type |
| `tracking/tracking_<gameId>.csv` | a player or the ball in a 0.1 s frame | 122 files, 811 MB, \~8.3M rows | x, y, speed, acceleration, orientation (`o`), direction (`dir`), events (snap, pass forward, sack) |

**Points to remember**

- **Tracking stops when the pass is thrown, or at the sack or scramble**, about 4 s after the snap on average. There is nothing after the catch, so separation downfield and yards after catch are not measurable.
- **Only about 0.5 s before the snap** is tracked, so we get the alignment at the snap but little pre-snap motion.
- **The dataset has no target column.** We can recover the targeted receiver for 91% of throws by matching the name in `playDescription` ("pass deep left to A.Cooper") to the players on the play.
- **Play direction is mixed.** Flip x, y, `o` and `dir` so offense always moves the same way.
- **The ball has no `nflId`.** Each frame has 23 rows: 22 players and the ball.
- **Use the PFF labels.** Pressure (a hit, hurry or sack) happens on 37% of plays. Coverage: 5,588 zone, 2,481 man.
- **Split by game or week**, never by frame.
- **Prototype on one game file**, then loop over all 122. The full tracking set is large.

## What we can derive

The most valuable derived data is a snapshot at the release frame: where every receiver and defender is at the moment the QB decides.

| Source | What we can build | Use for receivers |
| --- | --- | --- |
| `playDescription` text | Targeted receiver, throw depth (short or deep), direction (left, middle, right), tackler or defender named | Who was chosen, and the throw type |
| Tracking, receivers | Separation from the nearest defender at release, the defender's closing speed, depth vs. the first-down marker, distance from the QB, a basic route shape | **Openness of every option**, not just the target |
| Tracking, QB | Time to throw, dropback depth, speed at release, orientation frame by frame | Where he looked and how long he had |
| Tracking, pressure | Distance from the nearest rusher to the QB per frame, pocket area, time to first pressure | The pressure context of each decision |
| Tracking, defense | Safety shell at the snap (two deep vs. one deep), rotation after the snap, number of deep defenders at release | Coverage disguise |
| Scouting labels | RB and TE roles (route vs. block), chip blocks (`CH`), set-and-release (`SR`), backfield pickups (`PU`) | How often RBs and TEs are kept in to block, and what it costs the route |
| Joined files | Player age and size, per-player history over Weeks 1 to 8, game state (score margin, time left) | Receiver profiles and context |

Orientation is a usable signal for where the QB is looking. At release it is within 30° of the target on 64% of throws, with a median gap of 23°. It measures the body, not the eyes.

## Our idea: Open but Ignored vs. Over-Targeted

**When a receiver gets open, does the QB throw to him, and if not, who gets the ball instead?** We score every WR, TE and RB's openness at the throw, estimate how often an open receiver *should* be targeted, and compare that with who actually got the ball, split by coverage.

### How it works

1. **Openness.** For every route runner at the throw: separation from the nearest defender, plus that defender's closing speed. "Open" = the most open option on the play, or above a separation threshold we choose from the data on the day.
2. **Expected targets.** A simple logistic model gives each receiver a probability of being targeted, from openness, depth, distance from the QB and pressure at the throw. It is fit on all plays.
3. **Targets over expected (TOE).** Actual targets minus expected targets. Positive = **over-targeted**: the QB's favourite, who gets the ball even when covered. Negative = **open but ignored**.
4. **Split by coverage.** Man vs. zone for every player. Go deeper, to coverage families (Cover-1, Cover-3, Quarters, Cover-2), only for position groups or the busiest receivers, because samples get thin.
5. **Split by team.** Sum TOE over each offense's receivers. This shows whether a team spreads the ball according to who is open or funnels it to one or two favourites, and names each team's most over-targeted and most ignored receiver. Each team has about 7 to 8 games in Weeks 1 to 8. On defense, flip it: which defenses leave receivers open that QBs then ignore.
6. **Who gets it instead.** On every play where an open receiver was ignored, record the actual target's position, depth and openness. This produces patterns such as "open slot WR ignored, covered TE targeted."

### What we show

- **Headline chart:** each receiver's open rate (x) against his target share (y), separated by man vs. zone. Players above the diagonal are over-targeted, players below are ignored. The extremes are labelled by name.
- **Two leaderboards:** the 10 most over-targeted and the 10 most ignored receivers, with their TOE.
- **Team view:** one small panel per offense (32), its receivers' TOE as bars sorted from most over-targeted to most ignored. Offenses that rely on a single receiver stand out next to offenses that spread the ball by openness.
- **Where the ball goes instead:** a flow from the ignored receiver's position to the target's position, e.g. WR to RB checkdown.
- **Coverage profile:** who gets open against man, who only against zone.

### Pitfalls to handle on the day

- **The QB's decision changes openness at the throw.** Defenders break on the ball as he winds up, so his target can look covered. Measure openness 3 to 5 frames (0.3 to 0.5 s) before release as well.
- **Deep routes are still developing at release.** That is why depth goes into the expected-target model.
- **Only route runners are eligible.** Filter on `pff_role` = Pass Route, so blocking TEs and RBs are excluded.
- **About 9% of throws have no matched target.** Drop them, or fill them from nflverse `receiver_player_id`.
- **Sample sizes are unknown.** Count each receiver's routes first, and set a minimum before ranking anyone.

### Stretch goals, in order

1. Add pressure as a fourth split: are open receivers ignored more when the pocket collapses?
2. **Down-and-distance value.** Measure each route runner's depth against the line to gain at the throw, and ask whether a catch there would have been a successful play for that down. This sharpens the core metric: an ignored receiver counts only if he was open and a catch would have kept the drive on track. Sum it per receiver, team and QB. Thresholds and metrics are below.
3. Use the QB's orientation: did he even look toward the ignored receiver?
4. nflverse EPA: what the ignored option was worth compared with the throw he made.
5. **Recent games.** Player tracking for recent games is not publicly available, so the openness model cannot be rerun on them. A lighter proxy: nflverse play-by-play for the current season gives targets, and nflverse Next Gen Stats weekly receiving data gives each receiver's average separation. Together they produce target share vs. average separation, by receiver and team, for the latest weeks. Check how recently each source was updated on the day, and label the chart as a weekly-average proxy, not frame-level openness.

**Down-and-distance stretch goal: what counts as a useful target**

| Down | A catch is a success if it gains | What we look for |
| --- | --- | --- |
| 1st | 40% of yards to go | Any open receiver past the line of scrimmage is useful. Extra depth is a bonus. |
| 2nd | 60% of yards to go | Separate "on schedule" depth from big-play depth (e.g. 15+ yards downfield). |
| 3rd and 4th | 100% of yards to go | Depth past the sticks. Did the QB throw short of the sticks while someone was open past them? |

The 40/60/100% thresholds are the standard "success rate" definition used in football analytics. Metrics to build:

- **Depth vs. sticks:** each receiver's yards past (+) or short of (−) the line to gain at the throw.
- **Useful-open rate:** the share of a receiver's routes where he is open *and* at success depth.
- **Ignored-useful rate:** open at success depth but not targeted. This is the sharper version of our headline.
- **Short-of-sticks throws:** 3rd- and 4th-down throws behind the sticks while a receiver was open past them, per QB and team.
- **Expected-points value (needs nflverse 2021 play-by-play):** value each open receiver at the average EPA of completions at that down, distance and depth. Sum the EPA left on the field by ignored receivers.

Caveat: depth at the throw is not the catch point. Receivers keep running and yards after catch can turn a short catch into a first down. Either add a fixed yards-after-catch allowance, or present it plainly as "depth at the throw."

## External data

The most useful source is nflverse play-by-play: it joins one-to-one with our plays and adds the value of each outcome (EPA, expected points added). Download it on the day, matching the **season of the dataset we are given**. Our copy is 2021, but the event dataset may differ.

| Source | Join | What it adds |
| --- | --- | --- |
| [nflverse](https://nflverse.nflverse.com/) play-by-play | `gameId` = `old_game_id`, `playId` = `play_id` (per our README) | EPA per play, `receiver_player_id` (the official target, filling our 9% gap), air yards, yards after catch, CPOE, pass location, win probability |
| nflverse Next Gen Stats (weekly receiving and passing) | Player and week | Official separation, cushion and QB time-to-throw numbers to check our own metrics against |
| [Pro Football Reference](https://www.pro-football-reference.com/) | Player name and season | Season stats and context for the players we highlight |

The Python packages `nfl_data_py` and `nflreadpy` load nflverse data in one line. Both are open source, so the library rule is met. The sources for the 2021 dataset are cited from our README. The 2026 sources below were downloaded and checked.

### Up-to-date sources for recent games (checked 9 Oct 2026)

There is **no public player tracking for recent games**, but nflverse updates every night and covers 2026 Weeks 1 to 5. Four files cover the recent-games stretch goal. All are on the [nflverse-data releases page](https://github.com/nflverse/nflverse-data/releases).

| Source | Covers | Updated | What it gives us |
| --- | --- | --- | --- |
| [Play-by-play 2026](https://github.com/nflverse/nflverse-data/releases/tag/pbp) | Weeks 1–5, 65 games, 4,585 pass attempts, through Thursday 8 Oct | 9 Oct, 04:32 UTC | Target (`receiver_player_id`, 89% of attempts), EPA, air yards, YAC, CPOE, pass location and length. No coverage type. |
| [FTN charting 2026](https://github.com/nflverse/nflverse-data/releases/tag/ftn_charting) | Weeks 1–4 | 8 Oct | **`read_thrown`**: which read the QB threw to (1st, 2nd, checkdown `CHK`, plus `SD` and `DES`, to confirm on the day). Also contested ball, catchable ball, blitzers, pass rushers, play action. |
| [Next Gen Stats receiving](https://github.com/nflverse/nflverse-data/releases/tag/nextgen_stats) | Weeks 1–5 (Week 5 only partly in), \~70–75 qualifying receivers a week | 9 Oct | Average separation and cushion per receiver per week, targets, share of intended air yards. WR and TE only, no RBs. |
| [PFR advanced receiving](https://github.com/nflverse/nflverse-data/releases/tag/pfr_advstats) | Weeks 1–4 | 8 Oct | Drops, drop rate, broken tackles, passer rating when targeted |

**How they join:** FTN `nflverse_game_id` + `nflverse_play_id` match play-by-play `game_id` + `play_id`. NGS `player_gsis_id` matches play-by-play `receiver_player_id`.

**The recent-games version of our idea:** NGS average separation (how open) vs. target share from play-by-play (how often thrown to), per receiver and per team. FTN's `read_thrown` adds whether those targets came on the first read or later in the progression. It's a weekly-average proxy, not frame-level openness.

FTN data is shared under an attribution licence; credit FTN in our README if we use it.

## Game plan for the day

Stop adding analysis at 12:15 so the last 45 minutes go to the chart, the README and pushing the repo. A finished simple story beats an unfinished ambitious one.

1. **10:00–10:20:** Read the prompt and rubric, check that the dataset matches what we expect, and lock the idea. Create the public repo.
2. **10:20–11:00:** Load the files, standardize play direction, find each throw's target, and build the release-frame table: one row per eligible receiver per play.
3. **11:00–11:45:** Compute openness, pressure at release and coverage type. Sanity-check a few plays by plotting them.
4. **11:45–12:15:** Fit expected targets, compute TOE by receiver and by coverage (man vs. zone first, then coverage families), and find the headline. Add the nflverse join only if it's quick.
5. **12:15–12:45:** Make the headline chart and one supporting chart. Write the README.
6. **12:45–13:00:** Final push and check the repo from a clean clone. **Submit before 1:00 PM.**

**Suggested split for 3 people**

- **Data:** loading, joins, target matching, the release-frame table.
- **Metrics:** openness and pressure features, the aggregation.
- **Story:** football framing, charts, README, repo hygiene. Can also pull nflverse.

**Submission checklist**

- [ ] Public repo, created and pushed early
- [ ] Code runs top to bottom, with a `requirements.txt`
- [ ] README of 3 to 5 sentences: the question, the method in one line, the finding with a number
- [ ] The headline visualization or metric table committed to the repo
- [ ] No large data files committed; the README says where the data comes from
- [ ] Submitted before 1:00 PM

## Open questions and risks

- **Is the event dataset the same as our copy?** If it covers a different season, or tracks plays past the throw, idea 3 (separation) gets stronger and we can measure yards after catch. Decide at 10:00.
- **What does the challenge prompt actually ask?** It is only released at the start. Our ideas assume it is open-ended around skill-position players.
- **Which time zone?** The listing says "9:00 AM – 3:00 PM ET" for a London venue. We assume UK local time; confirm before travelling.
- **Does this brief break the no-advance-work rule?** It holds ideas and a description of the data, which the rules encourage, but none of its text or numbers go into the submission unchanged.
- **Will the libraries be available?** Plan on pandas, numpy, matplotlib or plotly, and scikit-learn. Check that Kiro and the venue Wi-Fi allow installs.
