// =============================================================================
// generate-data.mjs
// -----------------------------------------------------------------------------
// Produces realistic FAKE weekly receiver data for the NFL TOE dashboard and
// writes it to public/data/receivers.json.
//
// FALLBACK / DEMO ONLY. The committed dataset at public/data/receivers.json is
// REAL data built by scripts/build-real-data.mjs. This generator writes to a
// SEPARATE path (public/data/receivers.sample.json) and must NOT overwrite the
// real file. It exists so the dashboard can run against a same-shape synthetic
// file when real data is unavailable.
//
// WHAT IT GENERATES
//   - All 32 real NFL team abbreviations.
//   - 2-3 skill players per team => 80-100 distinct players total.
//   - 8 weekly rows per player (weeks 1-8).
//   - Believable archetypes:
//       * alpha WR          : very high target share, high open rate
//       * slot WR           : high open rate, moderate target share
//       * deep threat WR    : lower open rate, boom/bust target share
//       * checkdown RB      : moderate open rate, steady target share
//       * ignored role WR/TE: solid open rate, suppressed target share
//
// EXPECTATION MODEL (the heart of "Target Over Expectation")
//   expectedTargetShare = clamp(a + b * openRate, 0, 1)
//   toe                 = targetShare - expectedTargetShare
//   a and b are written into expectationModel in the output file and are the
//   single source of truth; src/lib/toe.ts mirrors them as defaults. To swap
//   the model, change A/B here (and the mirror) and regenerate.
//
// CONSISTENCY RULES ENFORCED
//   - receptions <= targets <= routesRun on every row.
//   - openRateVsMan / openRateVsZone average (roughly) to openRate.
//   - targetShareVsMan / targetShareVsZone average (roughly) to targetShare.
//   - Each team's weekly targetShare across ITS receivers sums to ~1 (the
//     modelled skill players are normalized to ~0.92 to leave headroom for
//     the unmodelled rest of the roster, keeping shares realistic and < 1).
//   - toe is computed directly from the model so check-data.mjs passes exactly.
//
// DETERMINISM
//   A small seeded PRNG makes output reproducible run-to-run.
// =============================================================================

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
// Fallback/demo output path — intentionally NOT receivers.json (which holds the
// committed real dataset).
const OUT_PATH = join(ROOT, "public", "data", "receivers.sample.json");

// --- Expectation model parameters -------------------------------------------
const A = 0.04; // intercept
const B = 0.45; // slope on openRate
const FORMULA = "clamp(a + b*openRate, 0, 1)";

const SCHEMA_VERSION = "1.0.0";
const WEEKS = 8;

// Sum of modelled skill players' target share per team per week. Kept below 1
// to leave realistic headroom for the rest of the roster (unmodelled players).
const TEAM_SHARE_BUDGET = 0.92;

const TEAMS = [
  "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
  "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
  "LV", "LAC", "LAR", "MIA", "MIN", "NE", "NO", "NYG",
  "NYJ", "PHI", "PIT", "SF", "SEA", "TB", "TEN", "WAS",
];

// A deterministic round-robin schedule: team i plays team (i+k) in week k.
function opponentFor(teamIndex, week) {
  const n = TEAMS.length;
  const offset = ((week % (n - 1)) + 1);
  return TEAMS[(teamIndex + offset) % n];
}

function gameIdFor(team, opponent, week) {
  // Stable, order-independent game id (home/away not modelled here).
  const [a, b] = [team, opponent].sort();
  return `W${String(week).padStart(2, "0")}-${a}-${b}`;
}

// --- Seeded PRNG (mulberry32) ------------------------------------------------
function makeRng(seed) {
  let s = seed >>> 0;
  return function rng() {
    s |= 0;
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rng = makeRng(20240917);

function rand(min, max) {
  return min + rng() * (max - min);
}
function jitter(base, spread) {
  return base + (rng() - 0.5) * 2 * spread;
}
function clamp(x, lo, hi) {
  return Math.max(lo, Math.min(hi, x));
}
function clamp01(x) {
  return clamp(x, 0, 1);
}
function round(x, dp = 4) {
  const f = 10 ** dp;
  return Math.round(x * f) / f;
}

// --- Archetypes --------------------------------------------------------------
// Each archetype defines base tendencies. targetWeight drives how the team's
// share budget is split; openRate / manBias shape coverage splits and TOE.
const ARCHETYPES = {
  alpha: {
    position: "WR",
    openRate: [0.42, 0.56],
    targetWeight: [3.2, 4.2],
    manBias: [-0.02, 0.06], // slight man advantage
    routes: [30, 40],
    ypr: [11, 15],
  },
  slot: {
    position: "WR",
    openRate: [0.52, 0.68], // gets open a lot
    targetWeight: [1.8, 2.8],
    manBias: [0.05, 0.14], // wins vs man especially
    routes: [26, 36],
    ypr: [8, 12],
  },
  deep: {
    position: "WR",
    openRate: [0.30, 0.44], // harder to separate
    targetWeight: [1.6, 2.6],
    manBias: [-0.14, -0.04], // better vs zone (soft shells)
    routes: [22, 32],
    ypr: [14, 20],
  },
  checkdown: {
    position: "RB",
    openRate: [0.55, 0.70], // wide open underneath
    targetWeight: [1.2, 2.0],
    manBias: [-0.02, 0.05],
    routes: [14, 24],
    ypr: [6, 9],
  },
  ignored: {
    // Solid open rate but suppressed target share => strongly negative TOE.
    position: "WR",
    openRate: [0.48, 0.62],
    targetWeight: [0.6, 1.1],
    manBias: [0.04, 0.12],
    routes: [20, 30],
    ypr: [10, 14],
  },
  ignoredTE: {
    position: "TE",
    openRate: [0.46, 0.60],
    targetWeight: [0.7, 1.3],
    manBias: [0.02, 0.08],
    routes: [20, 30],
    ypr: [9, 13],
  },
};

// Per-team roster: a mix of archetypes. Sized so total players land ~90.
// Some teams get 3 players, some 2 => 32 teams -> ~88 players.
function rosterPlanFor(teamIndex) {
  const plans = [
    ["alpha", "slot", "ignored"],
    ["alpha", "deep", "checkdown"],
    ["alpha", "slot", "deep"],
    ["alpha", "ignoredTE", "checkdown"],
    ["alpha", "deep", "ignored"],
    ["alpha", "slot", "checkdown"],
    ["alpha", "ignored"], // one-receiver-ish team (2 players)
    ["alpha", "deep"], // one-receiver-ish team (2 players)
  ];
  return plans[teamIndex % plans.length];
}

// --- Name generation ---------------------------------------------------------
const FIRST = [
  "Jalen", "Marcus", "Deandre", "Tyree", "Cooper", "Davante", "Amari", "Ja",
  "Mike", "Chris", "Garrett", "Noah", "Elijah", "Isaiah", "Trey", "Devon",
  "Keenan", "Stefon", "DK", "AJ", "CeeDee", "Puka", "Zay", "Rome", "Drake",
  "Brandon", "Calvin", "Terry", "Diontae", "Christian", "Austin", "Rashee",
];
const LAST = [
  "Harris", "Johnson", "Walker", "Hill", "Brown", "Carter", "Reed", "Nabers",
  "Thomas", "Olave", "Wilson", "Jennings", "Dell", "London", "Pittman",
  "Higgins", "Metcalf", "Smith", "Lamb", "Nacua", "Flowers", "Odunze",
  "Lockett", "Aiyuk", "McLaurin", "Johnston", "Bell", "Moore", "Watson",
];

function makeNamePool() {
  const used = new Set();
  return function nextName() {
    for (let attempt = 0; attempt < 500; attempt++) {
      const f = FIRST[Math.floor(rng() * FIRST.length)];
      const l = LAST[Math.floor(rng() * LAST.length)];
      const name = `${f} ${l}`;
      if (!used.has(name)) {
        used.add(name);
        return name;
      }
    }
    // Fallback guaranteed-unique name.
    const name = `Player ${used.size + 1}`;
    used.add(name);
    return name;
  };
}
const nextName = makeNamePool();

// --- Build players -----------------------------------------------------------
const players = [];
let playerCounter = 0;

TEAMS.forEach((team, teamIndex) => {
  const plan = rosterPlanFor(teamIndex);
  const seeds = plan.map((archKey) => {
    const arch = ARCHETYPES[archKey];
    const id = `P${String(++playerCounter).padStart(4, "0")}`;
    return {
      playerId: id,
      playerName: nextName(),
      team,
      teamIndex,
      archKey,
      position: arch.position,
      // Season-level tendencies, jittered per week later.
      baseOpenRate: rand(arch.openRate[0], arch.openRate[1]),
      targetWeight: rand(arch.targetWeight[0], arch.targetWeight[1]),
      manBias: rand(arch.manBias[0], arch.manBias[1]),
      baseRoutes: rand(arch.routes[0], arch.routes[1]),
      ypr: rand(arch.ypr[0], arch.ypr[1]),
    };
  });
  players.push(...seeds);
});

// --- Generate weekly rows ----------------------------------------------------
const rows = [];

for (let week = 1; week <= WEEKS; week++) {
  // Group players by team to normalize target share within each team-week.
  const byTeam = new Map();
  for (const p of players) {
    if (!byTeam.has(p.team)) byTeam.set(p.team, []);
    byTeam.get(p.team).push(p);
  }

  for (const [, teamPlayers] of byTeam) {
    // Weekly weights (jittered) -> normalized to the team share budget.
    const weekWeights = teamPlayers.map((p) => Math.max(0.1, jitter(p.targetWeight, 0.6)));
    const weightSum = weekWeights.reduce((a, b) => a + b, 0);

    teamPlayers.forEach((p, i) => {
      const arch = ARCHETYPES[p.archKey];
      const opponent = opponentFor(p.teamIndex, week);
      const gameId = gameIdFor(p.team, opponent, week);

      const openRate = clamp01(jitter(p.baseOpenRate, 0.06));
      const targetShare = clamp01((weekWeights[i] / weightSum) * TEAM_SHARE_BUDGET);

      // Model expectation + TOE.
      const expectedTargetShare = clamp01(A + B * openRate);
      const toe = targetShare - expectedTargetShare;

      // Coverage splits that average back to the overall value.
      // openRateVsMan/openRateVsZone centered on openRate +/- manBias.
      const orMan = clamp01(openRate + p.manBias);
      const orZone = clamp01(2 * openRate - orMan); // ensures mean ~= openRate
      // Target-share splits: players who win vs man see slightly higher man share.
      const tsBias = p.manBias * 0.5;
      const tsMan = clamp01(targetShare + tsBias);
      const tsZone = clamp01(2 * targetShare - tsMan);

      // Volume stats, honoring receptions <= targets <= routesRun.
      const routesRun = Math.max(6, Math.round(jitter(p.baseRoutes, 4)));
      // Targets scale with target share; capped at routesRun.
      const targets = clamp(
        Math.round(targetShare * rand(28, 40)),
        0,
        routesRun
      );
      const catchRate = clamp01(rand(0.58, 0.78) + (arch.position === "RB" ? 0.08 : 0));
      const receptions = clamp(Math.round(targets * catchRate), 0, targets);
      const yards = Math.round(receptions * p.ypr);

      rows.push({
        playerId: p.playerId,
        playerName: p.playerName,
        team: p.team,
        position: p.position,
        week,
        opponent,
        gameId,
        openRate: round(openRate),
        targetShare: round(targetShare),
        expectedTargetShare: round(expectedTargetShare),
        toe: round(toe),
        openRateVsMan: round(orMan),
        openRateVsZone: round(orZone),
        targetShareVsMan: round(tsMan),
        targetShareVsZone: round(tsZone),
        routesRun,
        targets,
        receptions,
        yards,
      });
    });
  }
}

// --- Recompute toe exactly from stored rounded values ------------------------
// check-data.mjs asserts toe === targetShare - expectedTargetShare within 1e-9.
// Rounding the three fields independently can introduce >1e-9 drift, so set toe
// from the already-rounded fields.
for (const r of rows) {
  r.toe = round(r.targetShare - r.expectedTargetShare);
}

const output = {
  schemaVersion: SCHEMA_VERSION,
  generatedAt: new Date().toISOString(),
  expectationModel: { formula: FORMULA, a: A, b: B },
  receivers: rows,
};

mkdirSync(dirname(OUT_PATH), { recursive: true });
writeFileSync(OUT_PATH, JSON.stringify(output, null, 2) + "\n", "utf8");

const distinctPlayers = new Set(rows.map((r) => r.playerId)).size;
const distinctTeams = new Set(rows.map((r) => r.team)).size;
console.log(
  `Wrote ${rows.length} rows (${distinctPlayers} players, ${distinctTeams} teams, ${WEEKS} weeks) -> ${OUT_PATH}`
);
