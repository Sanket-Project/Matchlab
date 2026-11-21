import { config } from "../../../config/dashboard.config.js";
import { SportsMatch, MatchesResponse } from "../../../shared/types.js";
import { formatToIST } from "../../../shared/formatters.js";
import { globalCache } from "./cache.js";

interface EspnCompetitor {
  id: string;
  name: string;
  displayName: string;
  score?: string;
  logo?: string;
  records?: Array<{ summary: string }>;
}

interface EspnSoccerEvent {
  id: string;
  name: string;
  date: string;
  status: {
    type: {
      name: string;
      description: string;
      state: "pre" | "in" | "post";
      completed: boolean;
      detail?: string;
      shortDetail?: string;
    };
    displayClock?: string;
    period?: number;
  };
  competitions: Array<{
    venue?: { fullName?: string };
    competitors: EspnCompetitor[];
    details?: Array<{
      type: { text: string };
      clock: { displayValue: string };
      team: { displayName: string };
      athletesInvolved?: Array<{ displayName: string }>;
    }>;
  }>;
}

/**
 * Fetch and transform soccer matches from ESPN
 */
async function fetchSoccerMatches(comp: typeof config.sports.football.competitions[0]): Promise<SportsMatch[]> {
  try {
    const res = await fetch(comp.endpoint, {
      headers: { "User-Agent": "Mozilla/5.0 (compatible; FounderCommandCenter/1.0)" },
      signal: AbortSignal.timeout(6000),
    });
    if (!res.ok) throw new Error(`ESPN Soccer HTTP ${res.status}`);

    const json: any = await res.json();
    const events: EspnSoccerEvent[] = json.events || [];
    const matches: SportsMatch[] = [];

    for (const ev of events) {
      const competition = ev.competitions?.[0];
      const competitors = competition?.competitors || [];
      const home = competitors.find((c: any) => c.homeAway === "home") || competitors[0];
      const away = competitors.find((c: any) => c.homeAway === "away") || competitors[1];

      if (!home || !away) continue;

      const state = ev.status?.type?.state;
      let status: "upcoming" | "live" | "full_time" = "upcoming";
      if (state === "in") status = "live";
      else if (state === "post" || ev.status?.type?.completed) status = "full_time";

      const kickoffDate = new Date(ev.date);
      const kickoffTimeIST = formatToIST(kickoffDate);

      // Key match events if available
      const rawEvents = competition?.details || [];
      const eventsList = rawEvents.map((d: any) => ({
        minute: d.clock?.displayValue || "",
        type: d.type?.text || "Event",
        player: d.athletesInvolved?.[0]?.displayName || "Player",
        team: d.team?.displayName || "",
      }));

      const homeName = (home as any).team?.displayName || (home as any).athlete?.displayName || home.displayName || home.name || "Home Team";
      const awayName = (away as any).team?.displayName || (away as any).athlete?.displayName || away.displayName || away.name || "Away Team";

      const isHomeFav = config.sports.football.defaultFavoriteTeams.some(f => homeName.toLowerCase().includes(f.toLowerCase()));
      const isAwayFav = config.sports.football.defaultFavoriteTeams.some(f => awayName.toLowerCase().includes(f.toLowerCase()));

      matches.push({
        id: `match-fb-${ev.id}`,
        sport: "football",
        competitionId: comp.id,
        competitionName: comp.name,
        status,
        statusText: ev.status?.type?.shortDetail || ev.status?.type?.description || "Scheduled",
        minuteOrSession: ev.status?.displayClock,
        kickoffTimeIST,
        venue: competition?.venue?.fullName || "Stadium",
        homeTeam: {
          name: homeName,
          score: home.score,
          crest: (home as any).team?.logo || `https://a.espncdn.com/combiner/i?img=/i/teamlogos/soccer/500/${home.id}.png&h=40&w=40`,
          isFavorite: isHomeFav,
        },
        awayTeam: {
          name: awayName,
          score: away.score,
          crest: (away as any).team?.logo || `https://a.espncdn.com/combiner/i?img=/i/teamlogos/soccer/500/${away.id}.png&h=40&w=40`,
          isFavorite: isAwayFav,
        },
        details: {
          events: eventsList.slice(0, 5),
          headToHead: `${homeName} vs ${awayName}`,
          summary: `Kickoff at ${kickoffTimeIST} at ${competition?.venue?.fullName || "venue"}.`,
        },
      });
    }

    return matches;
  } catch (err: any) {
    console.warn(`[Matches] Error fetching soccer comp ${comp.name}: ${err.message}`);
    return [];
  }
}

/**
 * Fetch and transform cricket matches from ESPN Cricket API
 */
async function fetchCricketMatches(): Promise<SportsMatch[]> {
  try {
    const res = await fetch(config.sports.cricket.scoreboardEndpoint, {
      headers: { "User-Agent": "Mozilla/5.0 (compatible; FounderCommandCenter/1.0)" },
      signal: AbortSignal.timeout(6000),
    });
    if (!res.ok) throw new Error(`ESPN Cricket HTTP ${res.status}`);

    const json: any = await res.json();
    const sports = json?.sports || [];
    const leagues = sports[0]?.leagues || [];
    const matches: SportsMatch[] = [];

    for (const lg of leagues) {
      const compName = lg.name || "Cricket Tournament";
      const events = lg.events || [];

      for (const ev of events) {
        const competitors = ev.competitors || [];
        const home = competitors[0];
        const away = competitors[1];
        if (!home || !away) continue;

        let status: "upcoming" | "live" | "full_time" = "upcoming";
        if (ev.status === "in") status = "live";
        else if (ev.status === "post") status = "full_time";

        const kickoffTimeIST = ev.date ? formatToIST(new Date(ev.date)) : "Time TBC";

        const isHomeFav = config.sports.cricket.defaultFavoriteTeams.some(f => home.name?.includes(f));
        const isAwayFav = config.sports.cricket.defaultFavoriteTeams.some(f => away.name?.includes(f));

        matches.push({
          id: `match-cr-${ev.id || Math.random().toString(36).substring(7)}`,
          sport: "cricket",
          competitionId: `cricket-${compName.toLowerCase().replace(/[^a-z0-9]/g, "-")}`,
          competitionName: compName,
          status,
          statusText: ev.summary || (status === "live" ? "Live in Play" : "Scheduled"),
          minuteOrSession: ev.summary,
          kickoffTimeIST,
          venue: ev.location || "Cricket Ground",
          homeTeam: {
            name: home.name,
            score: home.score,
            isFavorite: isHomeFav,
          },
          awayTeam: {
            name: away.name,
            score: away.score,
            isFavorite: isAwayFav,
          },
          details: {
            summary: ev.summary || `${home.name} vs ${away.name}`,
          },
        });
      }
    }

    return matches;
  } catch (err: any) {
    console.warn(`[Matches] Error fetching cricket: ${err.message}`);
    return [];
  }
}

/**
 * Get unified matches payload with support for favorites & demo mode
 */
export async function getMatchesData(): Promise<MatchesResponse> {
  const isDemo = process.env.USE_MOCK_SPORTS === "true";

  if (isDemo) {
    return {
      ok: true,
      matches: getDemoMatches(),
      checkedAt: new Date().toISOString(),
      isStale: false,
      isDemoData: true,
      source: "Mock Sports Provider (Demo Mode)",
    };
  }

  const result = await globalCache.getOrFetch(
    "matches:all",
    async () => {
      const footballPromises = config.sports.football.competitions.map(c => fetchSoccerMatches(c));
      const cricketPromise = fetchCricketMatches();

      const [footballResults, cricketMatches] = await Promise.all([
        Promise.all(footballPromises),
        cricketPromise,
      ]);

      const allMatches = [...footballResults.flat(), ...cricketMatches];

      if (allMatches.length === 0) {
        console.warn("[Matches] No matches returned from upstream; serving labeled demo data");
        return {
          ok: true,
          matches: getDemoMatches(),
          checkedAt: new Date().toISOString(),
          isDemoData: true,
          source: "Demo Fallback (ESPN Unavailable)",
        };
      }

      return {
        ok: true,
        matches: allMatches,
        checkedAt: new Date().toISOString(),
        isDemoData: false,
        source: "ESPN Sports Global APIs",
      };
    },
    config.cacheTTL.matchesUpcomingSeconds
  );

  return {
    ...result.data,
    isStale: result.isStale,
  };
}

/**
 * High-fidelity demo matches when API key or live upstream is absent
 */
export function getDemoMatches(): SportsMatch[] {
  return [
    {
      id: "demo-fb-1",
      sport: "football",
      competitionId: "eng.1",
      competitionName: "Premier League",
      status: "upcoming",
      statusText: "Today 06:00 PM IST",
      minuteOrSession: "Kickoff 18:00 IST",
      kickoffTimeIST: "Today, 06:00 PM IST",
      venue: "Etihad Stadium, Manchester",
      homeTeam: { name: "Manchester City", score: undefined, isFavorite: true },
      awayTeam: { name: "Fulham", score: undefined, isFavorite: false },
      details: {
        summary: "Manchester City host Fulham in Matchday 12 of the Premier League.",
        headToHead: "Man City have won the last 15 meetings across all competitions.",
      },
    },
    {
      id: "demo-cr-1",
      sport: "cricket",
      competitionId: "cricket-ind-nz",
      competitionName: "India tour of New Zealand 2026/27",
      status: "live",
      statusText: "India 284/4 (78.2 ov) - Day 2 Stumps",
      minuteOrSession: "Day 2 Stumps",
      kickoffTimeIST: "Today, 04:00 AM IST",
      venue: "Seddon Park, Hamilton",
      homeTeam: { name: "New Zealand", score: "312", isFavorite: false },
      awayTeam: { name: "India", score: "284/4", isFavorite: true },
      details: {
        summary: "India trail by 28 runs with 6 wickets in hand.",
        events: [
          { minute: "74.1 ov", type: "boundary", player: "Shubman Gill (112*)", team: "India" },
          { minute: "68.3 ov", type: "wicket", player: "Matt Henry b J. Bumrah", team: "New Zealand" },
        ],
      },
    },
  ];
}
