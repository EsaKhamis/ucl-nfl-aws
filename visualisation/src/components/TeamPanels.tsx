"use client";

// Team Tendency View: one compact panel per offense (all 32 teams). Each panel
// is a Recharts horizontal bar chart of that team's receivers, aggregated
// across the filtered weeks, sorted most-over-targeted -> most-ignored by TOE.
//
// teamConcentration() flags the extreme shapes: a highly concentrated offense
// ("one-receiver offense") gets a bright accent border + label, while an
// unusually even one ("spread-the-ball") gets a subtle highlight. A
// commentator can scan the grid and instantly call out who force-feeds and who
// shares.

import { useMemo } from "react";
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useDashboard } from "@/hooks/useDashboard";
import { teamConcentration } from "@/lib/toe";
import type { ReceiverWeekRow } from "@/lib/types";

/** All 32 team abbreviations (fixed order so the grid is stable). */
const ALL_TEAMS = [
  "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
  "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
  "LV", "LAC", "LAR", "MIA", "MIN", "NE", "NO", "NYG",
  "NYJ", "PHI", "PIT", "SF", "SEA", "TB", "TEN", "WAS",
];

/** One aggregated bar: a player's mean TOE across the filtered weeks. */
interface PlayerBar {
  playerId: string;
  name: string; // last name, compact
  toe: number;
}

interface TeamSummary {
  team: string;
  bars: PlayerBar[];
  gini: number;
  topShare: number;
  oneReceiverOffense: boolean;
  /** Low concentration = ball spread around. */
  spreadTheBall: boolean;
}

/** Last name only, for compact bar labels. */
function shortName(name: string): string {
  const parts = name.trim().split(/\s+/);
  return parts.length > 1 ? parts[parts.length - 1] : name;
}

/**
 * Build per-team summaries from the filtered rows. Players are aggregated by
 * mean TOE across the weeks present, and bars sorted descending (over-targeted
 * on top). teamConcentration drives the highlight.
 */
function summarize(rows: ReceiverWeekRow[]): Map<string, TeamSummary> {
  const byTeam = new Map<string, ReceiverWeekRow[]>();
  for (const r of rows) {
    const list = byTeam.get(r.team);
    if (list) list.push(r);
    else byTeam.set(r.team, [r]);
  }

  const out = new Map<string, TeamSummary>();
  for (const [team, teamRows] of byTeam) {
    // Mean TOE per player across the filtered weeks.
    const agg = new Map<string, { name: string; sum: number; n: number }>();
    for (const r of teamRows) {
      const cur = agg.get(r.playerId);
      if (cur) {
        cur.sum += r.toe;
        cur.n += 1;
      } else {
        agg.set(r.playerId, { name: r.playerName, sum: r.toe, n: 1 });
      }
    }
    const bars: PlayerBar[] = [...agg.entries()]
      .map(([playerId, v]) => ({
        playerId,
        name: shortName(v.name),
        toe: v.sum / v.n,
      }))
      .sort((a, b) => b.toe - a.toe);

    const conc = teamConcentration(teamRows);
    out.set(team, {
      team,
      bars,
      gini: conc.gini,
      topShare: conc.topShare,
      oneReceiverOffense: conc.oneReceiverOffense,
      spreadTheBall: !conc.oneReceiverOffense && conc.gini <= 0.2,
    });
  }
  return out;
}

interface BarTooltipItem {
  payload: PlayerBar;
}

function BarTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: BarTooltipItem[];
}) {
  if (!active || !payload || payload.length === 0) return null;
  const p = payload[0].payload;
  const signed = `${p.toe >= 0 ? "+" : ""}${Math.round(p.toe * 100)}%`;
  return (
    <div className="rounded-md border border-edge bg-ink/95 px-2.5 py-1.5 text-xs shadow-xl">
      <span className="font-black text-slate-50">{p.name}</span>{" "}
      <span className={p.toe >= 0 ? "font-bold text-pos" : "font-bold text-neg"}>
        TOE {signed}
      </span>
    </div>
  );
}

function TeamPanel({ summary }: { summary: TeamSummary | undefined; }) {
  // Empty team (no rows under the current filters) still renders a stub so the
  // grid always shows 32 panels.
  if (!summary || summary.bars.length === 0) {
    return (
      <div className="rounded-lg border border-edge bg-panel p-3">
        <div className="mb-1 flex items-baseline justify-between">
          <span className="text-lg font-black tracking-tight text-slate-50">
            {summary?.team ?? ""}
          </span>
        </div>
        <p className="flex h-[128px] items-center justify-center text-center text-xs font-bold text-slate-600">
          No data for filters
        </p>
      </div>
    );
  }

  const extreme = summary.oneReceiverOffense;
  const spread = summary.spreadTheBall;

  const borderClass = extreme
    ? "border-accent"
    : spread
    ? "border-pos/60"
    : "border-edge";

  // Chart height scales with the number of bars (compact but readable).
  const height = Math.max(128, summary.bars.length * 18);

  return (
    <div
      className={`rounded-lg border bg-panel p-3 ${borderClass} ${
        extreme ? "border-2" : ""
      }`}
    >
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="text-lg font-black tracking-tight text-slate-50">
          {summary.team}
        </span>
        {extreme && (
          <span className="rounded bg-accent px-1.5 py-0.5 text-[10px] font-black uppercase tracking-wider text-ink">
            One-receiver
          </span>
        )}
        {spread && (
          <span className="rounded bg-pos/20 px-1.5 py-0.5 text-[10px] font-black uppercase tracking-wider text-pos">
            Spread
          </span>
        )}
      </div>

      <div style={{ height }} className="w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            layout="vertical"
            data={summary.bars}
            margin={{ top: 2, right: 8, bottom: 2, left: 8 }}
            barCategoryGap={2}
          >
            <XAxis type="number" hide domain={["dataMin", "dataMax"]} />
            <YAxis
              type="category"
              dataKey="name"
              width={64}
              tick={{ fill: "#cbd5e1", fontSize: 10, fontWeight: 700 }}
              tickLine={false}
              axisLine={false}
              interval={0}
            />
            <Tooltip
              content={<BarTooltip />}
              cursor={{ fill: "#1e2636", fillOpacity: 0.4 }}
            />
            <Bar dataKey="toe" radius={2} isAnimationActive={false}>
              {summary.bars.map((b) => (
                <Cell
                  key={b.playerId}
                  fill={b.toe >= 0 ? "#22d3ee" : "#fb7185"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function TeamPanels() {
  const { filtered, loading, error } = useDashboard();

  const summaries = useMemo(() => summarize(filtered), [filtered]);

  return (
    <section className="rounded-xl border border-edge bg-panel p-6">
      <div className="mb-4">
        <h2 className="text-2xl font-black tracking-tight text-slate-50">
          Team Tendency
        </h2>
        <p className="text-sm text-slate-400">
          Each panel: receivers sorted over-targeted (cyan) to ignored (rose).
          <span className="ml-2 font-bold text-accent">Yellow border</span> = one-receiver offense,{" "}
          <span className="font-bold text-pos">cyan border</span> = spread-the-ball.
        </p>
      </div>

      {loading && (
        <p className="py-16 text-center text-xl font-bold text-slate-300">
          Loading teams…
        </p>
      )}
      {error && (
        <p className="py-16 text-center text-xl font-bold text-neg">{error}</p>
      )}

      {!loading && !error && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-8">
          {ALL_TEAMS.map((team) => (
            <TeamPanel key={team} summary={summaries.get(team) ?? { team, bars: [], gini: 0, topShare: 0, oneReceiverOffense: false, spreadTheBall: false }} />
          ))}
        </div>
      )}
    </section>
  );
}
