import React, { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Header } from "./components/Header.js";
import { Navigation, NavTab } from "./components/Navigation.js";
import { TodayAtAGlance } from "./components/TodayAtAGlance.js";
import { WorldSection } from "./components/world/WorldSection.js";
import { F1Section } from "./components/f1/F1Section.js";
import { MatchesSection } from "./components/matches/MatchesSection.js";
import {
  MarketsResponse,
  AIBriefingResponse,
  EventsResponse,
  ModelReleaseResponse,
  AINewsResponse,
  F1Response,
  MatchesResponse,
  TodayAtAGlance as GlanceData,
} from "@shared/types.js";
import { WifiOff } from "lucide-react";

export const App: React.FC = () => {
  const queryClient = useQueryClient();

  // Navigation & Preferences State
  const [currentTab, setCurrentTab] = useState<NavTab>("world");
  const [currency, setCurrency] = useState<"INR" | "USD">("INR");
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [isOffline, setIsOffline] = useState<boolean>(!navigator.onLine);

  // Theme State: Light / Dark and Astryx Theme (Butter, Neutral, Chocolate)
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    return (localStorage.getItem("command-center-theme") as "light" | "dark") ||
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  });

  const [astryxTheme, setAstryxTheme] = useState<"butter" | "neutral" | "chocolate">(() => {
    return (localStorage.getItem("command-center-astryx-theme") as any) || "butter";
  });

  // Apply theme attributes to document element
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("command-center-theme", theme);
  }, [theme]);

  useEffect(() => {
    document.documentElement.setAttribute("data-astryx-theme", astryxTheme);
    localStorage.setItem("command-center-astryx-theme", astryxTheme);
  }, [astryxTheme]);

  // Network online/offline detection
  useEffect(() => {
    const handleOnline = () => setIsOffline(false);
    const handleOffline = () => setIsOffline(true);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  // 1. Overview Query
  const { data: overviewData, isLoading: overviewLoading } = useQuery<{ ok: boolean; glance: GlanceData }>({
    queryKey: ["overview"],
    queryFn: async () => {
      const res = await fetch("/api/overview");
      if (!res.ok) throw new Error("Failed to load overview");
      return res.json();
    },
    refetchInterval: 30000,
  });

  // 2. Markets Query
  const {
    data: marketsData,
    isLoading: marketsLoading,
    isError: marketsError,
    error: marketsErr,
    refetch: refetchMarkets,
  } = useQuery<MarketsResponse>({
    queryKey: ["markets"],
    queryFn: async () => {
      const res = await fetch("/api/markets");
      if (!res.ok) throw new Error("Failed to load markets");
      return res.json();
    },
    refetchInterval: 60000,
  });

  // 3. AI Briefing Query
  const {
    data: briefingData,
    isLoading: briefingLoading,
    isError: briefingError,
    error: briefingErr,
    refetch: refetchBriefing,
  } = useQuery<AIBriefingResponse>({
    queryKey: ["briefing"],
    queryFn: async () => {
      const res = await fetch("/api/briefing");
      if (!res.ok) throw new Error("Failed to load briefing");
      return res.json();
    },
    refetchInterval: 180000,
  });

  // 4. Events Query
  const {
    data: eventsData,
    isLoading: eventsLoading,
    isError: eventsError,
    error: eventsErr,
    refetch: refetchEvents,
  } = useQuery<EventsResponse>({
    queryKey: ["events"],
    queryFn: async () => {
      const res = await fetch("/api/events");
      if (!res.ok) throw new Error("Failed to load events");
      return res.json();
    },
    refetchInterval: 180000,
  });

  // 5. Models Query
  const {
    data: modelsData,
    isLoading: modelsLoading,
    isError: modelsError,
    error: modelsErr,
    refetch: refetchModels,
  } = useQuery<ModelReleaseResponse>({
    queryKey: ["models"],
    queryFn: async () => {
      const res = await fetch("/api/models");
      if (!res.ok) throw new Error("Failed to load models");
      return res.json();
    },
    refetchInterval: 300000,
  });

  // 6. News Query
  const {
    data: newsData,
    isLoading: newsLoading,
    isError: newsError,
    error: newsErr,
    refetch: refetchNews,
  } = useQuery<AINewsResponse>({
    queryKey: ["news"],
    queryFn: async () => {
      const res = await fetch("/api/news");
      if (!res.ok) throw new Error("Failed to load news");
      return res.json();
    },
    refetchInterval: 120000,
  });

  // 7. F1 Query
  const {
    data: f1Data,
    isLoading: f1Loading,
    isError: f1Error,
    error: f1Err,
    refetch: refetchF1,
  } = useQuery<F1Response>({
    queryKey: ["f1"],
    queryFn: async () => {
      const res = await fetch("/api/f1");
      if (!res.ok) throw new Error("Failed to load F1");
      return res.json();
    },
    refetchInterval: 180000,
  });

  // 8. Matches Query
  const {
    data: matchesData,
    isLoading: matchesLoading,
    isError: matchesError,
    error: matchesErr,
    refetch: refetchMatches,
  } = useQuery<MatchesResponse>({
    queryKey: ["matches"],
    queryFn: async () => {
      const res = await fetch("/api/matches");
      if (!res.ok) throw new Error("Failed to load matches");
      return res.json();
    },
    refetchInterval: 30000,
  });

  // Manual refresh all trigger
  const handleRefreshAll = async () => {
    setIsRefreshing(true);
    await queryClient.invalidateQueries();
    setTimeout(() => setIsRefreshing(false), 800);
  };

  const freshestCheckedAt =
    marketsData?.checkedAt ||
    briefingData?.generatedAt ||
    matchesData?.checkedAt ||
    f1Data?.checkedAt;

  const liveMatchesCount = (matchesData?.matches || []).filter((m) => m.status === "live").length;

  return (
    <div className="min-h-screen bg-body text-text-primary pb-20 md:pb-12 transition-colors">
      {/* Offline Banner */}
      {isOffline && (
        <div
          role="status"
          className="bg-amber-500 text-stone-950 px-4 py-2 text-xs font-bold text-center flex items-center justify-center gap-2 shadow-sm"
        >
          <WifiOff className="w-4 h-4" />
          <span>Offline mode active · Displaying cached dashboard shell and last-known data.</span>
        </div>
      )}

      {/* Top Header */}
      <Header
        lastUpdated={freshestCheckedAt}
        onRefreshAll={handleRefreshAll}
        isRefreshing={isRefreshing}
        theme={theme}
        onToggleTheme={() => setTheme(theme === "light" ? "dark" : "light")}
        astryxTheme={astryxTheme}
        onChangeAstryxTheme={(t) => setAstryxTheme(t)}
        currency={currency}
        onToggleCurrency={() => setCurrency(currency === "INR" ? "USD" : "INR")}
      />

      {/* Navigation (Desktop Top Tabs & Mobile Bottom Bar) */}
      <Navigation
        currentTab={currentTab}
        onSelectTab={(tab) => setCurrentTab(tab)}
        matchesCount={matchesData?.matches?.length}
        liveMatchesCount={liveMatchesCount}
      />

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-6">
        {/* Today At A Glance Overview Card */}
        <TodayAtAGlance
          glance={overviewData?.glance}
          isLoading={overviewLoading}
          currency={currency}
          onNavigateTab={(tab) => setCurrentTab(tab)}
        />

        {/* Section View Routing */}
        {currentTab === "world" && (
          <WorldSection
            marketsData={marketsData}
            marketsLoading={marketsLoading}
            marketsError={marketsError}
            onRetryMarkets={() => refetchMarkets()}
            briefingData={briefingData}
            briefingLoading={briefingLoading}
            briefingError={briefingError}
            onRetryBriefing={() => refetchBriefing()}
            eventsData={eventsData}
            eventsLoading={eventsLoading}
            eventsError={eventsError}
            onRetryEvents={() => refetchEvents()}
            modelsData={modelsData}
            modelsLoading={modelsLoading}
            modelsError={modelsError}
            onRetryModels={() => refetchModels()}
            newsData={newsData}
            newsLoading={newsLoading}
            newsError={newsError}
            onRetryNews={() => refetchNews()}
            currency={currency}
          />
        )}

        {currentTab === "f1" && (
          <F1Section
            data={f1Data}
            isLoading={f1Loading}
            isError={f1Error}
            error={f1Err}
            onRetry={() => refetchF1()}
          />
        )}

        {currentTab === "matches" && (
          <MatchesSection
            data={matchesData}
            isLoading={matchesLoading}
            isError={matchesError}
            error={matchesErr}
            onRetry={() => refetchMatches()}
          />
        )}
      </main>
    </div>
  );
};
