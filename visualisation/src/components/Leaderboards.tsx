"use client";

// Two always-visible, side-by-side leaderboards built from the filtered
// dataset:
//   Left  — "Most Over-Targeted"  (top 10 by positive TOE)
//   Right — "Most Ignored / Coach I Was Open" (top 10 by negative TOE)
// Each row shows a large bold player name, team badge, a big signed/colored
// TOE value, and a one-line derived story hook for instant on-air talking
// points.

import { useMemo } from "react";

import { useDashboard } from "@/hooks/useDashboard";
import { deriveStoryHook } from "@/lib/stories";
import type { ReceiverWeekRow } from "@/lib/types";

const TOP_N = 10;

/** One representative row per player (the week with the largest |TOE|). */
function reduceToPlayers(rows: ReceiverWeekRow[]): ReceiverWeekRow[] {
  const repByPlayer = new Map<string, ReceiverWeekRow>();
  for (const r of rows) {
    const cur = repByPlayer.get(r.playerId);
    if (!cur || Math.abs(r.toe) > Math.abs(cur.toe)) repByPlayer.set(r.playerId, r);
  }
  return [...repByPlayer.values()];
}

function signedPct(x: number): string {
  return `${x >= 0 ? "+" : ""}${Math.round(x * 100)}%`;
}

function LeaderRow({
  rank,
  row,
  tone,
}: {
  rank: number;
  row: ReceiverWeekRow;
  tone: "pos" | "neg";
}) {
  const toneText = tone === "pos" ? "text-pos" : "text-neg";
  return (
    <li className="flex items-center gap-4 border-b border-edge/60 py-3 last:border-0">
      <span className="w-6 shrink-0 text-right text-lg font-black text-slate-600">
        {rank}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="truncate text-xl font-black text-slate-50">
            {row.playerName}
          </span>
          <span className="shrink-0 rounded bg-edge px-2 py-0.5 text-xs font-bold uppercase tracking-wider text-slate-300">
            {row.team}
          </span>
        </div>
        <p className="mt-0.5 truncate text-sm text-slate-400">
          {deriveStoryHook(row)}
        </p>
      </div>
      <span className={`shrink-0 text-2xl font-black tabular-nums ${toneText}`}>
        {signedPct(row.toe)}
      </span>
    </li>
  );
}

function Panel({
  title,
  subtitle,
  rows,
  tone,
}: {
  title: string;
  subtitle: string;
  rows: ReceiverWeekRow[];
  tone: "pos" | "neg";
}) {
  const accent = tone === "pos" ? "border-t-pos" : "border-t-neg";
  return (
    <div className={`rounded-xl border border-edge border-t-4 ${accent} bg-panel p-5`}>
      <h3 className="text-xl font-black tracking-tight text-slate-50">{title}</h3>
      <p className="mb-2 text-sm text-slate-400">{subtitle}</p>
      {rows.length === 0 ? (
        <p className="py-10 text-center text-base font-bold text-slate-500">
          No receivers match the current filters.
        </p>
      ) : (
        <ol>
          {rows.map((row, i) => (
            <LeaderRow key={row.playerId} rank={i + 1} row={row} tone={tone} />
          ))}
        </ol>
      )}
    </div>
  );
}

export function Leaderboards() {
  const { filtered } = useDashboard();

  const { overTargeted, ignored } = useMemo(() => {
    const players = reduceToPlayers(filtered);
    const over = players
      .filter((p) => p.toe > 0)
      .sort((a, b) => b.toe - a.toe)
      .slice(0, TOP_N);
    const ign = players
      .filter((p) => p.toe < 0)
      .sort((a, b) => a.toe - b.toe)
      .slice(0, TOP_N);
    return { overTargeted: over, ignored: ign };
  }, [filtered]);

  return (
    <section className="grid grid-cols-1 gap-5 lg:grid-cols-2">
      <Panel
        title="Most Over-Targeted"
        subtitle="Fed more than their separation earns"
        rows={overTargeted}
        tone="pos"
      />
      <Panel
        title="Most Ignored / Coach I Was Open"
        subtitle="Open but not getting the ball"
        rows={ignored}
        tone="neg"
      />
    </section>
  );
}
