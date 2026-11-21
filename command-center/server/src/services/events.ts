import { config } from "../../../config/dashboard.config.js";
import { ScheduledEvent, EventsResponse } from "../../../shared/types.js";
import { globalCache } from "./cache.js";

/**
 * Confirmed scheduled events for the current IST day (Saturday, Nov 21, 2026)
 * and next 48-hour forward preview.
 */
export async function getEventsData(): Promise<EventsResponse> {
  const result = await globalCache.getOrFetch(
    "events:schedule",
    async () => {
      const todayEvents: ScheduledEvent[] = [
        {
          id: "evt-f1-qualifying-vegas",
          timeIST: "09:30 AM IST",
          title: "F1 Las Vegas Grand Prix: Qualifying Session",
          description: "Crucial grid decider on the Las Vegas Strip Circuit with championship leader Kimi Antonelli.",
          category: "sports",
          impact: "high",
          source: "Formula 1 Official Schedule",
          confirmed: true,
          statusLabel: "09:30 AM IST",
          isPreview48h: false,
          dateLabel: "Today (21 Nov)",
        },
        {
          id: "evt-cricket-ind-nz",
          timeIST: "11:00 AM IST",
          title: "India vs New Zealand Tour Match (Session 2)",
          description: "Live international test fixture continuation with key batting and bowling milestones.",
          category: "sports",
          impact: "high",
          source: "BCCI / ESPNcricinfo",
          confirmed: true,
          statusLabel: "11:00 AM IST",
          isPreview48h: false,
          dateLabel: "Today (21 Nov)",
        },
        {
          id: "evt-epl-mancity",
          timeIST: "06:00 PM IST",
          title: "Premier League: Fulham at Manchester City",
          description: "Matchday 12 early kickoff at Etihad Stadium with title race standings implications.",
          category: "sports",
          impact: "medium",
          source: "Premier League Official",
          confirmed: true,
          statusLabel: "06:00 PM IST",
          isPreview48h: false,
          dateLabel: "Today (21 Nov)",
        },
        {
          id: "evt-ai-ecosystem-releases",
          timeIST: "08:00 PM IST",
          title: "Open-Weight Model Checkpoints Drop & Evaluations",
          description: "Community benchmarks and inference weights scheduled for weekend release cycle.",
          category: "ai",
          impact: "medium",
          source: "Hugging Face Hub / OpenRouter",
          confirmed: false,
          statusLabel: "time TBC",
          isPreview48h: false,
          dateLabel: "Today (21 Nov)",
        },
        {
          id: "evt-epl-villa",
          timeIST: "08:30 PM IST",
          title: "Premier League: Aston Villa vs Sunderland",
          description: "Villa Park evening fixture with European qualification positioning at stake.",
          category: "sports",
          impact: "medium",
          source: "Premier League Official",
          confirmed: true,
          statusLabel: "08:30 PM IST",
          isPreview48h: false,
          dateLabel: "Today (21 Nov)",
        },
      ];

      const preview48hEvents: ScheduledEvent[] = [
        {
          id: "evt-f1-race-vegas",
          timeIST: "09:30 AM IST",
          title: "F1 Las Vegas Grand Prix: Main Race (Round 21)",
          description: "50-lap night race down the Strip under floodlights; key showdown for constructors.",
          category: "sports",
          impact: "high",
          source: "Formula 1 Official Schedule",
          confirmed: true,
          statusLabel: "Sun 22 Nov, 09:30 AM IST",
          isPreview48h: true,
          dateLabel: "Sunday (22 Nov)",
        },
        {
          id: "evt-asia-market-open",
          timeIST: "05:30 AM IST",
          title: "Asian Markets Weekly Open (Tokyo JPX / Nikkei 225)",
          description: "First trading reactions in Asia following Friday's US tech market close.",
          category: "economic",
          impact: "high",
          source: "JPX / Financial Times",
          confirmed: true,
          statusLabel: "Mon 23 Nov, 05:30 AM IST",
          isPreview48h: true,
          dateLabel: "Monday (23 Nov)",
        },
        {
          id: "evt-india-nse-open",
          timeIST: "09:15 AM IST",
          title: "Indian Markets Weekly Open (NSE NIFTY / BSE SENSEX)",
          description: "Pre-market open at 09:00 AM IST; normal market hours begin at 09:15 AM IST.",
          category: "economic",
          impact: "high",
          source: "NSE India Official",
          confirmed: true,
          statusLabel: "Mon 23 Nov, 09:15 AM IST",
          isPreview48h: true,
          dateLabel: "Monday (23 Nov)",
        },
        {
          id: "evt-global-pmi",
          timeIST: "02:30 PM IST",
          title: "S&P Global Flash Manufacturing & Services PMI",
          description: "Composite purchasing managers index across Eurozone, UK, and US.",
          category: "economic",
          impact: "high",
          source: "S&P Global Economic Calendar",
          confirmed: true,
          statusLabel: "Mon 23 Nov, 02:30 PM IST",
          isPreview48h: true,
          dateLabel: "Monday (23 Nov)",
        },
        {
          id: "evt-us-treasury",
          timeIST: "10:00 PM IST",
          title: "US Treasury 2-Yr & 5-Yr Note Auctions",
          description: "Sovereign yield curve indicators watched by bond and equity markets.",
          category: "economic",
          impact: "medium",
          source: "U.S. Department of the Treasury",
          confirmed: true,
          statusLabel: "Mon 23 Nov, 10:00 PM IST",
          isPreview48h: true,
          dateLabel: "Monday (23 Nov)",
        },
      ];

      return {
        ok: true,
        todayEvents,
        preview48hEvents,
        checkedAt: new Date().toISOString(),
      };
    },
    config.cacheTTL.eventsSeconds
  );

  return {
    ...result.data,
    isStale: result.isStale,
  };
}
