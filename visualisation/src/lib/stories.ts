// Narrative derivation for broadcast "talking points".
//
// deriveStoryHook(row)      -> one-line narrative string for a single row.
// selectTopNarratives(rows) -> the 3-5 most interesting stories for Story Mode.

import type { ReceiverWeekRow } from "./types";
import { coverageSpecialist, teamConcentration } from "./toe";

function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}

/** Narrative category for a top-level story. */
export type NarrativeKind =
  | "over-targeted"
  | "ignored"
  | "one-receiver-offense"
  | "coverage-specialist"
  | "checkdown";

export interface Narrative {
  kind: NarrativeKind;
  /** Short headline for the Story Mode chip. */
  title: string;
  /** One-line talking point. */
  hook: string;
  /** Primary player this story is about (may be empty for team stories). */
  playerName: string;
  team: string;
  /** Magnitude used for ranking (higher = more interesting). */
  score: number;
}

/**
 * A one-line narrative for a single receiver-week row.
 * Examples:
 *   "Only targeted 18% despite 52% open rate vs man"
 *   "Force-fed: 34% target share on a 29% open rate"
 */
export function deriveStoryHook(row: ReceiverWeekRow): string {
  const name = row.playerName;

  // Strongly ignored: open but not fed.
  if (row.toe <= -0.08) {
    const bestCoverage =
      row.openRateVsMan >= row.openRateVsZone
        ? { label: "vs man", rate: row.openRateVsMan }
        : { label: "vs zone", rate: row.openRateVsZone };
    return `${name}: only targeted ${pct(row.targetShare)} despite ${pct(
      bestCoverage.rate
    )} open rate ${bestCoverage.label}`;
  }

  // Strongly over-targeted: fed regardless of separation.
  if (row.toe >= 0.08) {
    return `${name}: force-fed ${pct(row.targetShare)} target share on a ${pct(
      row.openRate
    )} open rate`;
  }

  // Coverage specialist angle.
  const spec = coverageSpecialist(row);
  if (spec === "man-only") {
    return `${name}: gets open vs man (${pct(row.openRateVsMan)}) but disappears vs zone (${pct(
      row.openRateVsZone
    )})`;
  }
  if (spec === "zone-only") {
    return `${name}: beats zone (${pct(row.openRateVsZone)}) but struggles vs man (${pct(
      row.openRateVsMan
    )})`;
  }

  // Neutral baseline.
  return `${name}: ${pct(row.targetShare)} target share, ${pct(row.openRate)} open rate (TOE ${
    row.toe >= 0 ? "+" : ""
  }${pct(row.toe)})`;
}

/**
 * Select the 3-5 most interesting narratives across the given (already
 * filtered) rows for Story Mode. Picks, when available:
 *   - biggest over-targeted player
 *   - biggest ignored player
 *   - a one-receiver offense
 *   - a man/zone coverage specialist
 *   - a checkdown pattern (RB with strong positive TOE / high open rate)
 */
export function selectTopNarratives(rows: ReceiverWeekRow[]): Narrative[] {
  if (rows.length === 0) return [];

  const narratives: Narrative[] = [];

  // Aggregate to one representative row per player (highest |toe| week) so a
  // single player doesn't flood the list across weeks.
  const repByPlayer = new Map<string, ReceiverWeekRow>();
  for (const r of rows) {
    const cur = repByPlayer.get(r.playerId);
    if (!cur || Math.abs(r.toe) > Math.abs(cur.toe)) repByPlayer.set(r.playerId, r);
  }
  const reps = [...repByPlayer.values()];

  // Biggest over-targeted.
  const over = [...reps].sort((a, b) => b.toe - a.toe)[0];
  if (over && over.toe > 0) {
    narratives.push({
      kind: "over-targeted",
      title: "Most over-targeted",
      hook: deriveStoryHook(over),
      playerName: over.playerName,
      team: over.team,
      score: over.toe,
    });
  }

  // Biggest ignored.
  const ignored = [...reps].sort((a, b) => a.toe - b.toe)[0];
  if (ignored && ignored.toe < 0 && ignored.playerId !== over?.playerId) {
    narratives.push({
      kind: "ignored",
      title: "Most ignored",
      hook: deriveStoryHook(ignored),
      playerName: ignored.playerName,
      team: ignored.team,
      score: -ignored.toe,
    });
  }

  // One-receiver offense (across the filtered rows, grouped by team).
  const byTeam = new Map<string, ReceiverWeekRow[]>();
  for (const r of rows) {
    if (!byTeam.has(r.team)) byTeam.set(r.team, []);
    byTeam.get(r.team)!.push(r);
  }
  let bestTeam: { team: string; score: number; topName: string } | null = null;
  for (const [team, teamRows] of byTeam) {
    const { gini, oneReceiverOffense, topShare } = teamConcentration(teamRows);
    if (oneReceiverOffense && (!bestTeam || gini > bestTeam.score)) {
      // Identify the dominant player for the hook.
      const share = new Map<string, { name: string; total: number }>();
      for (const r of teamRows) {
        const e = share.get(r.playerId) ?? { name: r.playerName, total: 0 };
        e.total += r.targetShare;
        share.set(r.playerId, e);
      }
      const top = [...share.values()].sort((a, b) => b.total - a.total)[0];
      bestTeam = { team, score: gini, topName: top?.name ?? "" };
      void topShare;
    }
  }
  if (bestTeam) {
    narratives.push({
      kind: "one-receiver-offense",
      title: "One-receiver offense",
      hook: `${bestTeam.team} is force-feeding ${bestTeam.topName} — the offense runs through one guy`,
      playerName: bestTeam.topName,
      team: bestTeam.team,
      score: bestTeam.score,
    });
  }

  // Coverage specialist (strongest man-only or zone-only separation gap).
  let bestSpec: { row: ReceiverWeekRow; gap: number } | null = null;
  for (const r of reps) {
    const spec = coverageSpecialist(r);
    if (spec === "man-only" || spec === "zone-only") {
      const gap = Math.abs(r.openRateVsMan - r.openRateVsZone);
      if (!bestSpec || gap > bestSpec.gap) bestSpec = { row: r, gap };
    }
  }
  if (bestSpec) {
    narratives.push({
      kind: "coverage-specialist",
      title: "Coverage specialist",
      hook: deriveStoryHook(bestSpec.row),
      playerName: bestSpec.row.playerName,
      team: bestSpec.row.team,
      score: bestSpec.gap,
    });
  }

  // Checkdown pattern: an RB being fed underneath (high open rate, positive TOE).
  const checkdown = reps
    .filter((r) => r.position === "RB")
    .sort((a, b) => b.openRate + b.toe - (a.openRate + a.toe))[0];
  if (checkdown && checkdown.openRate >= 0.5) {
    narratives.push({
      kind: "checkdown",
      title: "Checkdown valve",
      hook: `${checkdown.playerName} (${checkdown.team}) is the checkdown — ${pct(
        checkdown.openRate
      )} open rate, ${pct(checkdown.targetShare)} of the targets`,
      playerName: checkdown.playerName,
      team: checkdown.team,
      score: checkdown.openRate + checkdown.toe,
    });
  }

  // Cap at 5, keep the most interesting by score within kind priority order.
  return narratives.slice(0, 5);
}
