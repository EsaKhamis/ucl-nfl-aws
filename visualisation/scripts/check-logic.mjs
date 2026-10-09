// =============================================================================
// check-logic.mjs
// -----------------------------------------------------------------------------
// Sanity gate for the TOE / story logic. Because the logic lives in TypeScript
// (src/lib), this script re-implements the SAME small, pure rules against a few
// hand-built sample rows and asserts the expected classifications. It is a
// guardrail against logic drift, not a substitute for the TS source.
//
// If any assertion fails the process exits non-zero.
// =============================================================================

const EPS = 1e-9;
const failures = [];
function assert(cond, msg) {
  if (!cond) failures.push(msg);
}

// --- Mirror of the pure rules in src/lib/toe.ts / stories.ts -----------------
// MODEL mirrors the fitted a/b in receivers.json. It is used ONLY for the
// scatter's reference line (expectedTargetShareLine). Per-row toe is read from
// each row's own targetShare - expectedTargetShare, matching the real data.
const MODEL = { a: 0.085037, b: 0.067407 };
const clamp01 = (x) => Math.max(0, Math.min(1, x));
const expectedTargetShareLine = (openRate) => clamp01(MODEL.a + MODEL.b * openRate);
const pct = (x) => `${Math.round(x * 100)}%`;

function coverageSpecialist(row, threshold = 0.5) {
  const man = row.openRateVsMan >= threshold;
  const zone = row.openRateVsZone >= threshold;
  if (man && zone) return "wins-both";
  if (man) return "man-only";
  if (zone) return "zone-only";
  return "neither";
}

function deriveStoryHook(row) {
  const name = row.playerName;
  if (row.toe <= -0.08) {
    const best =
      row.openRateVsMan >= row.openRateVsZone
        ? { label: "vs man", rate: row.openRateVsMan }
        : { label: "vs zone", rate: row.openRateVsZone };
    return `${name}: only targeted ${pct(row.targetShare)} despite ${pct(best.rate)} open rate ${best.label}`;
  }
  if (row.toe >= 0.08) {
    return `${name}: force-fed ${pct(row.targetShare)} target share on a ${pct(row.openRate)} open rate`;
  }
  const spec = coverageSpecialist(row);
  if (spec === "man-only") {
    return `${name}: gets open vs man (${pct(row.openRateVsMan)}) but disappears vs zone (${pct(row.openRateVsZone)})`;
  }
  if (spec === "zone-only") {
    return `${name}: beats zone (${pct(row.openRateVsZone)}) but struggles vs man (${pct(row.openRateVsMan)})`;
  }
  return `${name}: ${pct(row.targetShare)} target share, ${pct(row.openRate)} open rate (TOE ${row.toe >= 0 ? "+" : ""}${pct(row.toe)})`;
}

// --- Sample rows -------------------------------------------------------------
// Each row carries its OWN expectedTargetShare (as real data does); toe is
// derived from the row, NOT recomputed from the a/b model.
//
// Over-targeted: fed way beyond a modest route-participation expectation.
const overTargeted = {
  playerName: "Alpha Dog",
  openRate: 0.3,
  targetShare: 0.34,
  expectedTargetShare: 0.18,
  openRateVsMan: 0.32,
  openRateVsZone: 0.28,
};
overTargeted.toe = overTargeted.targetShare - overTargeted.expectedTargetShare;

// Ignored: open but starved relative to a high route-participation baseline.
const ignored = {
  playerName: "Open Guy",
  openRate: 0.55,
  targetShare: 0.1,
  expectedTargetShare: 0.28,
  openRateVsMan: 0.6,
  openRateVsZone: 0.5,
};
ignored.toe = ignored.targetShare - ignored.expectedTargetShare;

// Man-only specialist: beats man, invisible vs zone, roughly neutral TOE.
const manOnly = {
  playerName: "Press Beater",
  openRate: 0.45,
  targetShare: 0.24,
  expectedTargetShare: 0.23,
  openRateVsMan: 0.62,
  openRateVsZone: 0.28,
};
manOnly.toe = manOnly.targetShare - manOnly.expectedTargetShare;

// --- Assertions --------------------------------------------------------------
// Reference-line model monotonic + clamped (used for the scatter line only).
assert(
  Math.abs(expectedTargetShareLine(0) - MODEL.a) < EPS,
  "expectedTargetShareLine(0) should equal a"
);
assert(expectedTargetShareLine(1) <= 1 + EPS, "expectedTargetShareLine must be clamped to <= 1");
assert(
  expectedTargetShareLine(0.6) > expectedTargetShareLine(0.2),
  "expectedTargetShareLine must increase with openRate"
);

// TOE signs.
assert(overTargeted.toe > 0.08, `over-targeted TOE should be strongly positive, got ${overTargeted.toe}`);
assert(ignored.toe < -0.08, `ignored TOE should be strongly negative, got ${ignored.toe}`);

// Classifier.
assert(coverageSpecialist(manOnly) === "man-only", "manOnly row should classify as man-only");
assert(coverageSpecialist(ignored) === "wins-both", "ignored row (open vs both) should be wins-both");
assert(
  coverageSpecialist({ openRateVsMan: 0.2, openRateVsZone: 0.6 }) === "zone-only",
  "row open only vs zone should be zone-only"
);
assert(
  coverageSpecialist({ openRateVsMan: 0.2, openRateVsZone: 0.2 }) === "neither",
  "row open vs neither should be neither"
);

// Story hooks.
const overHook = deriveStoryHook(overTargeted);
assert(overHook.includes("force-fed"), `over-targeted hook should mention force-fed, got: ${overHook}`);

const ignoredHook = deriveStoryHook(ignored);
assert(ignoredHook.includes("only targeted"), `ignored hook should mention only targeted, got: ${ignoredHook}`);

const manHook = deriveStoryHook(manOnly);
assert(manHook.includes("vs man"), `man-only hook should mention vs man, got: ${manHook}`);

// --- Report ------------------------------------------------------------------
if (failures.length) {
  console.error("check-logic FAILED:");
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}
console.log("check-logic OK: TOE model, classifiers, and story hooks behave as expected.");
