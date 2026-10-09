"use client";

// Live-broadcast filter bar: sticky, dark, high-contrast, big tactile
// controls. Week / Position / Coverage / Current-Game. All controls write to
// the shared DashboardProvider filter state via useDashboard(), so every
// section stays in sync.

import { useMemo } from "react";

import { useDashboard } from "@/hooks/useDashboard";
import { availableGames, availableWeeks } from "@/lib/filters";
import type { CoverageFilter, PositionFilter } from "@/lib/types";

const POSITIONS: { value: PositionFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "WR", label: "WR" },
  { value: "TE", label: "TE" },
  { value: "RB", label: "RB" },
];

const COVERAGES: { value: CoverageFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "man", label: "Man" },
  { value: "zone", label: "Zone" },
];

/** A segmented group of big tactile toggle buttons. */
function SegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (next: T) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[0.65rem] font-bold uppercase tracking-[0.2em] text-slate-500">
        {label}
      </span>
      <div className="flex gap-1 rounded-lg border border-edge bg-ink p-1">
        {options.map((opt) => {
          const active = opt.value === value;
          return (
            <button
              key={opt.value}
              type="button"
              onClick={() => onChange(opt.value)}
              aria-pressed={active}
              className={[
                "min-w-[3rem] rounded-md px-3 py-2 text-base font-bold transition-colors",
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
  );
}

export function FilterBar() {
  const { rows, filters, setFilters, resetFilters } = useDashboard();

  const weeks = useMemo(() => availableWeeks(rows), [rows]);
  const games = useMemo(
    () => availableGames(rows, filters.week),
    [rows, filters.week]
  );

  // Build readable matchup labels (AWAY @ HOME) per gameId within the scope.
  const gameLabels = useMemo(() => {
    const scoped =
      filters.week !== "all"
        ? rows.filter((r) => r.week === filters.week)
        : rows;
    const map = new Map<string, string>();
    for (const r of scoped) {
      if (!map.has(r.gameId)) {
        map.set(r.gameId, `${r.team} vs ${r.opponent}`);
      }
    }
    return map;
  }, [rows, filters.week]);

  return (
    <div className="sticky top-0 z-30 border-b border-edge bg-panel/95 backdrop-blur supports-[backdrop-filter]:bg-panel/80">
      <div className="mx-auto flex max-w-[1920px] flex-wrap items-end gap-5 px-6 py-4">
        {/* Week */}
        <div className="flex flex-col gap-1">
          <span className="text-[0.65rem] font-bold uppercase tracking-[0.2em] text-slate-500">
            Week
          </span>
          <select
            value={filters.week === "all" ? "all" : String(filters.week)}
            onChange={(e) => {
              const v = e.target.value;
              // Changing the week invalidates the game selection.
              setFilters({
                week: v === "all" ? "all" : Number(v),
                gameId: "all",
              });
            }}
            className="rounded-lg border border-edge bg-ink px-4 py-2 text-base font-bold text-slate-50 focus:border-accent focus:outline-none"
          >
            <option value="all">All weeks</option>
            {weeks.map((w) => (
              <option key={w} value={w}>
                Week {w}
              </option>
            ))}
          </select>
        </div>

        {/* Position */}
        <SegmentedControl<PositionFilter>
          label="Position"
          value={filters.position}
          options={POSITIONS}
          onChange={(position) => setFilters({ position })}
        />

        {/* Coverage */}
        <SegmentedControl<CoverageFilter>
          label="Coverage"
          value={filters.coverage}
          options={COVERAGES}
          onChange={(coverage) => setFilters({ coverage })}
        />

        {/* Current Game */}
        <div className="flex flex-col gap-1">
          <span className="text-[0.65rem] font-bold uppercase tracking-[0.2em] text-slate-500">
            Current Game
          </span>
          <select
            value={filters.gameId}
            onChange={(e) => setFilters({ gameId: e.target.value })}
            className="max-w-[16rem] rounded-lg border border-edge bg-ink px-4 py-2 text-base font-bold text-slate-50 focus:border-accent focus:outline-none"
          >
            <option value="all">All games</option>
            {games.map((g) => (
              <option key={g} value={g}>
                {gameLabels.get(g) ?? g}
              </option>
            ))}
          </select>
        </div>

        {/* Reset */}
        <button
          type="button"
          onClick={resetFilters}
          className="ml-auto rounded-lg border border-edge px-4 py-2 text-sm font-bold uppercase tracking-wider text-slate-400 transition-colors hover:border-slate-500 hover:text-slate-100"
        >
          Reset
        </button>
      </div>
    </div>
  );
}
