// Centralized Target Over Expectation (TOE) logic.
//
// toe = targetShare - expectedTargetShare
//
// IMPORTANT: per-row expectedTargetShare and toe are READ FROM THE DATA. The
// committed receivers.json is real data where expectedTargetShare is a
// route-participation baseline (routesRun / teamRoutes), NOT a + b*openRate.
// Do not recompute per-row expectation from the a/b model.
//
// The a/b linear model (defaultModel) is ONLY for:
//   - drawing the diagonal "expectation" reference line on the headline
//     scatter (expected target share as a function of open rate), and
//   - a fallback when a data file omits expectationModel.
// defaultModel mirrors receivers.json.expectationModel so the reference line
// matches the data's fitted coefficients. If the JSON's a/b change, update
// them here too (or pass the file's expectationModel explicitly).

import type { ExpectationModel, ReceiverWeekRow } from "./types";

/**
 * Default model, mirrors receivers.json.expectationModel (fitted on the real
 * dataset). Used for the scatter's reference line and as a fallback only.
 */
export const defaultModel: ExpectationModel = {
  formula: "clamp(a + b*openRate, 0, 1) (fit over tracking expectedTargetShare)",
  a: 0.205064,
  b: 0.051424,
};

function clamp01(x: number): number {
  return Math.max(0, Math.min(1, x));
}

/**
 * Reference-line value: expected target share as a linear function of open
 * rate under the fitted model. Use ONLY for the scatter's diagonal line or as
 * a fallback. Per-row expectation lives on each row (row.expectedTargetShare).
 */
export function expectedTargetShareLine(
  openRate: number,
  model: ExpectationModel = defaultModel
): number {
  return clamp01(model.a + model.b * openRate);
}

/** Target Over Expectation for a row (reads the row's stored expectation). */
export function toe(row: ReceiverWeekRow): number {
  return row.targetShare - row.expectedTargetShare;
}

/**
 * Team concentration of target share.
 *
 * Returns a Gini-like spread score in [0, 1] where 0 = perfectly even
 * distribution ("spread-the-ball") and 1 = one player gets everything
 * ("one-receiver offense"), plus a boolean flag for the extreme case.
 *
 * `rows` should be the rows for a single team (optionally a single week); if
 * multiple weeks are passed, shares are aggregated by player first.
 */
export function teamConcentration(rows: ReceiverWeekRow[]): {
  gini: number;
  oneReceiverOffense: boolean;
  topShare: number;
} {
  if (rows.length === 0) {
    return { gini: 0, oneReceiverOffense: false, topShare: 0 };
  }

  // Aggregate target share by player (sum across any weeks provided).
  const byPlayer = new Map<string, number>();
  for (const r of rows) {
    byPlayer.set(r.playerId, (byPlayer.get(r.playerId) ?? 0) + r.targetShare);
  }
  const shares = [...byPlayer.values()];
  const total = shares.reduce((a, b) => a + b, 0);

  if (total <= 0 || shares.length === 1) {
    return {
      gini: shares.length <= 1 ? 1 : 0,
      oneReceiverOffense: shares.length === 1,
      topShare: shares.length ? Math.max(...shares) / Math.max(total, 1e-9) : 0,
    };
  }

  const normalized = shares.map((s) => s / total).sort((a, b) => a - b);
  const n = normalized.length;

  // Gini coefficient.
  let cumWeighted = 0;
  for (let i = 0; i < n; i++) {
    cumWeighted += (i + 1) * normalized[i];
  }
  const gini = (2 * cumWeighted) / (n * 1) - (n + 1) / n;

  const topShare = normalized[n - 1];
  // "One-receiver offense": one player commands a dominant share and the
  // distribution is highly concentrated.
  const oneReceiverOffense = topShare >= 0.45 || gini >= 0.5;

  return {
    gini: Math.max(0, Math.min(1, gini)),
    oneReceiverOffense,
    topShare,
  };
}

export type CoverageSpecialist = "man-only" | "zone-only" | "wins-both" | "neither";

/**
 * Classify a receiver's separation profile by coverage.
 *
 * Uses openRateVsMan / openRateVsZone against a "gets open" threshold.
 *   - wins-both : open vs both man and zone
 *   - man-only  : open vs man, not vs zone
 *   - zone-only : open vs zone, not vs man
 *   - neither   : struggles against both
 */
export function coverageSpecialist(
  row: ReceiverWeekRow,
  threshold = 0.5
): CoverageSpecialist {
  const man = row.openRateVsMan >= threshold;
  const zone = row.openRateVsZone >= threshold;
  if (man && zone) return "wins-both";
  if (man) return "man-only";
  if (zone) return "zone-only";
  return "neither";
}
