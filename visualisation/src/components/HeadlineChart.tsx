"use client";

// Headline hero visual: a Recharts scatter of Open Rate (x) vs Target Share
// (y) for the filtered receivers, with a thick diagonal "expectation"
// reference line. Only the true extremes — the top 3-4 over-targeted and the
// top 3-4 ignored by TOE — get large bold name labels, so the story reads at
// a glance with zero interaction. Hovering any point shows full context.
//
// A local Man/Zone/Overall toggle swaps the point coordinates to the matching
// coverage split (openRateVs* / targetShareVs*). It defaults to whatever the
// global coverage filter is set to, but can be changed on the chart itself.

import { useEffect, useMemo, useState } from "react";
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
import { expectedTargetShareLine } from "@/lib/toe";
import type { CoverageFilter, ReceiverWeekRow } from "@/lib/types";

type CoverageView = CoverageFilter; // "all" | "man" | "zone"

/** One plotted point: a player reduced to a single representative row. */
interface Point {
  playerId: string;
  playerName: string;
  team: string;
  position: string;
  x: number; // open rate (for the active view)
  y: number; // target share (for the active view)
  toe: number;
  routesRun: number;
  targets: number;
  receptions: number;
  label: string | null; // non-null only for the extremes
}

const VIEW_OPTIONS: { value: CoverageView; label: string }[] = [
  { value: "all", label: "Overall" },
  { value: "man", label: "Man" },
  { value: "zone", label: "Zone" },
];

/** Open rate / target share for a row under the chosen coverage view. */
function coords(row: ReceiverWeekRow, view: CoverageView): { x: number; y: number } {
  if (view === "man") {
    return { x: row.openRateVsMan, y: row.targetShareVsMan };
  }
  if (view === "zone") {
    return { x: row.openRateVsZone, y: row.targetShareVsZone };
  }
  return { x: row.openRate, y: row.targetShare };
}

/**
 * Reduce the filtered rows to one representative point per player (the week
 * with the largest |TOE|), so a player appears once even across weeks.
 */
function reduceToPoints(rows: ReceiverWeekRow[], view: CoverageView): Point[] {
  const repByPlayer = new Map<string, ReceiverWeekRow>();
  for (const r of rows) {
    const cur = repByPlayer.get(r.playerId);
    if (!cur || Math.abs(r.toe) > Math.abs(cur.toe)) repByPlayer.set(r.playerId, r);
  }
  return [...repByPlayer.values()].map((r) => {
    const { x, y } = coords(r, view);
    return {
      playerId: r.playerId,
      playerName: r.playerName,
      team: r.team,
      position: r.position,
      x,
      y,
      toe: r.toe,
      routesRun: r.routesRun,
      targets: r.targets,
      receptions: r.receptions,
      label: null,
    };
  });
}

/** Last name only, for compact on-chart labels. */
function shortName(name: string): string {
  const parts = name.trim().split(/\s+/);
  return parts.length > 1 ? parts[parts.length - 1] : name;
}

interface TooltipPayloadItem {
  payload: Point;
}

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: TooltipPayloadItem[];
}) {
  if (!active || !payload || payload.length === 0) return null;
  const p = payload[0].payload;
  const signed = `${p.toe >= 0 ? "+" : ""}${Math.round(p.toe * 100)}%`;
  return (
    <div className="rounded-lg border border-edge bg-ink/95 px-3 py-2 text-sm shadow-xl">
      <p className="text-base font-black text-slate-50">
        {p.playerName}{" "}
        <span className="text-slate-400">
          {p.team} · {p.position}
        </span>
      </p>
      <p className={p.toe >= 0 ? "font-bold text-pos" : "font-bold text-neg"}>
        TOE {signed}
      </p>
      <p className="text-slate-300">
        Open {Math.round(p.x * 100)}% · Target share {Math.round(p.y * 100)}%
      </p>
      <p className="text-slate-400">
        {p.routesRun} routes · {p.targets} targets · {p.receptions} rec
      </p>
    </div>
  );
}

/** Large bold label rendered only on the extreme points. */
function ExtremeLabel(props: {
  x?: number;
  y?: number;
  payload?: Point;
}) {
  const { x, y, payload } = props;
  if (x == null || y == null || !payload || !payload.label) return null;
  const over = payload.toe >= 0;
  return (
    <text
      x={x}
      y={y - 12}
      textAnchor="middle"
      className="pointer-events-none"
      fill={over ? "#22d3ee" : "#fb7185"}
      fontSize={16}
      fontWeight={800}
    >
      {payload.label}
    </text>
  );
}

const EXTREME_COUNT = 4;

export function HeadlineChart() {
  const { filtered, filters, model, loading, error } = useDashboard();

  // Local view defaults to the global coverage filter, and follows it when it
  // changes, but can be overridden on the chart.
  const [view, setView] = useState<CoverageView>(filters.coverage);
  useEffect(() => {
    setView(filters.coverage);
  }, [filters.coverage]);

  const points = useMemo(() => reduceToPoints(filtered, view), [filtered, view]);

  // Flag the extremes: top N over-targeted (highest +TOE) and top N ignored
  // (lowest -TOE). Only these get large bold labels.
  const labelled = useMemo(() => {
    const byToeDesc = [...points].sort((a, b) => b.toe - a.toe);
    const over = byToeDesc.filter((p) => p.toe > 0).slice(0, EXTREME_COUNT);
    const ignored = byToeDesc
      .filter((p) => p.toe < 0)
      .slice(-EXTREME_COUNT);
    const extremeIds = new Set([
      ...over.map((p) => p.playerId),
      ...ignored.map((p) => p.playerId),
    ]);
    return points.map((p) =>
      extremeIds.has(p.playerId) ? { ...p, label: shortName(p.playerName) } : p
    );
  }, [points]);

  // Split into over-targeted (above expectation) and ignored (below) for color.
  const overPoints = useMemo(() => labelled.filter((p) => p.toe >= 0), [labelled]);
  const ignoredPoints = useMemo(() => labelled.filter((p) => p.toe < 0), [labelled]);

  // Diagonal expectation line endpoints across the open-rate domain.
  const lineData = useMemo(() => {
    const m = model ?? undefined;
    return [
      { x: 0, y: expectedTargetShareLine(0, m) },
      { x: 1, y: expectedTargetShareLine(1, m) },
    ];
  }, [model]);

  return (
    <section className="rounded-xl border border-edge bg-panel p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-black tracking-tight text-slate-50">
            Open Rate vs Target Share
          </h2>
          <p className="text-sm text-slate-400">
            Above the line = force-fed. Below = open but ignored.
          </p>
        </div>
        <div className="flex gap-1 rounded-lg border border-edge bg-ink p-1">
          {VIEW_OPTIONS.map((opt) => {
            const active = opt.value === view;
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => setView(opt.value)}
                aria-pressed={active}
                className={[
                  "rounded-md px-3 py-1.5 text-sm font-bold transition-colors",
                  active
                    ? "bg-accent text-ink"
                    : "text-slate-300 hover:bg-edge hover:text-slate-50",
                ].join(" ")}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      </div>

      {loading && (
        <p className="py-24 text-center text-xl font-bold text-slate-300">
          Loading chart…
        </p>
      )}
      {error && (
        <p className="py-24 text-center text-xl font-bold text-neg">
          {error}
        </p>
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
                name="Open Rate"
                domain={[0, 1]}
                tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                stroke="#64748b"
                tick={{ fill: "#94a3b8", fontSize: 13, fontWeight: 600 }}
              >
                <Label
                  value="Open Rate"
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
                name="Target Share"
                domain={[0, "auto"]}
                tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                stroke="#64748b"
                tick={{ fill: "#94a3b8", fontSize: 13, fontWeight: 600 }}
              >
                <Label
                  value="Target Share"
                  angle={-90}
                  position="left"
                  offset={0}
                  fill="#cbd5e1"
                  fontSize={14}
                  fontWeight={700}
                />
              </YAxis>
              <ZAxis range={[90, 90]} />
              <Tooltip
                content={<ChartTooltip />}
                cursor={{ strokeDasharray: "3 3", stroke: "#334155" }}
              />

              {/* Thick diagonal expectation line. */}
              <ReferenceLine
                ifOverflow="extendDomain"
                segment={lineData}
                stroke="#facc15"
                strokeWidth={3}
                strokeDasharray="6 4"
              />

              <Scatter
                name="Over-targeted"
                data={overPoints}
                fill="#22d3ee"
                fillOpacity={0.85}
                label={<ExtremeLabel />}
              />
              <Scatter
                name="Ignored"
                data={ignoredPoints}
                fill="#fb7185"
                fillOpacity={0.85}
                label={<ExtremeLabel />}
              />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
