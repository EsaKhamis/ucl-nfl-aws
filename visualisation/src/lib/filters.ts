// Pure filtering of receiver rows for the dashboard's live broadcast controls.

import type {
  CoverageFilter,
  PositionFilter,
  ReceiverWeekRow,
} from "./types";

export interface FilterState {
  /** Week number, or "all" for the full sample. */
  week: number | "all";
  position: PositionFilter;
  coverage: CoverageFilter;
  /** Specific gameId quick filter, or "all". */
  gameId: string | "all";
}

export const defaultFilters: FilterState = {
  week: "all",
  position: "all",
  coverage: "all",
  gameId: "all",
};

/**
 * Route minimum for a player to appear after aggregation: `season` when every
 * week is selected (spec Route_Minimum), otherwise `perWeek` x selected weeks.
 */
export const ROUTE_MINIMUM = { season: 100, perWeek: 15 };

/**
 * Collapse week rows to one row per player (same ReceiverWeekRow shape).
 * Counts are summed; rates are routes-weighted means, so targetShare and
 * expectedTargetShare are targets / routes and expected targets / routes.
 * Man/Zone rates are weighted by total routes (per-coverage route counts are
 * not in the file), an approximation. team/opponent/gameId/name/position come
 * from the player's week with the most routes; week is the first week.
 */
export function aggregatePlayers(rows: ReceiverWeekRow[]): ReceiverWeekRow[] {
  const byPlayer = new Map<string, ReceiverWeekRow[]>();
  for (const r of rows) {
    const list = byPlayer.get(r.playerId);
    if (list) list.push(r);
    else byPlayer.set(r.playerId, [r]);
  }
  const out: ReceiverWeekRow[] = [];
  for (const weeks of byPlayer.values()) {
    let main = weeks[0];
    let firstWeek = weeks[0].week;
    let routes = 0, targets = 0, receptions = 0, yards = 0;
    let xTargets = 0, open = 0, openMan = 0, openZone = 0, tsMan = 0, tsZone = 0;
    for (const r of weeks) {
      if (r.routesRun > main.routesRun) main = r;
      if (r.week < firstWeek) firstWeek = r.week;
      routes += r.routesRun;
      targets += r.targets;
      receptions += r.receptions;
      yards += r.yards;
      xTargets += r.expectedTargetShare * r.routesRun;
      open += r.openRate * r.routesRun;
      openMan += r.openRateVsMan * r.routesRun;
      openZone += r.openRateVsZone * r.routesRun;
      tsMan += r.targetShareVsMan * r.routesRun;
      tsZone += r.targetShareVsZone * r.routesRun;
    }
    const perRoute = (x: number) => (routes > 0 ? x / routes : 0);
    const targetShare = perRoute(targets);
    const expectedTargetShare = perRoute(xTargets);
    out.push({
      ...main,
      week: firstWeek,
      routesRun: routes,
      targets,
      receptions,
      yards,
      openRate: perRoute(open),
      targetShare,
      expectedTargetShare,
      toe: targetShare - expectedTargetShare,
      openRateVsMan: perRoute(openMan),
      openRateVsZone: perRoute(openZone),
      targetShareVsMan: perRoute(tsMan),
      targetShareVsZone: perRoute(tsZone),
    });
  }
  return out;
}

/**
 * Apply the current filter state to the raw rows, then aggregate to one row
 * per player across the selected weeks and apply ROUTE_MINIMUM.
 *
 * Note: coverage ("man"/"zone") does not drop rows — it selects which coverage
 * split the UI reads. Filtering by week/position/game narrows the row set.
 * Coverage is kept in state here so a single source governs all sections.
 */
export function applyFilters(
  rows: ReceiverWeekRow[],
  filters: FilterState
): ReceiverWeekRow[] {
  const selected = rows.filter((r) => {
    if (filters.week !== "all" && r.week !== filters.week) return false;
    if (filters.position !== "all" && r.position !== filters.position) return false;
    if (filters.gameId !== "all" && r.gameId !== filters.gameId) return false;
    return true;
  });
  const totalWeeks = new Set(rows.map((r) => r.week)).size;
  const selectedWeeks = new Set(selected.map((r) => r.week)).size;
  const minRoutes =
    selectedWeeks >= totalWeeks
      ? ROUTE_MINIMUM.season
      : ROUTE_MINIMUM.perWeek * selectedWeeks;
  return aggregatePlayers(selected).filter((r) => r.routesRun >= minRoutes);
}

/** Distinct, sorted weeks present in the data. */
export function availableWeeks(rows: ReceiverWeekRow[]): number[] {
  return [...new Set(rows.map((r) => r.week))].sort((a, b) => a - b);
}

/** Distinct, sorted gameIds present in the data (optionally for a week). */
export function availableGames(
  rows: ReceiverWeekRow[],
  week?: number | "all"
): string[] {
  const scoped =
    week && week !== "all" ? rows.filter((r) => r.week === week) : rows;
  return [...new Set(scoped.map((r) => r.gameId))].sort();
}
