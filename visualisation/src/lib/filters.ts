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
 * Apply the current filter state to the raw rows.
 *
 * Note: coverage ("man"/"zone") does not drop rows — it selects which coverage
 * split the UI reads. Filtering by week/position/game narrows the row set.
 * Coverage is kept in state here so a single source governs all sections.
 */
export function applyFilters(
  rows: ReceiverWeekRow[],
  filters: FilterState
): ReceiverWeekRow[] {
  return rows.filter((r) => {
    if (filters.week !== "all" && r.week !== filters.week) return false;
    if (filters.position !== "all" && r.position !== filters.position) return false;
    if (filters.gameId !== "all" && r.gameId !== filters.gameId) return false;
    return true;
  });
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
