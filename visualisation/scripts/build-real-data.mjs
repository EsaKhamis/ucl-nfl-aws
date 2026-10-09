// =============================================================================
// build-real-data.mjs
// -----------------------------------------------------------------------------
// REAL-DATA ETL for the NFL "Target Over Expectation" (TOE) dashboard.
//
// Converts the NFL Big Data Bowl 2023 CSVs (2021 season, weeks 1-8) into the
// receivers.json shape consumed by the dashboard UI. This is the NO-TRACKING
// proxy pipeline: the tracking/ folder is ignored entirely; "open rate" is a
// documented target-rate PROXY (see derivation 7 below), not true separation.
//
// SOURCE DIRECTORY (absolute, read-only; nothing here is modified):
//   c:\Users\yousu\OneDrive\Documents\GitHub\ucl-nfl-aws\data
//     games.csv            gameId, season, week, homeTeamAbbr, visitorTeamAbbr
//     players.csv          nflId, officialPosition, displayName, ...
//     plays.csv            gameId, playId, playDescription, possessionTeam,
//                          defensiveTeam, passResult, pff_passCoverageType, ...
//     pffScoutingData.csv  gameId, playId, nflId, pff_role, ...
//   (tracking/ is IGNORED on purpose.)
//
// OUTPUT (both files written identically):
//   ../public/data/receivers.json       (dashboard loads this)
//   ../public/data/receivers.real.json   (identical backup copy)
//
// OUTPUT ENVELOPE (byte-compatible with the dashboard — see src/lib/types.ts,
// src/context/DashboardProvider.tsx validateFile, scripts/check-data.mjs):
//   {
//     schemaVersion, generatedAt,
//     expectationModel: { formula, a, b },   // a/b are a least-squares fit of
//                                             // expectedTargetShare ~ a+b*openRate
//                                             // over the real rows, so the UI's
//                                             // displayed model string is
//                                             // meaningful. Per-row toe does NOT
//                                             // use a/b (the UI reads
//                                             // row.targetShare-row.expectedTargetShare).
//     receivers: [ ReceiverWeekRow, ... ]     // one row per player per week
//   }
// NOTE: the task brief says "JSON array of objects", but the dashboard already
// in this folder REQUIRES the wrapped object (it reads file.receivers and
// file.expectationModel and throws otherwise). "UI renders with zero code
// changes" is the hard requirement, so the wrapper wins. Each per-row object
// still matches the required field names/derivations exactly.
//
// TEAM ABBREVIATION: source uses 'LA' for the LA Rams -> mapped to 'LAR' on
// output. All other abbreviations are already standard.
//
// =============================================================================
// DERIVATIONS (each row is one player's week; all rate fields rounded 4 dp):
//
//  1. ROUTES. Each pffScoutingData row with pff_role=='Pass Route' is one route
//     for (gameId, playId, nflId). Joined to plays for possessionTeam / coverage
//     type and to games for week. routesRun = count of a player's Pass Route
//     rows in the week. The player's team for the week = MODE of possessionTeam
//     over their route plays. opponent = the defensiveTeam faced (mode over the
//     same plays). gameId emitted = the game the player ran the most routes in
//     that week.
//
//  2. TARGETS. The targeted receiver is parsed from playDescription via
//     "... to <token>" or "... intended for <token>" (interceptions). <token>
//     is firstInitials + '.' + lastName as the NFL gamebook renders it, e.g.
//     "A.Cooper", "D.Schultz", compound-first "D.J. Moore" -> "Dj.Moore",
//     "Amon-Ra St. Brown" -> "A.St.Brown". We resolve a token to an nflId by
//     building the SAME token for every player on the possessionTeam roster and
//     matching (case-insensitive, trailing '.' stripped). If several roster
//     players share a token, prefer the one who ran a Pass Route on that play.
//     targets = count of the week's plays where the player was the parsed+
//     matched target. teamTargets(week) = number of that team's pass plays in
//     the week whose target parsed AND matched a roster player (so shares sum
//     sensibly; unmatched/throw-away/spike plays are excluded from the base).
//
//  3. RECEPTIONS / YARDS. A matched target with passResult=='C' is a reception.
//     yards parsed from "for <N> yards" (negative allowed); "no gain" -> 0.
//     Any target whose yardage can't be parsed contributes 0 yards (noted).
//
//  4. targetShare = playerTargets / teamTargets(week), clamped 0..1.
//
//  5. expectedTargetShare = routesRun / teamRoutes(week), where teamRoutes is
//     the sum of routesRun over that team's KEPT WR/TE/RB that week. Rationale:
//     a player who runs 30% of the team's routes is "expected" to earn ~30% of
//     the targets. THIS IS THE SWAPPABLE EXPECTATION BASELINE (route
//     participation). Clamped 0..1.
//
//  6. toe = round(targetShare - expectedTargetShare, 4). May be negative.
//
//  7. openRate = PROXY = round(targets / routesRun, 4), clamped 0..1. This is a
//     TARGET-RATE proxy for separation, used only because the no-tracking
//     pipeline cannot measure true openness. Rows with routesRun==0 are dropped.
//
//  8. MAN / ZONE. Routes and targets are recomputed restricted to plays with
//     pff_passCoverageType=='Man' vs 'Zone' ('Other' excluded).
//       openRateVsMan  = targetsVsMan  / routesVsMan   (0 if routesVsMan==0)
//       openRateVsZone = targetsVsZone / routesVsZone  (0 if routesVsZone==0)
//       targetShareVsMan  = playerTargetsVsMan  / teamTargetsVsMan(week)  (0 if 0)
//       targetShareVsZone = playerTargetsVsZone / teamTargetsVsZone(week) (0 if 0)
//
// POSITION MAP: WR->WR, TE->TE, RB/HB/FB->RB. All others (QB/OL/DEF) dropped.
// Only players who ran >=1 Pass Route that week are emitted.
//
// CONSISTENCY GUARANTEES (asserted at the end): receptions<=targets<=routesRun;
// toe==targetShare-expectedTargetShare within rounding; every rate in 0..1.
//
// ASSUMPTIONS / NOTES:
//   - A "pass play" for teamTargets is any play whose description contains a
//     parseable+matched target token (complete, incomplete, or intercepted).
//     Sacks/scrambles/throw-aways carry no target and are excluded from the base.
//   - Compound first-name initials are concatenated as the gamebook does
//     ("D.J." -> "Dj"); last names keep internal '.', '-' and apostrophes.
//   - No heavy dependencies: a small, robust hand-rolled RFC-4180-ish CSV reader
//     is used (handles quotes, embedded commas, embedded newlines, "" escapes).
//
// RUN:  node scripts/build-real-data.mjs   (from the visualisation folder)
// =============================================================================

import { mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SRC_DIR = "c:\\Users\\yousu\\OneDrive\\Documents\\GitHub\\ucl-nfl-aws\\data";
const OUT_DIR = join(ROOT, "public", "data");
const OUT_MAIN = join(OUT_DIR, "receivers.json");
const OUT_BACKUP = join(OUT_DIR, "receivers.real.json");

const SCHEMA_VERSION = "1.0.0-real";
const NA = "NA";

// --- team abbreviation normalisation ----------------------------------------
function normTeam(abbr) {
  return abbr === "LA" ? "LAR" : abbr;
}

// --- small math helpers ------------------------------------------------------
function clamp(x, lo, hi) {
  return Math.max(lo, Math.min(hi, x));
}
function clamp01(x) {
  return clamp(x, 0, 1);
}
function round(x, dp = 4) {
  const f = 10 ** dp;
  return Math.round((x + Number.EPSILON) * f) / f;
}
function safeDiv(a, b) {
  return b > 0 ? a / b : 0;
}
function mode(arr) {
  const counts = new Map();
  let best = null;
  let bestN = -1;
  for (const v of arr) {
    const n = (counts.get(v) ?? 0) + 1;
    counts.set(v, n);
    if (n > bestN) {
      bestN = n;
      best = v;
    }
  }
  return best;
}

// -----------------------------------------------------------------------------
// Robust CSV reader (RFC-4180-ish): quoted fields, embedded commas / newlines,
// doubled "" escapes. Returns array of row objects keyed by the header.
// -----------------------------------------------------------------------------
function parseCsv(text) {
  const rows = [];
  let field = "";
  let record = [];
  let inQuotes = false;
  let i = 0;
  const n = text.length;

  // Normalise BOM.
  if (text.charCodeAt(0) === 0xfeff) i = 1;

  function endField() {
    record.push(field);
    field = "";
  }
  function endRecord() {
    endField();
    // Skip fully empty trailing lines.
    if (!(record.length === 1 && record[0] === "")) {
      rows.push(record);
    }
    record = [];
  }

  while (i < n) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 2;
          continue;
        }
        inQuotes = false;
        i++;
        continue;
      }
      field += c;
      i++;
      continue;
    }
    if (c === '"') {
      inQuotes = true;
      i++;
      continue;
    }
    if (c === ",") {
      endField();
      i++;
      continue;
    }
    if (c === "\r") {
      // Handle CRLF and lone CR.
      if (text[i + 1] === "\n") i++;
      endRecord();
      i++;
      continue;
    }
    if (c === "\n") {
      endRecord();
      i++;
      continue;
    }
    field += c;
    i++;
  }
  // Flush last field/record if the file doesn't end with a newline.
  if (field !== "" || record.length > 0) {
    endRecord();
  }

  if (rows.length === 0) return [];
  const header = rows[0];
  const out = [];
  for (let r = 1; r < rows.length; r++) {
    const rec = rows[r];
    const obj = {};
    for (let c = 0; c < header.length; c++) {
      obj[header[c]] = rec[c] ?? "";
    }
    out.push(obj);
  }
  return out;
}

function readCsv(name) {
  const text = readFileSync(join(SRC_DIR, name), "utf8");
  return parseCsv(text);
}

// -----------------------------------------------------------------------------
// Name/token handling. Build the gamebook-style token(s) for a player's name so
// we can match against the token parsed from playDescription.
//   "Amari Cooper"          -> ["a.cooper"]
//   "Dalton Schultz"        -> ["d.schultz"]
//   "D.J. Moore"            -> ["dj.moore", "d.moore"]
//   "T.J. Hockenson"        -> ["tj.hockenson", "t.hockenson"]
//   "Amon-Ra St. Brown"     -> ["a.st.brown"]
//
// WHY MULTIPLE TOKENS: the NFL gamebook is INCONSISTENT for compound first
// initials. It renders "D.J. Moore" as "Dj.Moore" (both initials) but
// "T.J. Hockenson" / "K.J. Osborn" / "D.J. Chark" with the FIRST initial only
// ("T.Hockenson", "K.Osborn", "D.Chark"). The rendering is not derivable from
// the stored displayName, so we emit both the concatenated-initials form and
// the first-initial-only form and accept a match on either. Verified against
// the data: zero within-team collisions on the first-initial form, so this
// adds no ambiguity. The remaining ambiguity (if any) is still broken by
// route participation on the play. Last names keep internal '.', '-', '\''.
// -----------------------------------------------------------------------------
function playerTokens(displayName) {
  const name = displayName.trim();
  if (!name) return [];

  const words = name.split(/\s+/);
  if (words.length === 1) {
    return [normalizeToken(words[0])];
  }

  // Known multi-word last-name prefixes that the gamebook keeps attached.
  const lastNamePrefixes = new Set(["st.", "st", "van", "von", "de", "del", "la", "le", "mac", "mc", "o'"]);

  let lastStart = words.length - 1;
  if (lastStart - 1 >= 1 && lastNamePrefixes.has(words[lastStart - 1].toLowerCase())) {
    lastStart -= 1;
  }

  const firstWords = words.slice(0, lastStart);
  const lastWords = words.slice(lastStart);
  const lastName = lastWords.join("");

  // Collect first-portion initials in order ("D.J." -> ["D","J"]).
  const initials = [];
  for (const w of firstWords) {
    if (w.includes(".")) {
      for (const piece of w.split(".")) {
        const ch = piece.match(/[A-Za-z]/);
        if (ch) initials.push(ch[0]);
      }
    } else {
      const ch = w.match(/[A-Za-z]/);
      if (ch) initials.push(ch[0]);
    }
  }
  if (initials.length === 0) {
    return [normalizeToken(lastName)];
  }

  const tokens = new Set();
  // Full concatenated-initials form ("Dj.Moore").
  tokens.add(normalizeToken(`${initials.join("")}.${lastName}`));
  // First-initial-only form ("T.Hockenson").
  tokens.add(normalizeToken(`${initials[0]}.${lastName}`));
  return [...tokens];
}

function normalizeToken(tok) {
  // Lowercase, drop trailing periods, remove internal spaces (so a prefixed
  // last name like "St. Brown" -> "st.brown" matches regardless of the space
  // the gamebook inserts), keep '\'' and '-'.
  return tok.toLowerCase().replace(/\s+/g, "").replace(/\.+$/, "");
}

// Parse the target token out of a play description.
function parseTargetToken(desc) {
  // Prefer "to <token>" then fall back to "intended for <token>".
  // Token: an uppercase initial, '.', then a last name of letters/'/'-; the
  // last name may be a two-part prefixed name the gamebook writes with a space,
  // e.g. "A.St. Brown" -> captured as "A.St. Brown" (an optional
  // "<Prefix>. <Word>" tail). normalizeToken then drops the internal space.
  const rx =
    /(?: to | intended for )([A-Z][A-Za-z]*\.(?:[A-Za-z]+\.\s)?[A-Za-z][A-Za-z'\-]*)/;
  const m = rx.exec(desc);
  if (!m) return null;
  return normalizeToken(m[1]);
}

// Parse yardage from a play description. "for 5 yards" -> 5, "for -3 yards" ->
// -3, "no gain" -> 0, "for 1 yard" -> 1. Returns null if nothing parseable.
function parseYards(desc) {
  if (/\bno gain\b/i.test(desc)) return 0;
  const m = /for (-?\d+) yards?\b/i.exec(desc);
  if (m) return parseInt(m[1], 10);
  return null;
}

// =============================================================================
// LOAD
// =============================================================================
console.log(`Reading CSVs from ${SRC_DIR} ...`);
const games = readCsv("games.csv");
const players = readCsv("players.csv");
const plays = readCsv("plays.csv");
const pff = readCsv("pffScoutingData.csv");
console.log(
  `  games=${games.length} players=${players.length} plays=${plays.length} pff=${pff.length}`
);

// gameId -> week
const weekByGame = new Map();
for (const g of games) {
  weekByGame.set(g.gameId, Number(g.week));
}

// nflId -> player meta (only kept skill positions)
function mapPosition(official) {
  if (official === "WR") return "WR";
  if (official === "TE") return "TE";
  if (official === "RB" || official === "HB" || official === "FB") return "RB";
  return null;
}
const playerMeta = new Map();
for (const p of players) {
  const pos = mapPosition(p.officialPosition);
  playerMeta.set(p.nflId, {
    nflId: p.nflId,
    name: p.displayName,
    position: pos, // may be null for non-skill
    tokens: playerTokens(p.displayName), // one or more gamebook-style tokens
  });
}

// play key -> play meta
function playKey(gameId, playId) {
  return `${gameId}|${playId}`;
}
const playMeta = new Map();
for (const pl of plays) {
  const week = weekByGame.get(pl.gameId);
  if (week == null) continue; // play from a game not in games.csv
  playMeta.set(playKey(pl.gameId, pl.playId), {
    gameId: pl.gameId,
    playId: pl.playId,
    week,
    possessionTeam: normTeam(pl.possessionTeam),
    defensiveTeam: normTeam(pl.defensiveTeam),
    passResult: pl.passResult,
    coverageType: pl.pff_passCoverageType, // Man / Zone / Other / NA
    desc: pl.playDescription,
    targetToken: parseTargetToken(pl.playDescription),
    yards: parseYards(pl.playDescription),
  });
}

// =============================================================================
// ROUTES: build per (week, player) route rows and per-play route participation.
// =============================================================================
// routesByWeekPlayer: `${week}|${nflId}` -> { count, manCount, zoneCount,
//   teamCounts(Map team->n), oppCounts(Map), gameCounts(Map) }
const routesByWeekPlayer = new Map();
// routeParticipants: playKey -> Set(nflId) who ran a route (for tie-break).
const routeParticipants = new Map();

let routeRows = 0;
for (const row of pff) {
  if (row.pff_role !== "Pass Route") continue;
  const meta = playerMeta.get(row.nflId);
  if (!meta || !meta.position) continue; // only kept skill positions
  const pm = playMeta.get(playKey(row.gameId, row.playId));
  if (!pm) continue;
  routeRows++;

  // tie-break participation
  const pk = playKey(row.gameId, row.playId);
  if (!routeParticipants.has(pk)) routeParticipants.set(pk, new Set());
  routeParticipants.get(pk).add(row.nflId);

  const key = `${pm.week}|${row.nflId}`;
  let agg = routesByWeekPlayer.get(key);
  if (!agg) {
    agg = {
      week: pm.week,
      nflId: row.nflId,
      count: 0,
      manCount: 0,
      zoneCount: 0,
      teamCounts: new Map(),
      oppCounts: new Map(),
      gameCounts: new Map(),
    };
    routesByWeekPlayer.set(key, agg);
  }
  agg.count++;
  if (pm.coverageType === "Man") agg.manCount++;
  else if (pm.coverageType === "Zone") agg.zoneCount++;
  agg.teamCounts.set(pm.possessionTeam, (agg.teamCounts.get(pm.possessionTeam) ?? 0) + 1);
  agg.oppCounts.set(pm.defensiveTeam, (agg.oppCounts.get(pm.defensiveTeam) ?? 0) + 1);
  agg.gameCounts.set(pm.gameId, (agg.gameCounts.get(pm.gameId) ?? 0) + 1);
}
console.log(`  Pass Route rows (kept skill players, joined): ${routeRows}`);

// Resolve each player's team / opponent / gameId for the week (mode).
function modeOfMap(m) {
  let best = null;
  let bestN = -1;
  for (const [k, v] of m) {
    if (v > bestN) {
      bestN = v;
      best = k;
    }
  }
  return best;
}
for (const agg of routesByWeekPlayer.values()) {
  agg.team = modeOfMap(agg.teamCounts);
  agg.opponent = modeOfMap(agg.oppCounts);
  agg.gameId = modeOfMap(agg.gameCounts);
}

// =============================================================================
// TARGETS: resolve each pass play's target token to an nflId on the possession
// team roster, then count targets / receptions / yards per (week, player) and
// team denominators.
// =============================================================================

// Precompute token -> candidate nflIds per team (across kept skill players who
// appear anywhere in the season on route rows for that team OR in the roster).
// We match against ALL players (not just skill) to detect ambiguity, but only
// skill players produce output rows; a target resolved to a non-skill player
// (rare, e.g. a lineman eligible) is still counted into teamTargets if matched
// to a skill player only. To keep teamTargets sensible we count a target in the
// base ONLY when it resolves to a kept skill player.

// Build team roster token index lazily from players that ran >=1 route for that
// team this season (more reliable than officialPosition alone), falling back to
// all players sharing the token.
// playersByTeamSeason: team -> Set(nflId) that ran a route for team.
const playersByTeamSeason = new Map();
for (const agg of routesByWeekPlayer.values()) {
  for (const [team] of agg.teamCounts) {
    if (!playersByTeamSeason.has(team)) playersByTeamSeason.set(team, new Set());
    playersByTeamSeason.get(team).add(agg.nflId);
  }
}

// Resolve a target token on a specific play to an nflId (kept skill player).
function resolveTarget(pm) {
  const token = pm.targetToken;
  if (!token) return null;
  const team = pm.possessionTeam;
  const roster = playersByTeamSeason.get(team);
  if (!roster) return null;

  const candidates = [];
  for (const nflId of roster) {
    const meta = playerMeta.get(nflId);
    if (!meta || !meta.position) continue;
    if (meta.tokens.includes(token)) candidates.push(nflId);
  }
  if (candidates.length === 0) return null;
  if (candidates.length === 1) return candidates[0];

  // Ambiguous: prefer the candidate who ran a route on THIS play.
  const participants = routeParticipants.get(playKey(pm.gameId, pm.playId));
  if (participants) {
    const onPlay = candidates.filter((id) => participants.has(id));
    if (onPlay.length === 1) return onPlay[0];
    if (onPlay.length > 1) return onPlay[0]; // still tied; take first deterministically
  }
  return candidates[0];
}

// Aggregations.
// targetsByWeekPlayer: `${week}|${nflId}` -> { targets, receptions, yards,
//   manTargets, zoneTargets }
const targetsByWeekPlayer = new Map();
// teamTargets: `${week}|${team}` -> { all, man, zone }
const teamTargets = new Map();

for (const pm of playMeta.values()) {
  const nflId = resolveTarget(pm);
  if (!nflId) continue; // no parseable+matched target: excluded from base
  const team = pm.possessionTeam;

  // team denominators
  const tk = `${pm.week}|${team}`;
  let td = teamTargets.get(tk);
  if (!td) {
    td = { all: 0, man: 0, zone: 0 };
    teamTargets.set(tk, td);
  }
  td.all++;
  if (pm.coverageType === "Man") td.man++;
  else if (pm.coverageType === "Zone") td.zone++;

  // player tallies
  const key = `${pm.week}|${nflId}`;
  let pt = targetsByWeekPlayer.get(key);
  if (!pt) {
    pt = { targets: 0, receptions: 0, yards: 0, manTargets: 0, zoneTargets: 0 };
    targetsByWeekPlayer.set(key, pt);
  }
  pt.targets++;
  if (pm.coverageType === "Man") pt.manTargets++;
  else if (pm.coverageType === "Zone") pt.zoneTargets++;
  if (pm.passResult === "C") {
    pt.receptions++;
    pt.yards += pm.yards == null ? 0 : pm.yards;
  }
}

// =============================================================================
// TEAM ROUTES per week (for expectedTargetShare) over KEPT skill players.
// =============================================================================
// teamRoutes: `${week}|${team}` -> { all, man, zone }
const teamRoutes = new Map();
for (const agg of routesByWeekPlayer.values()) {
  const tk = `${agg.week}|${agg.team}`;
  let tr = teamRoutes.get(tk);
  if (!tr) {
    tr = { all: 0, man: 0, zone: 0 };
    teamRoutes.set(tk, tr);
  }
  tr.all += agg.count;
  tr.man += agg.manCount;
  tr.zone += agg.zoneCount;
}

// =============================================================================
// EMIT ROWS
// =============================================================================
const rows = [];
for (const agg of routesByWeekPlayer.values()) {
  if (agg.count < 1) continue; // routesRun >= 1
  const meta = playerMeta.get(agg.nflId);
  if (!meta || !meta.position) continue;

  const key = `${agg.week}|${agg.nflId}`;
  const pt = targetsByWeekPlayer.get(key) ?? {
    targets: 0,
    receptions: 0,
    yards: 0,
    manTargets: 0,
    zoneTargets: 0,
  };

  const tTargets = teamTargets.get(`${agg.week}|${agg.team}`) ?? { all: 0, man: 0, zone: 0 };
  const tRoutes = teamRoutes.get(`${agg.week}|${agg.team}`) ?? { all: 0, man: 0, zone: 0 };

  const routesRun = agg.count;
  const targets = pt.targets;
  const receptions = pt.receptions;
  const yards = pt.yards;

  const openRate = clamp01(safeDiv(targets, routesRun));
  const targetShare = clamp01(safeDiv(targets, tTargets.all));
  const expectedTargetShare = clamp01(safeDiv(routesRun, tRoutes.all));
  const toe = round(round(targetShare) - round(expectedTargetShare));

  const openRateVsMan = clamp01(safeDiv(pt.manTargets, agg.manCount));
  const openRateVsZone = clamp01(safeDiv(pt.zoneTargets, agg.zoneCount));
  const targetShareVsMan = clamp01(safeDiv(pt.manTargets, tTargets.man));
  const targetShareVsZone = clamp01(safeDiv(pt.zoneTargets, tTargets.zone));

  rows.push({
    playerId: String(agg.nflId),
    playerName: meta.name,
    team: agg.team,
    position: meta.position,
    week: agg.week,
    opponent: agg.opponent,
    gameId: String(agg.gameId),
    openRate: round(openRate),
    targetShare: round(targetShare),
    expectedTargetShare: round(expectedTargetShare),
    toe,
    openRateVsMan: round(openRateVsMan),
    openRateVsZone: round(openRateVsZone),
    targetShareVsMan: round(targetShareVsMan),
    targetShareVsZone: round(targetShareVsZone),
    routesRun,
    targets,
    receptions,
    yards,
  });
}

// Recompute toe exactly from the stored rounded fields (dashboard asserts
// toe === targetShare - expectedTargetShare within 1e-9).
for (const r of rows) {
  r.toe = round(r.targetShare - r.expectedTargetShare);
}

// Sort deterministically: week, team, descending toe.
rows.sort((a, b) => a.week - b.week || a.team.localeCompare(b.team) || b.toe - a.toe);

// =============================================================================
// EXPECTATION MODEL (display-only a/b). Least-squares fit of
// expectedTargetShare ~ a + b*openRate over the emitted rows. Per-row toe does
// NOT use these; they only make the dashboard's displayed model line meaningful.
// =============================================================================
function fitLinear(xs, ys) {
  const n = xs.length;
  if (n === 0) return { a: 0, b: 0 };
  let sx = 0, sy = 0, sxx = 0, sxy = 0;
  for (let i = 0; i < n; i++) {
    sx += xs[i];
    sy += ys[i];
    sxx += xs[i] * xs[i];
    sxy += xs[i] * ys[i];
  }
  const denom = n * sxx - sx * sx;
  if (Math.abs(denom) < 1e-12) return { a: round(sy / n, 6), b: 0 };
  const b = (n * sxy - sx * sy) / denom;
  const a = (sy - b * sx) / n;
  return { a: round(a, 6), b: round(b, 6) };
}
const fit = fitLinear(
  rows.map((r) => r.openRate),
  rows.map((r) => r.expectedTargetShare)
);

const output = {
  schemaVersion: SCHEMA_VERSION,
  generatedAt: new Date().toISOString(),
  expectationModel: {
    formula: "expectedTargetShare = routesRun / teamRoutes(week) (route-participation baseline)",
    a: fit.a,
    b: fit.b,
  },
  receivers: rows,
};

// =============================================================================
// WRITE
// =============================================================================
mkdirSync(OUT_DIR, { recursive: true });
const json = JSON.stringify(output, null, 2) + "\n";
writeFileSync(OUT_MAIN, json, "utf8");
writeFileSync(OUT_BACKUP, json, "utf8");

// =============================================================================
// CONSISTENCY ASSERTIONS
// =============================================================================
const EPS = 1e-9;
let bad = 0;
for (const r of rows) {
  if (!(r.receptions <= r.targets && r.targets <= r.routesRun)) bad++;
  if (Math.abs(r.toe - (r.targetShare - r.expectedTargetShare)) > EPS) bad++;
  for (const f of [
    "openRate",
    "targetShare",
    "expectedTargetShare",
    "openRateVsMan",
    "openRateVsZone",
    "targetShareVsMan",
    "targetShareVsZone",
  ]) {
    if (r[f] < 0 || r[f] > 1) bad++;
  }
}
if (bad > 0) {
  console.error(`CONSISTENCY FAILURES: ${bad}`);
  process.exit(1);
}

// =============================================================================
// SUMMARY
// =============================================================================
const distinctPlayers = new Set(rows.map((r) => r.playerId)).size;
const distinctTeams = new Set(rows.map((r) => r.team)).size;
const weeks = [...new Set(rows.map((r) => r.week))].sort((a, b) => a - b);

console.log("");
console.log("=== REAL DATA BUILD SUMMARY ===");
console.log(`player-week rows : ${rows.length}`);
console.log(`distinct players : ${distinctPlayers}`);
console.log(`distinct teams   : ${distinctTeams} (expect 32)`);
console.log(`weeks            : ${weeks.join(", ")} (expect 1..8)`);
console.log(`expectation fit  : a=${fit.a}, b=${fit.b} (display only)`);
console.log(`wrote            : ${OUT_MAIN}`);
console.log(`wrote            : ${OUT_BACKUP}`);

const wk1 = rows.filter((r) => r.week === 1).sort((a, b) => b.toe - a.toe);
function fmt(r) {
  return `${r.toe >= 0 ? "+" : ""}${r.toe.toFixed(4)}  ${r.playerName} (${r.team}) ts=${r.targetShare} ets=${r.expectedTargetShare} rt=${r.routesRun} tg=${r.targets}`;
}
console.log("");
console.log("--- Week 1 top-5 TOE (most over-targeted) ---");
wk1.slice(0, 5).forEach((r) => console.log("  " + fmt(r)));
console.log("--- Week 1 bottom-5 TOE (most ignored) ---");
wk1.slice(-5).reverse().forEach((r) => console.log("  " + fmt(r)));
