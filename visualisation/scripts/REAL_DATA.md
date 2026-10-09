# Real Data Pipeline

This document describes the real-data ETL that feeds the NFL "Target Over
Expectation" (TOE) dashboard. It is the no-tracking **proxy** pipeline.

## Source dataset

- **NFL Big Data Bowl 2023** CSVs, **2021 season, weeks 1–8**.
- Absolute source directory (read-only, never modified by the pipeline):
  `c:\Users\yousu\OneDrive\Documents\GitHub\ucl-nfl-aws\data`
- Files used: `games.csv`, `players.csv`, `plays.csv`, `pffScoutingData.csv`.
- The `tracking/` folder is **ignored on purpose** — this pipeline derives
  everything from play-by-play and PFF scouting roles, not player tracking.
- `NA` is the literal missing-value string. Team abbreviation `LA` (LA Rams) is
  mapped to `LAR` on output; all other abbreviations are already standard.

## Regenerate

From the `visualisation` folder:

```bash
node scripts/build-real-data.mjs
# or
npm run data:real
```

This writes two identical files:

- `public/data/receivers.json` — the file the dashboard loads.
- `public/data/receivers.real.json` — identical backup copy.

## Output shape

The dashboard (`src/context/DashboardProvider.tsx`, `src/lib/types.ts`,
`scripts/check-data.mjs`) requires a **wrapped object**, so the pipeline emits:

```jsonc
{
  "schemaVersion": "1.0.0-real",
  "generatedAt": "<ISO timestamp>",
  "expectationModel": { "formula": "...", "a": <number>, "b": <number> },
  "receivers": [ /* one ReceiverWeekRow per player per week */ ]
}
```

Each `receivers[]` row has exactly these fields (rate fields rounded to 4
decimals; counts are integers):

`playerId, playerName, team, position, week, opponent, gameId, routesRun,
targets, receptions, yards, openRate, targetShare, expectedTargetShare, toe,
openRateVsMan, openRateVsZone, targetShareVsMan, targetShareVsZone`.

> **Note on the envelope.** A plain JSON array would break the dashboard (its
> loader reads `file.receivers` and `file.expectationModel` and throws
> otherwise). Keeping the UI working with zero code changes is the hard
> requirement, so the wrapper is used while every per-row field matches the
> required schema exactly.

## Derivations

Position map: `WR→WR`, `TE→TE`, `RB/HB/FB→RB`; all others (QB/OL/defense) are
dropped. Only players who ran at least one pass route in a week are emitted.

1. **Routes.** Each `pffScoutingData` row with `pff_role == "Pass Route"` is one
   route for `(gameId, playId, nflId)`. Joined to `plays` for `possessionTeam`
   and `pff_passCoverageType`, and to `games` for `week`.
   `routesRun` = count of a player's Pass Route rows in the week. The player's
   **team** for the week is the mode of `possessionTeam` over their route plays;
   **opponent** is the mode of `defensiveTeam`; emitted `gameId` is the game they
   ran the most routes in that week.

2. **Targets.** The targeted receiver is parsed from `playDescription` via
   `… to <token>` (falling back to `… intended for <token>` for interceptions).
   `<token>` is `firstInitials + "." + lastName` as the NFL gamebook renders it.
   Each roster player's token is rebuilt from `displayName` and matched
   case-insensitively (trailing `.` ignored, internal spaces removed).
   `targets` = count of the week's plays where the player was the matched target.
   `teamTargets(week)` = number of that team's pass plays in the week whose
   target **parsed and matched** a kept skill player (so shares sum sensibly;
   throw-aways, spikes, sacks and unmatched targets are excluded from the base).

   **Name-matching caveats handled defensively:**
   - Compound first initials are rendered **inconsistently** by the gamebook —
     e.g. `D.J. Moore → "Dj.Moore"` (both initials) but
     `T.J. Hockenson/K.J. Osborn/D.J. Chark → "T.Hockenson"/…` (first initial
     only). Each player therefore gets **two candidate tokens** (full
     concatenated initials and first-initial-only); a match on either counts.
     Verified: zero within-team collisions on the first-initial form.
   - Prefixed last names like `Amon-Ra St. Brown` render as `A.St. Brown`
     (with a space); tokens drop internal spaces so both sides compare equal.
   - Hyphen (`Peoples-Jones`) and apostrophe (`O'Connell`) names are preserved.
   - If a token is still ambiguous within a team, the player who ran a route on
     that same play wins.

3. **Receptions / yards.** A matched target with `passResult == "C"` is a
   reception. `yards` is parsed from `"for <N> yards"` (negative allowed);
   `"no gain"` → 0. Any target whose yardage cannot be parsed contributes 0
   yards.

4. **targetShare** = `playerTargets / teamTargets(week)`, clamped 0..1.

5. **expectedTargetShare** = `routesRun / teamRoutes(week)`, where
   `teamRoutes(week)` is the sum of `routesRun` over that team's kept WR/TE/RB
   that week. **This is the swappable expectation baseline:** route
   participation. Rationale — a player who runs ~30% of the team's routes is
   "expected" to earn ~30% of its targets. Clamped 0..1.

6. **toe** = `round(targetShare − expectedTargetShare, 4)`. May be negative.

7. **openRate** = **PROXY** = `round(targets / routesRun, 4)`, clamped 0..1.
   This is a **target-rate proxy** for separation, used only because the
   no-tracking pipeline cannot measure true openness. Rows with `routesRun == 0`
   are dropped. Treat it as "how often this route turned into a target," not as
   measured separation. It is the first thing to replace once tracking-based
   separation is available.

8. **Man / Zone splits.** Routes and targets are recomputed restricted to plays
   with `pff_passCoverageType == "Man"` vs `"Zone"` (`"Other"` excluded).
   - `openRateVsMan = targetsVsMan / routesVsMan` (0 if `routesVsMan == 0`);
     `openRateVsZone` likewise.
   - `targetShareVsMan = playerTargetsVsMan / teamTargetsVsMan(week)` (0 if the
     denominator is 0); `targetShareVsZone` likewise.

## Expectation model `a` / `b` (display only)

The dashboard shows the model as text `(a=…, b=…)` but **does not** recompute
per-row `toe` from `a`/`b` — it reads `row.targetShare − row.expectedTargetShare`
directly. To keep the displayed line meaningful rather than a placeholder, the
pipeline fits a simple ordinary-least-squares line
`expectedTargetShare ≈ a + b·openRate` over the emitted rows and stores those
real `a`/`b`. The authoritative per-row `expectedTargetShare` remains the
route-participation value from derivation 5; the fitted `a`/`b` are informational
only.

## Consistency guarantees

Asserted before the files are written (the build exits non-zero on failure):

- `receptions ≤ targets ≤ routesRun` on every row.
- `toe == targetShare − expectedTargetShare` within 1e-9.
- Every rate field is within `[0, 1]`.
- 32 distinct teams, weeks 1–8.

`node scripts/check-data.mjs` (the dashboard's own gate) also passes against the
generated file.

## Swapping in future / different data

Point `SRC_DIR` at a dataset with the same column names and rerun. The two most
likely upgrades: replace the `openRate` target-rate proxy with a tracking-based
separation measure, and/or swap the route-participation expectation baseline in
derivation 5 for a richer model.
