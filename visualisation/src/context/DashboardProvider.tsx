"use client";

// Single source of truth for the dashboard: loads receivers.json once, holds
// filter + story-mode state, and exposes a memoized filtered dataset. Every
// section reads this via useDashboard() so filters apply consistently.

import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  applyFilters,
  defaultFilters,
  type FilterState,
} from "@/lib/filters";
import type { ExpectationModel, ReceiverWeekRow, ReceiversFile } from "@/lib/types";

export interface DashboardContextValue {
  /** True while the data file is loading. */
  loading: boolean;
  /** Set if loading or validation failed. */
  error: string | null;
  /** All rows from the file (unfiltered). */
  rows: ReceiverWeekRow[];
  /** Rows after applying the current filters. */
  filtered: ReceiverWeekRow[];
  /** Expectation model from the file. */
  model: ExpectationModel | null;

  filters: FilterState;
  setFilters: (next: Partial<FilterState>) => void;
  resetFilters: () => void;

  storyMode: boolean;
  setStoryMode: (on: boolean) => void;
  toggleStoryMode: () => void;
}

export const DashboardContext = createContext<DashboardContextValue | null>(null);

const DATA_URL = "/data/receivers.json";

/** Runtime validation of the fetched file against the ReceiversFile shape. */
function validateFile(data: unknown): ReceiversFile {
  if (typeof data !== "object" || data === null) {
    throw new Error("receivers.json is not an object");
  }
  const f = data as Partial<ReceiversFile>;
  if (!Array.isArray(f.receivers)) {
    throw new Error("receivers.json: 'receivers' must be an array");
  }
  if (
    !f.expectationModel ||
    typeof f.expectationModel.a !== "number" ||
    typeof f.expectationModel.b !== "number"
  ) {
    throw new Error("receivers.json: 'expectationModel' with numeric a/b required");
  }
  if (f.receivers.length > 0) {
    const r = f.receivers[0] as Partial<ReceiverWeekRow>;
    const requiredNumeric: (keyof ReceiverWeekRow)[] = [
      "openRate",
      "targetShare",
      "expectedTargetShare",
      "toe",
      "week",
    ];
    for (const key of requiredNumeric) {
      if (typeof r[key] !== "number") {
        throw new Error(`receivers.json: row field '${String(key)}' must be a number`);
      }
    }
    if (typeof r.playerId !== "string" || typeof r.team !== "string") {
      throw new Error("receivers.json: row 'playerId'/'team' must be strings");
    }
  }
  return f as ReceiversFile;
}

export function DashboardProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<ReceiverWeekRow[]>([]);
  const [model, setModel] = useState<ExpectationModel | null>(null);
  const [filters, setFiltersState] = useState<FilterState>(defaultFilters);
  // Talking Points (Story Mode) open by default; the toggle still turns it off.
  const [storyMode, setStoryMode] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(DATA_URL, { cache: "no-store" });
        if (!res.ok) {
          throw new Error(`Failed to load ${DATA_URL}: ${res.status}`);
        }
        const json = (await res.json()) as unknown;
        const file = validateFile(json);
        if (cancelled) return;
        setRows(file.receivers);
        setModel(file.expectationModel);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const setFilters = useCallback((next: Partial<FilterState>) => {
    setFiltersState((prev) => ({ ...prev, ...next }));
  }, []);

  const resetFilters = useCallback(() => {
    setFiltersState(defaultFilters);
  }, []);

  const toggleStoryMode = useCallback(() => {
    setStoryMode((s) => !s);
  }, []);

  const filtered = useMemo(() => applyFilters(rows, filters), [rows, filters]);

  const value = useMemo<DashboardContextValue>(
    () => ({
      loading,
      error,
      rows,
      filtered,
      model,
      filters,
      setFilters,
      resetFilters,
      storyMode,
      setStoryMode,
      toggleStoryMode,
    }),
    [
      loading,
      error,
      rows,
      filtered,
      model,
      filters,
      setFilters,
      resetFilters,
      storyMode,
      toggleStoryMode,
    ]
  );

  return (
    <DashboardContext.Provider value={value}>
      {children}
    </DashboardContext.Provider>
  );
}
