// =============================================================================
// check-data.mjs
// -----------------------------------------------------------------------------
// Integrity gate for public/data/receivers.json. Exits non-zero on any failure
// so it can be wired into CI / the verification loop.
//
// The committed receivers.json is REAL data (Big Data Bowl PFF/play feeds,
// built by scripts/build-real-data.mjs). This check validates SCHEMA +
// CONSISTENCY, not a synthetic row count. It must pass for the real file and
// for any same-shape drop-in (including the synthetic fallback).
//
// Asserts:
//   - Wrapper shape: receivers[] array + expectationModel { a, b } numeric.
//   - All 32 real team abbreviations are present (exactly 32 teams).
//   - Distinct players within a realistic range (>= 50, <= 1200).
//   - Weeks 1-8 all present.
//   - Every row: required fields present with correct types.
//   - Every row: all *Rate / *Share fields within [0, 1] (small epsilon).
//   - Every row: toe === targetShare - expectedTargetShare within rounding.
//   - Every row: receptions <= targets <= routesRun.
//   - Every row: position in {WR, TE, RB}.
// =============================================================================

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DATA_PATH = join(__dirname, "..", "public", "data", "receivers.json");

const EXPECTED_TEAMS = [
  "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
  "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
  "LV", "LAC", "LAR", "MIA", "MIN", "NE", "NO", "NYG",
  "NYJ", "PHI", "PIT", "SF", "SEA", "TB", "TEN", "WAS",
];
const EXPECTED_WEEKS = [1, 2, 3, 4, 5, 6, 7, 8];
const VALID_POSITIONS = new Set(["WR", "TE", "RB"]);

// Player-count bounds sized for REAL data (hundreds of players across a season
// slice) while still rejecting an empty/garbage file. The synthetic fallback
// (~88 players) also falls inside this range.
const MIN_PLAYERS = 50;
const MAX_PLAYERS = 1200;

// toe == targetShare - expectedTargetShare. Rows are rounded to 4 dp in the
// real build, so allow a rounding-scale tolerance rather than 1e-9.
const TOE_EPS = 5e-4;
// Rates/shares must sit in [0,1] with a tiny epsilon for float noise.
const RATE_EPS = 1e-6;

const RATE_FIELDS = [
  "openRate",
  "targetShare",
  "expectedTargetShare",
  "openRateVsMan",
  "openRateVsZone",
  "targetShareVsMan",
  "targetShareVsZone",
];
const NUMERIC_FIELDS = [
  "week",
  ...RATE_FIELDS,
  "toe",
  "routesRun",
  "targets",
  "receptions",
  "yards",
];
const STRING_FIELDS = ["playerId", "playerName", "team", "position", "opponent", "gameId"];

const failures = [];
function check(cond, msg) {
  if (!cond) failures.push(msg);
}

let file;
try {
  file = JSON.parse(readFileSync(DATA_PATH, "utf8"));
} catch (err) {
  console.error(`FATAL: could not read/parse ${DATA_PATH}: ${err.message}`);
  process.exit(1);
}

// Wrapper shape
const rows = Array.isArray(file.receivers) ? file.receivers : null;
check(rows !== null, "receivers array missing");
check(
  file.expectationModel &&
    typeof file.expectationModel.a === "number" &&
    typeof file.expectationModel.b === "number",
  "expectationModel with numeric a/b missing"
);

if (rows) {
  check(rows.length > 0, "receivers array is empty");

  // Teams
  const teams = new Set(rows.map((r) => r.team));
  for (const t of EXPECTED_TEAMS) {
    check(teams.has(t), `missing team: ${t}`);
  }
  check(teams.size === EXPECTED_TEAMS.length, `expected 32 teams, found ${teams.size}`);

  // Weeks
  const weeks = new Set(rows.map((r) => r.week));
  for (const w of EXPECTED_WEEKS) {
    check(weeks.has(w), `missing week: ${w}`);
  }

  // Distinct players
  const players = new Set(rows.map((r) => r.playerId));
  check(
    players.size >= MIN_PLAYERS && players.size <= MAX_PLAYERS,
    `expected ${MIN_PLAYERS}-${MAX_PLAYERS} distinct players, found ${players.size}`
  );

  // Per-row rules
  let typeFails = 0;
  let rangeFails = 0;
  let toeFails = 0;
  let orderFails = 0;
  let posFails = 0;
  for (const r of rows) {
    for (const k of NUMERIC_FIELDS) {
      if (typeof r[k] !== "number" || Number.isNaN(r[k])) typeFails++;
    }
    for (const k of STRING_FIELDS) {
      if (typeof r[k] !== "string") typeFails++;
    }
    for (const k of RATE_FIELDS) {
      const v = r[k];
      if (typeof v === "number" && (v < -RATE_EPS || v > 1 + RATE_EPS)) rangeFails++;
    }
    if (Math.abs(r.toe - (r.targetShare - r.expectedTargetShare)) > TOE_EPS) toeFails++;
    if (!(r.receptions <= r.targets && r.targets <= r.routesRun)) orderFails++;
    if (!VALID_POSITIONS.has(r.position)) posFails++;
  }
  check(typeFails === 0, `${typeFails} field type violations`);
  check(rangeFails === 0, `${rangeFails} rate/share fields outside [0,1]`);
  check(toeFails === 0, `${toeFails} rows violate toe == targetShare - expectedTargetShare`);
  check(orderFails === 0, `${orderFails} rows violate receptions <= targets <= routesRun`);
  check(posFails === 0, `${posFails} rows have invalid position`);
}

if (failures.length) {
  console.error("check-data FAILED:");
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}

console.log(
  `check-data OK: ${rows.length} rows, ${new Set(rows.map((r) => r.playerId)).size} players, ${new Set(rows.map((r) => r.team)).size} teams, weeks ${[...new Set(rows.map((r) => r.week))].sort((a, b) => a - b).join(",")}.`
);
