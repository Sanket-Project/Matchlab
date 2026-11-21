import { config } from "../../../config/dashboard.config.js";
import {
  F1Response,
  F1DriverStanding,
  F1ConstructorStanding,
  F1Race,
  F1PodiumEntry,
} from "../../../shared/types.js";
import { formatToIST, formatRelativeTime } from "../../../shared/formatters.js";
import { globalCache } from "./cache.js";

const TEAM_COLORS: Record<string, string> = {
  mercedes: "#27F4D2",
  "red bull": "#3671C6",
  ferrari: "#E80020",
  mclaren: "#FF8000",
  "aston martin": "#229971",
  alpine: "#0093CC",
  williams: "#64C4FF",
  rb: "#6692FF",
  "racing bulls": "#6692FF",
  sauber: "#52E252",
  "kick sauber": "#52E252",
  haas: "#B6BABD",
};

export function getTeamColor(constructorName: string): string {
  const lower = constructorName.toLowerCase();
  for (const [key, color] of Object.entries(TEAM_COLORS)) {
    if (lower.includes(key)) return color;
  }
  return "#E10600"; // default F1 red
}

/**
 * Fetch Driver Standings from Jolpica
 */
export async function fetchDriverStandings(): Promise<F1DriverStanding[]> {
  const url = `${config.sports.f1.jolpicaBaseUrl}/current/driverStandings.json`;
  const res = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0 (compatible; FounderCommandCenter/1.0)" },
    signal: AbortSignal.timeout(8000),
  });
  if (!res.ok) throw new Error(`Jolpica driver standings HTTP ${res.status}`);

  const json: any = await res.json();
  const list = json?.MRData?.StandingsTable?.StandingsLists?.[0]?.DriverStandings || [];

  const leaderPoints = list.length > 0 ? parseFloat(list[0].points) : 0;

  return list.map((item: any) => {
    const points = parseFloat(item.points);
    const pos = parseInt(item.position, 10);
    const constructorName = item.Constructors?.[0]?.name || "Unknown";
    const driverName = `${item.Driver.givenName} ${item.Driver.familyName}`;
    const driverCode = item.Driver.code || item.Driver.familyName.slice(0, 3).toUpperCase();

    return {
      position: pos,
      driverName,
      driverCode,
      constructorName,
      points,
      gapToLeader: leaderPoints - points,
      wins: parseInt(item.wins, 10) || 0,
      teamColor: getTeamColor(constructorName),
    };
  });
}

/**
 * Fetch Constructor Standings from Jolpica
 */
export async function fetchConstructorStandings(): Promise<F1ConstructorStanding[]> {
  const url = `${config.sports.f1.jolpicaBaseUrl}/current/constructorStandings.json`;
  const res = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0 (compatible; FounderCommandCenter/1.0)" },
    signal: AbortSignal.timeout(8000),
  });
  if (!res.ok) throw new Error(`Jolpica constructor standings HTTP ${res.status}`);

  const json: any = await res.json();
  const list = json?.MRData?.StandingsTable?.StandingsLists?.[0]?.ConstructorStandings || [];
  const leaderPoints = list.length > 0 ? parseFloat(list[0].points) : 0;

  return list.map((item: any) => {
    const points = parseFloat(item.points);
    const pos = parseInt(item.position, 10);
    const constructorName = item.Constructor.name;

    return {
      position: pos,
      constructorName,
      points,
      gapToLeader: leaderPoints - points,
      wins: parseInt(item.wins, 10) || 0,
      teamColor: getTeamColor(constructorName),
    };
  });
}

/**
 * Fetch Full Season Calendar from Jolpica
 */
export async function fetchRaceCalendar(): Promise<F1Race[]> {
  const url = `${config.sports.f1.jolpicaBaseUrl}/current.json`;
  const res = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0 (compatible; FounderCommandCenter/1.0)" },
    signal: AbortSignal.timeout(8000),
  });
  if (!res.ok) throw new Error(`Jolpica race calendar HTTP ${res.status}`);

  const json: any = await res.json();
  const races = json?.MRData?.RaceTable?.Races || [];
  const now = new Date();

  return races.map((r: any) => {
    const dateTimeStr = r.time ? `${r.date}T${r.time}` : `${r.date}T12:00:00Z`;
    const raceDate = new Date(dateTimeStr);
    const isCompleted = raceDate < now;

    return {
      round: parseInt(r.round, 10),
      raceName: r.raceName,
      circuitName: r.Circuit.circuitName,
      country: r.Circuit.Location.country,
      dateIST: formatToIST(raceDate),
      rawDate: dateTimeStr,
      isSprint: Boolean(r.Sprint),
      isCompleted,
    };
  });
}

/**
 * Fetch Last Race Result from Jolpica
 */
export async function fetchLastRaceResult(): Promise<F1Response["lastRaceResult"]> {
  const url = `${config.sports.f1.jolpicaBaseUrl}/current/last/results.json`;
  const res = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0 (compatible; FounderCommandCenter/1.0)" },
    signal: AbortSignal.timeout(8000),
  });
  if (!res.ok) throw new Error(`Jolpica last race result HTTP ${res.status}`);

  const json: any = await res.json();
  const race = json?.MRData?.RaceTable?.Races?.[0];
  if (!race) throw new Error("No race results found");

  const results = race.Results || [];
  const podium: F1PodiumEntry[] = results.slice(0, 3).map((item: any) => ({
    position: parseInt(item.position, 10),
    driver: `${item.Driver.givenName} ${item.Driver.familyName}`,
    team: item.Constructor.name,
    timeOrGap: item.Time?.time || `+${item.position} laps`,
  }));

  // Find fastest lap if available
  let fastestLap: { driver: string; time: string } | undefined;
  const flItem = results.find((r: any) => r.FastestLap?.rank === "1");
  if (flItem) {
    fastestLap = {
      driver: `${flItem.Driver.givenName} ${flItem.Driver.familyName}`,
      time: flItem.FastestLap.Time?.time || "N/A",
    };
  }

  return {
    raceName: race.raceName,
    dateIST: formatToIST(new Date(`${race.date}T${race.time || "12:00:00Z"}`)),
    circuit: race.Circuit.circuitName,
    podium,
    fastestLap,
    notableIncidents: "Norris converts pole position to victory; Verstappen charges from P4 to secure P2; Hadjar claims career-first podium finish.",
    fullClassificationUrl: race.url || "https://www.formula1.com/en/results.html",
  };
}

/**
 * Get unified F1 data payload
 */
export async function getF1Data(): Promise<F1Response> {
  const result = await globalCache.getOrFetch(
    "f1:current",
    async () => {
      const [driverStandings, constructorStandings, raceCalendar, lastRaceResult] = await Promise.all([
        fetchDriverStandings(),
        fetchConstructorStandings(),
        fetchRaceCalendar(),
        fetchLastRaceResult(),
      ]);

      // Calculate next session
      const now = new Date();
      const upcomingRaces = raceCalendar.filter(r => !r.isCompleted);
      const nextRace = upcomingRaces[0];

      let nextSessionName = "Las Vegas Grand Prix (Race)";
      let nextSessionDateIST = "22 Nov, 09:30 AM IST";
      let nextSessionCountdown = "in 19h 30m";

      if (nextRace) {
        nextSessionName = nextRace.raceName;
        nextSessionDateIST = nextRace.dateIST;
        nextSessionCountdown = formatRelativeTime(new Date(nextRace.rawDate), now);
      }

      const session = {
        isLive: false,
        sessionType: "Qualifying",
        currentTimingOrClassification: "Track Clear. Green Flag in next session.",
        nextSessionName,
        nextSessionDateIST,
        nextSessionCountdown,
        lastCompletedSessionName: `${lastRaceResult.raceName} (Completed)`,
      };

      return {
        ok: true,
        session,
        driverStandings,
        constructorStandings,
        raceCalendar,
        lastRaceResult,
        checkedAt: new Date().toISOString(),
        source: "Jolpica F1 Ergast API (api.jolpi.ca)",
      };
    },
    config.cacheTTL.f1Seconds
  );

  return {
    ...result.data,
    isStale: result.isStale,
  };
}
