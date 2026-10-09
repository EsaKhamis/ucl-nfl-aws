# NFL TOE Broadcast Dashboard

A clean, high-contrast, single-page web dashboard for NFL receiver **Target Over
Expectation (TOE)** analytics. Built for broadcasters, color commentators, and
analysts who need three strong, visual, data-backed talking points in under 10
seconds.

Every view is story-first and scannable: big numbers, bold player names, the
most over-targeted and most ignored receivers impossible to miss, and
broadcast-style filters (Week, Position, Coverage, Current Game) plus a
**Story Mode** toggle that surfaces the strongest narratives for the current
view.

## Sections

1. **Headline Chart** — hero scatter, x = Open Rate, y = Target Share, with a
   thick diagonal expectation line; only the ~3-4 most over-targeted and ~3-4
   most ignored players are labelled.
2. **Leaderboards** — side-by-side "Most Over-Targeted" and "Most Ignored /
   Coach I Was Open" top-10 lists, each row with a one-line story hook.
3. **Team Tendency** — 32 compact panels, horizontal bars sorted most
   over-targeted → most ignored, with one-receiver offenses highlighted.
4. **Where the Ball Goes Instead** — a Sankey flow from ignored receivers to
   where the targets actually go.
5. **Coverage Profile** — a quadrant chart separating man-only, zone-only, and
   wins-both specialists for matchup talk.

## Stack

- **Next.js 15** (App Router) + **React 18** + **TypeScript 5**
- **Tailwind CSS 3** (dark broadcast palette in `tailwind.config.ts`)
- **Recharts 2.x** for the scatter, bar, and quadrant charts
- **@nivo/sankey** (+ `@nivo/core`) for the ball-flow Sankey only

> React 18 + Recharts 2.x is pinned deliberately to avoid the documented
> React 19 / Recharts SVG-not-rendering bug.

### Charting choice: Recharts vs @nivo/sankey

Recharts drives every standard chart (scatter, bars, quadrant) because its
declarative React component model, `ReferenceLine`, and `Tooltip` fit the
"zero-interaction story at a glance" requirement with minimal code. Recharts has
no first-class Sankey, so **@nivo/sankey** handles the single flow diagram in
"Where the Ball Goes Instead." Keeping both libraries scoped this way avoids
pulling in a second full charting toolkit for the other sections.

## Running

From the repo root (`c:\Users\yousu\OneDrive\Documents\GitHub\visualisation`):

```bash
npm install        # install dependencies
npm run dev        # start the dev server at http://localhost:3000
npm run build      # production build (the primary verification gate)
npm run start      # serve the production build
npm run lint       # eslint
```

Data integrity / fallback helpers:

```bash
npm run generate-data   # write synthetic fallback -> public/data/receivers.sample.json
node scripts/check-data.mjs    # validate public/data/receivers.json shape + consistency
node scripts/check-logic.mjs   # sanity-check TOE/story helpers
```

> On OneDrive, running `npm run build` twice back-to-back can throw a spurious
> `readlink EINVAL` on `.next`. Delete `.next` and rebuild — it is not a code
> error.

## Data

The dashboard loads a single file at runtime via
`fetch('/data/receivers.json')` inside `DashboardProvider`. The file is
validated against the `ReceiversFile` shape (see `src/lib/types.ts`), and every
section reads the same filtered dataset through `useDashboard()`.

### File shape (`public/data/receivers.json`)

```jsonc
{
  "schemaVersion": "1.0.0-real",
  "generatedAt": "2024-01-01T00:00:00.000Z",
  "expectationModel": {
    "formula": "clamp(a + b*openRate, 0, 1)",
    "a": 0.085037,
    "b": 0.067407
  },
  "receivers": [ /* ReceiverWeekRow[] */ ]
}
```

| Field              | Type   | Description                                                      |
| ------------------ | ------ | ---------------------------------------------------------------- |
| `schemaVersion`    | string | Dataset schema version tag (e.g. `"1.0.0-real"`).                |
| `generatedAt`      | string | ISO timestamp when the file was produced.                        |
| `expectationModel` | object | Linear coefficients for the scatter's reference line (see below).|
| `receivers`        | array  | One `ReceiverWeekRow` per player per week.                       |

#### `expectationModel`

| Field     | Type   | Description                                                             |
| --------- | ------ | ----------------------------------------------------------------------- |
| `formula` | string | Human-readable formula, `clamp(a + b*openRate, 0, 1)`.                   |
| `a`       | number | Intercept of the linear expectation line.                               |
| `b`       | number | Slope on `openRate` of the linear expectation line.                     |

#### `ReceiverWeekRow` columns

| Column               | Type              | Description                                                            |
| -------------------- | ----------------- | ---------------------------------------------------------------------- |
| `playerId`           | string            | Stable unique player identifier.                                       |
| `playerName`         | string            | Display name (bold on-air label).                                      |
| `team`               | string            | Team abbreviation, e.g. `"KC"`.                                        |
| `position`           | `WR` \| `TE` \| `RB` | Receiver position.                                                  |
| `week`               | number            | 1-based week number.                                                   |
| `opponent`           | string            | Opponent team abbreviation.                                            |
| `gameId`             | string            | Game key, stable per game (not week-prefixed in the real data).        |
| `openRate`           | number (0-1)      | Overall open rate.                                                     |
| `targetShare`        | number (0-1)      | Share of the team's targets this week.                                 |
| `expectedTargetShare`| number (0-1)      | Model expectation for target share (stored per row — read it, don't recompute). |
| `toe`                | number            | Target Over Expectation = `targetShare - expectedTargetShare` (stored per row). |
| `openRateVsMan`      | number (0-1)      | Open rate against man coverage.                                        |
| `openRateVsZone`     | number (0-1)      | Open rate against zone coverage.                                       |
| `targetShareVsMan`   | number (0-1)      | Target share against man coverage.                                     |
| `targetShareVsZone`  | number (0-1)      | Target share against zone coverage.                                    |
| `routesRun`          | number            | Routes run in the week.                                                |
| `targets`            | number            | Targets in the week (`receptions <= targets <= routesRun`).            |
| `receptions`         | number            | Receptions in the week.                                                |
| `yards`              | number            | Receiving yards in the week.                                           |

### Expectation formula & where `a` / `b` live

```
expectedTargetShare = clamp(a + b * openRate, 0, 1)
toe                 = targetShare - expectedTargetShare
```

- Each row's `expectedTargetShare` and `toe` are **stored on the row** and read
  as-is throughout the UI. The committed real dataset uses a route-participation
  baseline (`routesRun / teamRoutes(week)`) for the per-row `expectedTargetShare`.
- The linear coefficients `a` and `b` live in two mirrored places:
  - `expectationModel.a` / `expectationModel.b` in
    `public/data/receivers.json`.
  - `defaultModel` in `src/lib/toe.ts` (fallback / mirror).
- `a` and `b` are used **only** to draw the Headline Chart's diagonal
  expectation reference line (`expectedTargetShareLine(openRate)` in
  `src/lib/toe.ts`). They do **not** recompute per-row TOE.

### Swapping in real data (zero code changes)

1. Replace `public/data/receivers.json` with your feed using the **same wrapper
   shape and the exact same column names** documented above (same
   `schemaVersion` / `generatedAt` / `expectationModel` / `receivers[]`).
2. If your expectation model's coefficients differ, update
   `expectationModel.a` and `expectationModel.b` in the JSON — and keep the
   mirror `defaultModel` in `src/lib/toe.ts` in sync (it only affects the
   scatter's reference line).

No component, type, or logic changes are required: the provider fetches and
validates the file at runtime, and every section renders off it. A synthetic
fallback (`public/data/receivers.sample.json`) can be regenerated with
`npm run generate-data` and never overwrites `receivers.json`.

## Project structure

```
app/                 App Router entry (layout, page, globals.css, DashboardShell)
src/lib/             types.ts, toe.ts, stories.ts, filters.ts
src/context/         DashboardProvider.tsx (data load + filter/story state)
src/hooks/           useDashboard.ts
src/components/       FilterBar + the 5 sections + StoryMode
scripts/             data generator + check-data / check-logic
public/data/         receivers.json (swappable dataset)
```
