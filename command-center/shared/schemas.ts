import { z } from "zod";

export const MarketQuoteSchema = z.object({
  symbol: z.string(),
  name: z.string(),
  price: z.number(),
  change: z.number(),
  changePct: z.number(),
  currency: z.string(),
  dayHigh: z.number().nullable().optional(),
  dayLow: z.number().nullable().optional(),
  asOf: z.string(),
  series: z.array(z.number()),
  marketStatus: z.enum(["open", "closed", "pre", "post"]),
  exchange: z.string(),
  source: z.string(),
  region: z.string().optional(),
  category: z.enum(["index", "commodity", "fx", "crypto"]).optional(),
});

export const MarketsResponseSchema = z.object({
  ok: z.boolean(),
  indices: z.array(MarketQuoteSchema),
  commoditiesAndFx: z.array(MarketQuoteSchema),
  checkedAt: z.string(),
  isStale: z.boolean().default(false),
  lastGoodAt: z.string().optional(),
  error: z.string().optional(),
});

export const AIBriefingItemSchema = z.object({
  id: z.string(),
  headline: z.string(),
  summary: z.string().max(300), // at most ~40 words
  category: z.string(),
  confidence: z.enum(["confirmed", "reported"]),
  whyItMatters: z.string(),
  sourceUrls: z.array(z.string().url()).min(1),
  published: z.string(),
});

export const AIBriefingResponseSchema = z.object({
  ok: z.boolean(),
  items: z.array(AIBriefingItemSchema).min(3),
  generatedAt: z.string(),
  modelUsed: z.string(),
  isStale: z.boolean().default(false),
  lastGoodAt: z.string().optional(),
  validationErrors: z.array(z.string()).optional(),
});

export const ScheduledEventSchema = z.object({
  id: z.string(),
  timeIST: z.string(),
  title: z.string(),
  description: z.string(),
  category: z.enum(["earnings", "economic", "ai", "sports", "policy"]),
  impact: z.enum(["high", "medium", "low"]),
  source: z.string(),
  confirmed: z.boolean(),
  statusLabel: z.string(), // e.g. "time TBC" or "09:30 AM IST"
  isPreview48h: z.boolean().default(false),
  dateLabel: z.string(),
});

export const EventsResponseSchema = z.object({
  ok: z.boolean(),
  todayEvents: z.array(ScheduledEventSchema),
  preview48hEvents: z.array(ScheduledEventSchema),
  checkedAt: z.string(),
  isStale: z.boolean().default(false),
});

export const ModelReleaseSchema = z.object({
  id: z.string(),
  name: z.string(),
  lab: z.string(),
  releaseStatus: z.enum(["released", "announced", "preview", "deprecated"]),
  releasedAt: z.string(),
  ageDays: z.number(),
  isNew: z.boolean(),
  contextWindow: z.number().optional(),
  priceIn: z.number().optional(),
  priceOut: z.number().optional(),
  isFree: z.boolean().default(false),
  blurb: z.string(),
  url: z.string().url(),
  officialSource: z.string(),
});

export const ModelReleaseResponseSchema = z.object({
  ok: z.boolean(),
  items: z.array(ModelReleaseSchema),
  source: z.string(),
  checkedAt: z.string(),
  isStale: z.boolean().default(false),
});

export const AINewsCardSchema = z.object({
  id: z.string(),
  title: z.string(),
  url: z.string().url(),
  source: z.string(),
  published: z.string(),
  publishedRelative: z.string(),
  labs: z.array(z.string()),
  whyItMatters: z.string(),
  theme: z.string(),
  sourceCount: z.number().default(1),
  sources: z.array(z.object({ name: z.string(), url: z.string() })).default([]),
});

export const AINewsResponseSchema = z.object({
  ok: z.boolean(),
  items: z.array(AINewsCardSchema),
  checkedAt: z.string(),
  isStale: z.boolean().default(false),
  sourcesStatus: z.array(z.object({ source: z.string(), ok: z.boolean() })),
});

export const F1DriverStandingSchema = z.object({
  position: z.number(),
  driverName: z.string(),
  driverCode: z.string(),
  constructorName: z.string(),
  points: z.number(),
  gapToLeader: z.number(),
  wins: z.number(),
  teamColor: z.string(),
});

export const F1ConstructorStandingSchema = z.object({
  position: z.number(),
  constructorName: z.string(),
  points: z.number(),
  gapToLeader: z.number(),
  wins: z.number(),
  teamColor: z.string(),
});

export const F1RaceSchema = z.object({
  round: z.number(),
  raceName: z.string(),
  circuitName: z.string(),
  country: z.string(),
  dateIST: z.string(),
  rawDate: z.string(),
  isSprint: z.boolean(),
  isCompleted: z.boolean(),
  winner: z.string().optional(),
});

export const F1PodiumEntrySchema = z.object({
  position: z.number(),
  driver: z.string(),
  team: z.string(),
  timeOrGap: z.string(),
});

export const F1ResponseSchema = z.object({
  ok: z.boolean(),
  session: z.object({
    isLive: z.boolean(),
    sessionType: z.string(),
    currentTimingOrClassification: z.string(),
    nextSessionName: z.string(),
    nextSessionDateIST: z.string(),
    nextSessionCountdown: z.string(),
    lastCompletedSessionName: z.string(),
  }),
  driverStandings: z.array(F1DriverStandingSchema),
  constructorStandings: z.array(F1ConstructorStandingSchema),
  raceCalendar: z.array(F1RaceSchema),
  lastRaceResult: z.object({
    raceName: z.string(),
    dateIST: z.string(),
    circuit: z.string(),
    podium: z.array(F1PodiumEntrySchema),
    fastestLap: z.object({ driver: z.string(), time: z.string() }).optional(),
    notableIncidents: z.string(),
    fullClassificationUrl: z.string(),
  }),
  checkedAt: z.string(),
  isStale: z.boolean().default(false),
  source: z.string(),
});

export const MatchTeamSchema = z.object({
  name: z.string(),
  score: z.union([z.string(), z.number()]).optional(),
  crest: z.string().optional(),
  isFavorite: z.boolean().default(false),
});

export const MatchEventDetailSchema = z.object({
  minute: z.string(),
  type: z.string(),
  player: z.string(),
  team: z.string(),
});

export const SportsMatchSchema = z.object({
  id: z.string(),
  sport: z.enum(["football", "cricket"]),
  competitionId: z.string(),
  competitionName: z.string(),
  status: z.enum(["upcoming", "live", "full_time"]),
  statusText: z.string(),
  minuteOrSession: z.string().optional(),
  kickoffTimeIST: z.string(),
  venue: z.string(),
  homeTeam: MatchTeamSchema,
  awayTeam: MatchTeamSchema,
  details: z.object({
    lineups: z.object({ home: z.array(z.string()), away: z.array(z.string()) }).optional(),
    events: z.array(MatchEventDetailSchema).optional(),
    headToHead: z.string().optional(),
    summary: z.string().optional(),
  }).optional(),
});

export const MatchesResponseSchema = z.object({
  ok: z.boolean(),
  matches: z.array(SportsMatchSchema),
  checkedAt: z.string(),
  isStale: z.boolean().default(false),
  isDemoData: z.boolean().default(false),
  source: z.string(),
});

export const HealthStatusSchema = z.object({
  status: z.enum(["ok", "degraded", "error"]),
  uptime: z.number(),
  checkedAt: z.string(),
  sources: z.record(
    z.object({
      ok: z.boolean(),
      latencyMs: z.number(),
      lastChecked: z.string(),
      lastGoodAt: z.string().optional(),
      error: z.string().optional(),
    })
  ),
});
