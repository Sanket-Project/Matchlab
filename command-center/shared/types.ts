import { z } from "zod";
import {
  MarketQuoteSchema,
  MarketsResponseSchema,
  AIBriefingItemSchema,
  AIBriefingResponseSchema,
  ScheduledEventSchema,
  EventsResponseSchema,
  ModelReleaseSchema,
  ModelReleaseResponseSchema,
  AINewsCardSchema,
  AINewsResponseSchema,
  F1DriverStandingSchema,
  F1ConstructorStandingSchema,
  F1RaceSchema,
  F1PodiumEntrySchema,
  F1ResponseSchema,
  MatchTeamSchema,
  MatchEventDetailSchema,
  SportsMatchSchema,
  MatchesResponseSchema,
  HealthStatusSchema,
} from "./schemas.js";

export type MarketQuote = z.infer<typeof MarketQuoteSchema>;
export type MarketsResponse = z.infer<typeof MarketsResponseSchema>;

export type AIBriefingItem = z.infer<typeof AIBriefingItemSchema>;
export type AIBriefingResponse = z.infer<typeof AIBriefingResponseSchema>;

export type ScheduledEvent = z.infer<typeof ScheduledEventSchema>;
export type EventsResponse = z.infer<typeof EventsResponseSchema>;

export type ModelRelease = z.infer<typeof ModelReleaseSchema>;
export type ModelReleaseResponse = z.infer<typeof ModelReleaseResponseSchema>;

export type AINewsCard = z.infer<typeof AINewsCardSchema>;
export type AINewsResponse = z.infer<typeof AINewsResponseSchema>;

export type F1DriverStanding = z.infer<typeof F1DriverStandingSchema>;
export type F1ConstructorStanding = z.infer<typeof F1ConstructorStandingSchema>;
export type F1Race = z.infer<typeof F1RaceSchema>;
export type F1PodiumEntry = z.infer<typeof F1PodiumEntrySchema>;
export type F1Response = z.infer<typeof F1ResponseSchema>;

export type MatchTeam = z.infer<typeof MatchTeamSchema>;
export type MatchEventDetail = z.infer<typeof MatchEventDetailSchema>;
export type SportsMatch = z.infer<typeof SportsMatchSchema>;
export type MatchesResponse = z.infer<typeof MatchesResponseSchema>;

export type HealthStatus = z.infer<typeof HealthStatusSchema>;

export interface TodayAtAGlance {
  marketLeader: {
    symbol: string;
    name: string;
    changePct: number;
    price: number;
    currency: string;
  } | null;
  topHeadline: {
    title: string;
    source: string;
    whyItMatters: string;
  } | null;
  nextF1Session: {
    sessionName: string;
    countdown: string;
    dateIST: string;
  } | null;
  nextMatch: {
    matchName: string;
    competition: string;
    kickoffTimeIST: string;
    isLive: boolean;
  } | null;
  keyTodayEvent: {
    title: string;
    timeIST: string;
    impact: string;
  } | null;
  checkedAt: string;
}
