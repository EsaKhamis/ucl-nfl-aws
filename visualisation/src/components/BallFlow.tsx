"use client";

// "Where the Ball Goes Instead" — a Sankey flow (via @nivo/sankey) showing
// where a team's targets actually land when a receiver is being ignored.
//
// To stay readable (not a hairball) the flow is modeled at the position level.
// For every team that has at least one *ignored* receiver (clearly negative
// TOE), we route a weight equal to that team's ignored-target volume into the
// positions actually getting fed on that team (positive-TOE / dominant target
// shares). Sources are labeled "Ignored WR/TE/RB"; destinations are
// "WR/TE/RB targets". The result reads as a handful of bold bands:
// "ignored WRs -> RB checkdowns", "ignored deep threats -> TE", etc.

import { useMemo } from "react";
import { ResponsiveSankey } from "@nivo/sankey";

import { useDashboard } from "@/hooks/useDashboard";
import type { Position, ReceiverWeekRow } from "@/lib/types";

interface SankeyNode {
  id: string;
}

interface SankeyLink {
  source: string;
  target: string;
  value: number;
}

interface SankeyData {
  nodes: SankeyNode[];
  links: SankeyLink[];
}

const POSITIONS: Position[] = ["WR", "TE", "RB"];

/** A receiver is "ignored" when meaningfully below expectation. */
const IGNORED_TOE = -0.03;
/** A receiver is a real "destination" when at/above expectation and fed. */
const FED_TOE = 0.0;

function sourceId(pos: Position): string {
  return `Ignored ${pos}`;
}
function targetId(pos: Position): string {
  return `${pos} targets`;
}

/**
 * Build position-level Sankey nodes/links from the filtered rows.
 *
 * Per team: sum the (expected-but-undelivered) target share of ignored
 * receivers by their position = how much attention is being withheld. Sum the
 * actual target share of fed receivers by position = where the ball goes.
 * Distribute each ignored-position bucket across the team's fed positions in
 * proportion to how much each fed position is being favored. Aggregate across
 * teams into position->position bands.
 */
function buildSankey(rows: ReceiverWeekRow[]): SankeyData {
  // link weight accumulator keyed by "srcPos>dstPos"
  const linkWeight = new Map<string, number>();

  const byTeam = new Map<string, ReceiverWeekRow[]>();
  for (const r of rows) {
    const list = byTeam.get(r.team);
    if (list) list.push(r);
    else byTeam.set(r.team, [r]);
  }

  for (const teamRows of byTeam.values()) {
    // Collapse to one representative row per player (largest |TOE| week) so a
    // player isn't double-counted across weeks.
    const repByPlayer = new Map<string, ReceiverWeekRow>();
    for (const r of teamRows) {
      const cur = repByPlayer.get(r.playerId);
      if (!cur || Math.abs(r.toe) > Math.abs(cur.toe)) {
        repByPlayer.set(r.playerId, r);
      }
    }
    const reps = [...repByPlayer.values()];

    // Withheld attention by ignored source position.
    const ignoredByPos = new Map<Position, number>();
    // Favored actual target share by fed destination position.
    const fedByPos = new Map<Position, number>();

    for (const r of reps) {
      if (r.toe <= IGNORED_TOE) {
        // magnitude of how open-but-ignored they are
        ignoredByPos.set(r.position, (ignoredByPos.get(r.position) ?? 0) + Math.abs(r.toe));
      } else if (r.toe >= FED_TOE) {
        fedByPos.set(r.position, (fedByPos.get(r.position) ?? 0) + Math.max(r.toe, 0.0001) + r.targetShare * 0.25);
      }
    }

    const fedTotal = [...fedByPos.values()].reduce((a, b) => a + b, 0);
    if (fedTotal <= 0 || ignoredByPos.size === 0) continue;

    for (const [srcPos, withheld] of ignoredByPos) {
      for (const [dstPos, fed] of fedByPos) {
        const value = withheld * (fed / fedTotal);
        if (value <= 0) continue;
        const key = `${srcPos}>${dstPos}`;
        linkWeight.set(key, (linkWeight.get(key) ?? 0) + value);
      }
    }
  }

  // Materialize nodes only for positions that actually participate, so the
  // diagram shows no orphan nodes.
  const usedSources = new Set<Position>();
  const usedTargets = new Set<Position>();
  const links: SankeyLink[] = [];

  for (const [key, value] of linkWeight) {
    const [srcPos, dstPos] = key.split(">") as [Position, Position];
    // Round to keep tiny slivers from cluttering the picture.
    const v = Math.round(value * 1000) / 10; // scaled % points, 1dp
    if (v <= 0) continue;
    usedSources.add(srcPos);
    usedTargets.add(dstPos);
    links.push({ source: sourceId(srcPos), target: targetId(dstPos), value: v });
  }

  const nodes: SankeyNode[] = [
    ...POSITIONS.filter((p) => usedSources.has(p)).map((p) => ({ id: sourceId(p) })),
    ...POSITIONS.filter((p) => usedTargets.has(p)).map((p) => ({ id: targetId(p) })),
  ];

  return { nodes, links };
}

/** Broadcast palette by node id. */
function nodeColor(node: { id: string }): string {
  if (node.id.startsWith("Ignored")) return "#fb7185"; // ignored = rose
  return "#22d3ee"; // destination = cyan
}

export function BallFlow() {
  const { filtered, loading, error } = useDashboard();

  const data = useMemo(() => buildSankey(filtered), [filtered]);
  const hasFlow = data.nodes.length > 0 && data.links.length > 0;

  return (
    <section className="rounded-xl border border-slate-700 bg-panel p-6">
      <div className="mb-4">
        <h2 className="text-2xl font-black tracking-tight text-slate-50">
          Where the Ball Goes Instead
        </h2>
        <p className="text-base font-semibold text-slate-200">
          When these receivers are ignored (rose), the targets flow to who&apos;s
          actually fed (cyan).
        </p>
      </div>

      {loading && (
        <p className="py-24 text-center text-xl font-bold text-slate-300">
          Loading flow…
        </p>
      )}
      {error && (
        <p className="py-24 text-center text-xl font-bold text-neg">{error}</p>
      )}

      {!loading && !error && !hasFlow && (
        <p className="py-24 text-center text-xl font-bold text-slate-200">
          No ignored-receiver flow for the current filters.
        </p>
      )}

      {!loading && !error && hasFlow && (
        <div className="h-[480px] w-full">
          <ResponsiveSankey
            data={data}
            margin={{ top: 16, right: 160, bottom: 16, left: 160 }}
            align="justify"
            colors={nodeColor}
            nodeOpacity={1}
            nodeThickness={22}
            nodeInnerPadding={3}
            nodeSpacing={28}
            nodeBorderWidth={0}
            nodeBorderRadius={3}
            // nivo defaults to "multiply", which darkens bands to near-black on
            // the dark panel. "normal" keeps the rose/cyan bands bright.
            linkBlendMode="normal"
            linkOpacity={0.7}
            linkHoverOpacity={0.95}
            linkContract={2}
            enableLinkGradient
            labelPosition="outside"
            labelOrientation="horizontal"
            labelPadding={12}
            labelTextColor="#f8fafc"
            theme={{
              text: { fontSize: 14, fill: "#f8fafc" },
              labels: { text: { fontWeight: 800, fontSize: 15 } },
              tooltip: {
                container: {
                  background: "#05070d",
                  color: "#f8fafc",
                  border: "1px solid #475569",
                  fontSize: 13,
                },
              },
            }}
          />
        </div>
      )}
    </section>
  );
}
