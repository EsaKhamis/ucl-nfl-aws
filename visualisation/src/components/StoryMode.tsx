"use client";

// Story Mode / Talking Points.
//
// A subtle-but-prominent toggle wired to the DashboardProvider storyMode flag.
// When ON, selectTopNarratives() runs over the CURRENT filtered dataset and
// surfaces the 3-5 most interesting narratives (biggest over-target, biggest
// ignored, a one-receiver offense, a man/zone specialist, a notable checkdown
// pattern) as a bold, high-contrast talking-points strip a commentator can
// read in under 10 seconds. Other sections read the same storyMode flag via
// useDashboard() to add annotation emphasis.

import { useMemo } from "react";

import { useDashboard } from "@/hooks/useDashboard";
import { selectTopNarratives, type NarrativeKind } from "@/lib/stories";

/** Short label + accent tone per narrative kind. */
const KIND_META: Record<
  NarrativeKind,
  { badge: string; ring: string; text: string }
> = {
  "over-targeted": {
    badge: "Over-targeted",
    ring: "border-pos/70",
    text: "text-pos",
  },
  ignored: {
    badge: "Ignored",
    ring: "border-neg/70",
    text: "text-neg",
  },
  "one-receiver-offense": {
    badge: "One-receiver offense",
    ring: "border-accent/70",
    text: "text-accent",
  },
  "coverage-specialist": {
    badge: "Coverage specialist",
    ring: "border-sky-400/70",
    text: "text-sky-300",
  },
  checkdown: {
    badge: "Checkdown",
    ring: "border-violet-400/70",
    text: "text-violet-300",
  },
};

export function StoryMode() {
  const { filtered, storyMode, toggleStoryMode } = useDashboard();

  const narratives = useMemo(
    () => (storyMode ? selectTopNarratives(filtered) : []),
    [storyMode, filtered]
  );

  return (
    <section
      aria-label="Story Mode talking points"
      className={[
        "rounded-2xl border transition-colors",
        storyMode
          ? "border-accent/60 bg-accent/5"
          : "border-edge bg-panel/60",
      ].join(" ")}
    >
      {/* Toggle header */}
      <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
        <div className="flex items-center gap-3">
          <span
            className={[
              "inline-flex h-2.5 w-2.5 rounded-full",
              storyMode ? "bg-accent" : "bg-slate-600",
            ].join(" ")}
            aria-hidden
          />
          <div>
            <h2 className="text-xl font-black tracking-tight text-slate-50">
              Story Mode
            </h2>
            <p className="text-sm font-medium text-slate-400">
              {storyMode
                ? "Top talking points for the current view"
                : "Flip on to surface the 3-5 strongest on-air narratives"}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={toggleStoryMode}
          role="switch"
          aria-checked={storyMode}
          className={[
            "inline-flex items-center gap-3 rounded-xl px-5 py-2.5 text-base font-black uppercase tracking-wider transition-colors",
            storyMode
              ? "bg-accent text-ink hover:bg-accent/90"
              : "border border-edge bg-ink text-slate-200 hover:border-accent/60 hover:text-accent",
          ].join(" ")}
        >
          <span
            className={[
              "inline-flex h-6 w-11 items-center rounded-full p-0.5 transition-colors",
              storyMode ? "bg-ink/30" : "bg-edge",
            ].join(" ")}
            aria-hidden
          >
            <span
              className={[
                "h-5 w-5 rounded-full bg-slate-50 shadow transition-transform",
                storyMode ? "translate-x-5" : "translate-x-0",
              ].join(" ")}
            />
          </span>
          Talking Points
        </button>
      </div>

      {/* Talking-points strip */}
      {storyMode && (
        <div className="border-t border-accent/30 px-5 py-4">
          {narratives.length === 0 ? (
            <p className="text-lg font-bold text-slate-400">
              No standout narratives for this filter — widen the view (try All
              weeks or All games).
            </p>
          ) : (
            <ol className="grid grid-cols-1 gap-3 md:grid-cols-2 2xl:grid-cols-3">
              {narratives.map((n, i) => {
                const meta = KIND_META[n.kind];
                return (
                  <li
                    key={`${n.kind}-${n.playerName}-${i}`}
                    className={[
                      "flex flex-col gap-1 rounded-xl border bg-ink/60 px-4 py-3",
                      meta.ring,
                    ].join(" ")}
                  >
                    <span
                      className={[
                        "text-xs font-black uppercase tracking-[0.18em]",
                        meta.text,
                      ].join(" ")}
                    >
                      {meta.badge}
                    </span>
                    <p className="text-lg font-bold leading-snug text-slate-50">
                      {n.hook}
                    </p>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      )}
    </section>
  );
}
