"use client";

// Coverage Profile: a quadrant scatter of open rate vs man (x) and open rate
// vs zone (y). coverageSpecialist() buckets each receiver so matchup
// specialists stand out:
//   - wins-both : open vs man AND zone (top-right)  -> accent/yellow
//   - man-only  : open vs man, not zone (bottom-right) -> cyan
//   - zone-only : open vs zone, not man (top-left)    -> rose
//   - neither   : struggles vs both (bottom-left)     -> muted
// Reference lines sit at the sample medians so the quadrants adapt to the
// filtered pool, and the standout specialists (the extreme man-only /
// zone-only / wins-both) are labeled with bold names for instant matchup talk.

import { useMemo } from "react";
import {
  CartesianGrid,
  Label,
  ReferenceLine,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
  ResponsiveContainer,
} from "recharts";

import { useDashboard } from "@/hooks/useDashboard";
import { coverageSpecialist, type CoverageSpecialist } from "@/lib/toe";
import type { ReceiverWeekRow } from "@/lib/types";

interface Point {
  playerId: string;
  playerName: string;
  team: string;
  position: string;
  x: number; // openRateVsMan
  y: number; // openRateVsZone
  kind: CoverageSpecialist;
  label: string | null;
}

const KIND_COLOR: Record<CoverageSpecialist, string> = {
  "wins-both": "#facc15",
  "man-only": "#22d3ee",
  "zone-only": "#fb7185",
  neither: "#475569",
};

const KIND_LABEL: Record<CoverageSpecialist, string> = {
  "wins-both": "Wins both",
  "man-only": "Man-only",
  "zone-only": "Zone-only",
  neither: "Neither",
};

/** Last name only, for compact labels. */
function shortName(name: string): string {
  const parts = name.trim().split(/\s+/);
  return parts.length > 1 ? parts[parts.length - 1] : name;
}

function median(values: number[]): number {
  if (values.length === 0) return 0.5;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];
}

/** One representative row per player (largest total separation). */
function reduceToPoints(rows: ReceiverWeekRow[]): Point[] {
  const repByPlayer = new Map<string, ReceiverWeekRow>();
  for (const r of rows) {
    const cur = repByPlayer.get(r.playerId);
    const score = r.openRateVsMan + r.openRateVsZone;
    const curScore = cur ? cur.openRateVsMan + cur.openRateVsZone : -1;
    if (!cur || score > curScore) repByPlayer.set(r.playerId, r);
  }
  return [...repByPlayer.values()].map((r) => ({
    playerId: r.playerId,
    playerName: r.playerName,
    team: r.team,
    position: r.position,
    x: r.openRateVsMan,
    y: r.openRateVsZone,
    kind: coverageSpecialist(r),
    label: null,
  }));
}

interface TooltipItem {
  payload: Point;
}

function ProfileTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: TooltipItem[];
}) {
  if (!active || !payload || payload.length === 0) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-lg border border-edge bg-ink/95 px-3 py-2 text-sm shadow-xl">
      <p className="text-base font-black text-slate-50">
        {p.playerName}{" "}
        <span className="text-slate-400">
          {p.team} · {p.position}
        </span>
      </p>
      <p className="font-bold" style={{ color: KIND_COLOR[p.kind] }}>
        {KIND_LABEL[p.kind]}
      </p>
      <p className="text-slate-300">
        Open vs man {Math.round(p.x * 100)}% · vs zone {Math.round(p.y * 100)}%
      </p>
    </div>
  );
}

/** Bold name label, rendered only on flagged specialists. */
function SpecialistLabel(props: { x?: number; y?: number; payload?: Point }) {
  const { x, y, payload } = props;
  if (x == null || y == null || !payload || !payload.label) return null;
  return (
    <text
      x={x}
      y={y - 10}
      textAnchor="middle"
      className="pointer-events-none"
      fill={KIND_COLOR[payload.kind]}
      fontSize={14}
      fontWeight={800}
    >
      {payload.label}
    </text>
  );
}

/** How many of each specialist type to label (the clearest standouts). */
const LABEL_PER_KIND = 3;

export function CoverageProfile() {
  const { filtered, loading, error } = useDashboard();

  const { points, medMan, medZone } = useMemo(() => {
    const pts = reduceToPoints(filtered);
    const mMan = median(pts.map((p) => p.x));
    const mZone = median(pts.map((p) => p.y));

    // Label the most extreme standouts per specialist kind:
    //   wins-both  -> highest combined separation
    //   man-only   -> biggest man-over-zone gap
    //   zone-only  -> biggest zone-over-man gap
    const toLabel = new Set<string>();
    const winsBoth = pts
      .filter((p) => p.kind === "wins-both")
      .sort((a, b) => b.x + b.y - (a.x + a.y))
      .slice(0, LABEL_PER_KIND);
    const manOnly = pts
      .filter((p) => p.kind === "man-only")
      .sort((a, b) => b.x - b.y - (a.x - a.y))
      .slice(0, LABEL_PER_KIND);
    const zoneOnly = pts
      .filter((p) => p.kind === "zone-only")
      .sort((a, b) => b.y - b.x - (a.y - a.x))
      .slice(0, LABEL_PER_KIND);
    for (const p of [...winsBoth, ...manOnly, ...zoneOnly]) toLabel.add(p.playerId);

    const labeled = pts.map((p) =>
      toLabel.has(p.playerId) ? { ...p, label: shortName(p.playerName) } : p
    );
    return { points: labeled, medMan: mMan, medZone: mZone };
  }, [filtered]);

  // Split by kind for colored series + per-kind labeling.
  const byKind = useMemo(() => {
    const groups: Record<CoverageSpecialist, Point[]> = {
      "wins-both": [],
      "man-only": [],
      "zone-only": [],
      neither: [],
    };
    for (const p of points) groups[p.kind].push(p);
    return groups;
  }, [points]);

  return (
    <section className="rounded-xl border border-edge bg-panel p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-black tracking-tight text-slate-50">
            Coverage Profile
          </h2>
          <p className="text-sm text-slate-400">
            Who gets open vs man, vs zone, or both. Specialists are labeled for
            matchup talk.
          </p>
        </div>
        <div className="flex flex-wrap gap-3 text-xs font-bold">
          {(["wins-both", "man-only", "zone-only", "neither"] as CoverageSpecialist[]).map(
            (k) => (
              <span key={k} className="flex items-center gap-1.5 text-slate-300">
                <span
                  className="inline-block h-3 w-3 rounded-full"
                  style={{ backgroundColor: KIND_COLOR[k] }}
                />
                {KIND_LABEL[k]}
              </span>
            )
          )}
        </div>
      </div>

      {loading && (
        <p className="py-24 text-center text-xl font-bold text-slate-300">
          Loading coverage profile…
        </p>
      )}
      {error && (
        <p className="py-24 text-center text-xl font-bold text-neg">{error}</p>
      )}

      {!loading && !error && points.length === 0 && (
        <p className="py-24 text-center text-xl font-bold text-slate-400">
          No receivers match the current filters.
        </p>
      )}

      {!loading && !error && points.length > 0 && (
        <div className="h-[560px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 24, right: 32, bottom: 48, left: 24 }}>
              <CartesianGrid stroke="#1e2636" strokeDasharray="3 3" />
              <XAxis
                type="number"
                dataKey="x"
                name="Open vs Man"
                domain={[0, 1]}
                tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                stroke="#64748b"
                tick={{ fill: "#94a3b8", fontSize: 13, fontWeight: 600 }}
              >
                <Label
                  value="Open Rate vs Man"
                  position="bottom"
                  offset={16}
                  fill="#cbd5e1"
                  fontSize={14}
                  fontWeight={700}
                />
              </XAxis>
              <YAxis
                type="number"
                dataKey="y"
                name="Open vs Zone"
                domain={[0, 1]}
                tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                stroke="#64748b"
                tick={{ fill: "#94a3b8", fontSize: 13, fontWeight: 600 }}
              >
                <Label
                  value="Open Rate vs Zone"
                  angle={-90}
                  position="left"
                  offset={0}
                  fill="#cbd5e1"
                  fontSize={14}
                  fontWeight={700}
                />
              </YAxis>
              <ZAxis range={[80, 80]} />
              <Tooltip
                content={<ProfileTooltip />}
                cursor={{ strokeDasharray: "3 3", stroke: "#334155" }}
              />

              {/* Median quadrant dividers. */}
              <ReferenceLine
                x={medMan}
                stroke="#facc15"
                strokeWidth={2}
                strokeDasharray="6 4"
              />
              <ReferenceLine
                y={medZone}
                stroke="#facc15"
                strokeWidth={2}
                strokeDasharray="6 4"
              />

              <Scatter
                name="Wins both"
                data={byKind["wins-both"]}
                fill={KIND_COLOR["wins-both"]}
                fillOpacity={0.9}
                label={<SpecialistLabel />}
              />
              <Scatter
                name="Man-only"
                data={byKind["man-only"]}
                fill={KIND_COLOR["man-only"]}
                fillOpacity={0.9}
                label={<SpecialistLabel />}
              />
              <Scatter
                name="Zone-only"
                data={byKind["zone-only"]}
                fill={KIND_COLOR["zone-only"]}
                fillOpacity={0.9}
                label={<SpecialistLabel />}
              />
              <Scatter
                name="Neither"
                data={byKind.neither}
                fill={KIND_COLOR.neither}
                fillOpacity={0.55}
              />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
