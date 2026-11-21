import React from "react";
import { MarketsModule } from "./MarketsModule.js";
import { AIBriefingModule } from "./AIBriefingModule.js";
import { EventsModule } from "./EventsModule.js";
import { ModelsModule } from "./ModelsModule.js";
import { NewsModule } from "./NewsModule.js";
import {
  MarketsResponse,
  AIBriefingResponse,
  EventsResponse,
  ModelReleaseResponse,
  AINewsResponse,
} from "@shared/types.js";

interface WorldSectionProps {
  marketsData?: MarketsResponse;
  marketsLoading: boolean;
  marketsError: boolean;
  onRetryMarkets: () => void;

  briefingData?: AIBriefingResponse;
  briefingLoading: boolean;
  briefingError: boolean;
  onRetryBriefing: () => void;

  eventsData?: EventsResponse;
  eventsLoading: boolean;
  eventsError: boolean;
  onRetryEvents: () => void;

  modelsData?: ModelReleaseResponse;
  modelsLoading: boolean;
  modelsError: boolean;
  onRetryModels: () => void;

  newsData?: AINewsResponse;
  newsLoading: boolean;
  newsError: boolean;
  onRetryNews: () => void;

  currency: "INR" | "USD";
}

export const WorldSection: React.FC<WorldSectionProps> = ({
  marketsData,
  marketsLoading,
  marketsError,
  onRetryMarkets,

  briefingData,
  briefingLoading,
  briefingError,
  onRetryBriefing,

  eventsData,
  eventsLoading,
  eventsError,
  onRetryEvents,

  modelsData,
  modelsLoading,
  modelsError,
  onRetryModels,

  newsData,
  newsLoading,
  newsError,
  onRetryNews,

  currency,
}) => {
  return (
    <div className="space-y-6">
      {/* 1. Markets Module */}
      <MarketsModule
        data={marketsData}
        isLoading={marketsLoading}
        isError={marketsError}
        onRetry={onRetryMarkets}
        currency={currency}
      />

      {/* 2. AI Briefing Module */}
      <AIBriefingModule
        data={briefingData}
        isLoading={briefingLoading}
        isError={briefingError}
        onRetry={onRetryBriefing}
      />

      {/* 3. What Happens Today Module */}
      <EventsModule
        data={eventsData}
        isLoading={eventsLoading}
        isError={eventsError}
        onRetry={onRetryEvents}
      />

      {/* 4. Newer Model Releases Module */}
      <ModelsModule
        data={modelsData}
        isLoading={modelsLoading}
        isError={modelsError}
        onRetry={onRetryModels}
      />

      {/* 5. Latest AI News Module */}
      <NewsModule
        data={newsData}
        isLoading={newsLoading}
        isError={newsError}
        onRetry={onRetryNews}
      />
    </div>
  );
};
