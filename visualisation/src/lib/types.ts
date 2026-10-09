// Shared data model for the NFL TOE dashboard.
//
// These types mirror public/data/receivers.json EXACTLY (same field names,
// same 0-1 / number conventions). Real weekly data can be dropped into
// receivers.json with the identical shape and zero code changes.

/** Receiver position. */
export type Position = "WR" | "TE" | "RB";

/** Coverage filter selection in the UI. */
export type CoverageFilter = "all" | "man" | "zone";

/** Position filter selection in the UI (any position or all). */
export type PositionFilter = Position | "all";

/**
 * The linear expectation model used to compute expectedTargetShare.
 * expectedTargetShare = clamp(a + b * openRate, 0, 1)
 */
export interface ExpectationModel {
  /** Human-readable formula, e.g. "clamp(a + b*openRate, 0, 1)". */
  formula: string;
  /** Intercept. */
  a: number;
  /** Slope on openRate. */
  b: number;
}

/**
 * One row = one player's performance in one week.
 * All *Rate / *Share fields are fractions in [0, 1].
 */
export interface ReceiverWeekRow {
  playerId: string;
  playerName: string;
  /** Team abbreviation, e.g. "KC". */
  team: string;
  position: Position;
  /** 1-based week number. */
  week: number;
  /** Opponent team abbreviation. */
  opponent: string;
  gameId: string;

  /** Overall open rate, 0-1. */
  openRate: number;
  /** Share of the team's targets this week, 0-1. */
  targetShare: number;
  /** Model expectation for target share, 0-1. */
  expectedTargetShare: number;
  /** Target Over Expectation = targetShare - expectedTargetShare. */
  toe: number;

  /** Open rate when facing man coverage, 0-1. */
  openRateVsMan: number;
  /** Open rate when facing zone coverage, 0-1. */
  openRateVsZone: number;
  /** Target share when facing man coverage, 0-1. */
  targetShareVsMan: number;
  /** Target share when facing zone coverage, 0-1. */
  targetShareVsZone: number;

  routesRun: number;
  targets: number;
  receptions: number;
  yards: number;
}

/** The full on-disk / fetched data file shape. */
export interface ReceiversFile {
  schemaVersion: string;
  generatedAt: string;
  expectationModel: ExpectationModel;
  receivers: ReceiverWeekRow[];
}
