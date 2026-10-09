"use client";

// Compact methodology note shown under the dashboard header. Two items: the
// route-minimum sample filter (read from ROUTE_MINIMUM so the copy always
// matches the filter every section uses) and how separation / "open" are
// measured from the tracking data (features.py, Config defaults).

import { ROUTE_MINIMUM } from "@/lib/filters";

export function MethodologyNote() {
  return (
    <aside
      aria-label="Methodology"
      className="mt-3 flex max-w-5xl flex-col gap-1 rounded-lg border border-edge bg-panel px-4 py-3 text-sm leading-relaxed text-slate-300"
    >
      <p>
        <span className="font-bold text-slate-100">Sample filter:</span>{" "}
        receivers with fewer than {ROUTE_MINIMUM.season} routes across weeks
        1–8 are dropped from the analysis (fewer than {ROUTE_MINIMUM.perWeek}{" "}
        routes when a single week or game is selected).
      </p>
      <p>
        <span className="font-bold text-slate-100">Separation:</span>{" "}
        straight-line distance in yards from the receiver to the nearest
        defender, taken from player tracking 0.4 seconds before the pass is
        released. Openness then subtracts the ground that defender would close
        in half a second, plus a penalty if he is within 2 yards of the
        throwing lane; the receiver with the highest openness on each play
        counts as &ldquo;open&rdquo; (no fixed yardage cutoff).
      </p>
    </aside>
  );
}
