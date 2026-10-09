"use client";

// Final broadcast composition (FEAT-004). Dark, high-contrast, desktop-first
// (~1920px) layout for broadcast monitors. Order:
//   FilterBar (sticky) > Story Mode > HeadlineChart (hero) > Leaderboards >
//   TeamPanels > BallFlow > CoverageProfile.
// Every section reads the shared DashboardProvider context via useDashboard()
// so filters and Story Mode apply consistently.

import { BallFlow } from "@/components/BallFlow";
import { CoverageProfile } from "@/components/CoverageProfile";
import { FilterBar } from "@/components/FilterBar";
import { HeadlineChart } from "@/components/HeadlineChart";
import { Leaderboards } from "@/components/Leaderboards";
import { MethodologyNote } from "@/components/MethodologyNote";
import { StoryMode } from "@/components/StoryMode";
import { TeamPanels } from "@/components/TeamPanels";
import { useDashboard } from "@/hooks/useDashboard";

/** A labelled section wrapper with a large, scannable broadcast heading. */
function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-edge pb-2">
        <h2 className="text-2xl font-black tracking-tight text-slate-50">
          {title}
        </h2>
        {subtitle && (
          <p className="text-base font-semibold text-slate-500">{subtitle}</p>
        )}
      </div>
      {children}
    </section>
  );
}

export function DashboardShell() {
  const { loading, error } = useDashboard();

  return (
    <div className="min-h-screen bg-ink">
      <FilterBar />

      <main className="mx-auto flex max-w-[1920px] flex-col gap-10 px-6 py-8 lg:px-10">
        <header className="flex flex-col gap-1">
          <p className="text-sm font-black uppercase tracking-[0.3em] text-accent">
            Target Over Expectation
          </p>
          <h1 className="text-5xl font-black leading-none tracking-tight text-slate-50">
            NFL TOE Broadcast Dashboard
          </h1>
          <p className="mt-1 text-xl font-semibold text-slate-400">
            Who&apos;s force-fed, who&apos;s being ignored — three strong points
            in under 10 seconds.
          </p>
        </header>

        {error && (
          <p className="rounded-lg border border-neg/60 bg-neg/10 px-4 py-3 text-lg font-bold text-neg">
            Failed to load data: {error}
          </p>
        )}

        {loading && (
          <p className="text-xl font-bold text-slate-300">Loading receivers…</p>
        )}

        {!error && (
          <>
            <StoryMode />

            <Section
              title="Headline Chart"
              subtitle="Open Rate vs Target Share — extremes labelled"
            >
              <HeadlineChart />
            </Section>

            <Section
              title="Leaderboards"
              subtitle="Most over-targeted vs most ignored"
            >
              <Leaderboards />
            </Section>

            <Section
              title="Team Tendency"
              subtitle="One-receiver offenses vs spread-the-ball"
            >
              <TeamPanels />
            </Section>

            <Section
              title="Where the Ball Goes Instead"
              subtitle="Ignored receivers → actual targets"
            >
              <BallFlow />
            </Section>

            <Section
              title="Coverage Profile"
              subtitle="Man-only, zone-only, and wins-both specialists"
            >
              <CoverageProfile />
            </Section>
          </>
        )}
        <MethodologyNote />
      </main>
    </div>
  );
}
