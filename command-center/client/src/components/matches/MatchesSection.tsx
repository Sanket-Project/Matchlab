import React, { useState, useEffect } from "react";
import { Trophy, Star, ChevronDown, ChevronUp, Clock, AlertCircle } from "lucide-react";
import { MatchesResponse, SportsMatch } from "@shared/types.js";
import { formatToIST } from "@shared/formatters.js";
import { Skeleton } from "../common/Skeleton.js";
import { StaleBadge } from "../common/StaleBadge.js";
import { ErrorState } from "../common/ErrorState.js";

interface MatchesSectionProps {
  data?: MatchesResponse;
  isLoading: boolean;
  isError: boolean;
  error?: Error | null;
  onRetry: () => void;
}

export const MatchesSection: React.FC<MatchesSectionProps> = ({
  data,
  isLoading,
  isError,
  error,
  onRetry,
}) => {
  const [filterSport, setFilterSport] = useState<"all" | "football" | "cricket">("all");
  const [favoritesOnly, setFavoritesOnly] = useState<boolean>(false);
  const [expandedMatchId, setExpandedMatchId] = useState<string | null>(null);

  // Local storage for user favorites
  const [customFavorites, setCustomFavorites] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem("command-center-favorites");
      return saved ? JSON.parse(saved) : [];
    } catch (e) {
      return [];
    }
  });

  const toggleFavoriteTeam = (teamName: string) => {
    setCustomFavorites((prev) => {
      const updated = prev.includes(teamName) ? prev.filter((t) => t !== teamName) : [...prev, teamName];
      try {
        localStorage.setItem("command-center-favorites", JSON.stringify(updated));
      } catch (e) {}
      return updated;
    });
  };

  const isTeamFavorite = (teamName: string, isDefaultFav?: boolean) => {
    return isDefaultFav || customFavorites.includes(teamName);
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
          <Skeleton className="h-6 w-48 mb-4" />
          <div className="space-y-3">
            <Skeleton className="h-28 rounded-lg" count={4} />
          </div>
        </div>
      </div>
    );
  }

  if (isError || !data?.ok) {
    return (
      <div className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
        <h3 className="text-base font-bold text-text-primary mb-3 flex items-center gap-2">
          <Trophy className="w-4 h-4 text-accent" />
          Live Matches & Scores
        </h3>
        <ErrorState
          title="Sports Scoreboard Offline"
          message={error?.message || "Failed to retrieve real-time scoreboards from ESPN."}
          onRetry={onRetry}
        />
      </div>
    );
  }

  const allMatches = data.matches || [];

  const filteredMatches = allMatches.filter((m) => {
    if (filterSport !== "all" && m.sport !== filterSport) return false;
    if (favoritesOnly) {
      const homeFav = isTeamFavorite(m.homeTeam.name, m.homeTeam.isFavorite);
      const awayFav = isTeamFavorite(m.awayTeam.name, m.awayTeam.isFavorite);
      return homeFav || awayFav;
    }
    return true;
  });

  const liveMatches = filteredMatches.filter((m) => m.status === "live");
  const upcomingMatches = filteredMatches.filter((m) => m.status === "upcoming");
  const completedMatches = filteredMatches.filter((m) => m.status === "full_time");

  return (
    <div className="space-y-6">
      <section aria-labelledby="matches-heading" className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
        {/* Header & Controls */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4 border-b border-border/60 pb-3">
          <div>
            <div className="flex items-center gap-2">
              <h3 id="matches-heading" className="text-base font-bold text-text-primary flex items-center gap-2">
                <Trophy className="w-4 h-4 text-accent" />
                Live Sports Radar & Fixtures
              </h3>
              {data.isStale && <StaleBadge />}
              {data.isDemoData && (
                <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded bg-amber-500/10 text-warning border border-amber-500/30">
                  Demo Data Mode
                </span>
              )}
            </div>
            <p className="text-xs text-text-secondary mt-0.5">
              Premier League, Champions League, La Liga & International Cricket · Checked {formatToIST(data.checkedAt)}
            </p>
          </div>

          {/* Filters & Favorites Toggle */}
          <div className="flex flex-wrap items-center gap-1.5">
            {/* Favorites Toggle */}
            <button
              onClick={() => setFavoritesOnly(!favoritesOnly)}
              className={`touch-target-44 px-3 py-1 text-xs rounded-md font-medium transition-all flex items-center gap-1.5 ${
                favoritesOnly
                  ? "bg-amber-500/20 text-warning border border-amber-500/40 font-bold"
                  : "bg-muted/60 text-text-secondary hover:text-text-primary border border-border"
              }`}
            >
              <Star className={`w-3.5 h-3.5 ${favoritesOnly ? "fill-amber-500 text-amber-500" : ""}`} />
              <span>My Teams</span>
            </button>

            {/* Sport Filter */}
            <div className="flex items-center gap-1 bg-muted/60 p-1 rounded-lg border border-border/60">
              {(["all", "football", "cricket"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setFilterSport(s)}
                  className={`touch-target-44 px-2.5 py-1 text-xs rounded-md font-medium capitalize transition-all ${
                    filterSport === s
                      ? "bg-surface text-text-primary font-semibold shadow-xs"
                      : "text-text-secondary hover:text-text-primary"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Matches List */}
        {filteredMatches.length === 0 ? (
          <div className="p-8 text-center rounded-lg border border-border/60 bg-muted/20">
            <Trophy className="w-8 h-8 mx-auto text-text-tertiary mb-2" />
            <p className="text-sm font-semibold text-text-primary">No matches found matching active filters</p>
            <p className="text-xs text-text-secondary mt-1">Try toggling "My Teams" or switching to "All Sports".</p>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredMatches.map((m) => {
              const isExpanded = expandedMatchId === m.id;
              const isLive = m.status === "live";
              const homeIsFav = isTeamFavorite(m.homeTeam.name, m.homeTeam.isFavorite);
              const awayIsFav = isTeamFavorite(m.awayTeam.name, m.awayTeam.isFavorite);

              return (
                <article
                  key={m.id}
                  className={`p-3.5 rounded-lg border transition-all ${
                    isLive
                      ? "border-accent/40 bg-accent/5 shadow-xs"
                      : "border-border/80 bg-elevated hover:border-border-focus"
                  }`}
                >
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2 pb-2 border-b border-border/40">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-muted text-text-secondary border border-border">
                        {m.competitionName}
                      </span>
                      {isLive && (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-red-500 text-white flex items-center gap-1 animate-pulse">
                          <span className="w-1.5 h-1.5 rounded-full bg-white" />
                          LIVE
                        </span>
                      )}
                    </div>

                    <div className="text-xs text-text-tertiary flex items-center gap-2">
                      <span>{m.venue}</span>
                      <span>·</span>
                      <span className="font-medium text-text-primary tabular-nums">{m.kickoffTimeIST}</span>
                    </div>
                  </div>

                  {/* Teams & Scoreboard */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-center">
                    {/* Teams Rows */}
                    <div className="space-y-2">
                      {/* Home Team */}
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => toggleFavoriteTeam(m.homeTeam.name)}
                            className="p-1 text-text-tertiary hover:text-amber-500 transition-colors"
                            aria-label={`Favorite ${m.homeTeam.name}`}
                          >
                            <Star className={`w-3.5 h-3.5 ${homeIsFav ? "fill-amber-500 text-amber-500" : ""}`} />
                          </button>
                          {m.homeTeam.crest && (
                            <img src={m.homeTeam.crest} alt="" className="w-5 h-5 object-contain" />
                          )}
                          <span className={`text-sm ${homeIsFav ? "font-bold text-accent" : "font-semibold text-text-primary"}`}>
                            {m.homeTeam.name}
                          </span>
                        </div>
                        <span className="text-sm font-bold text-text-primary tabular-nums">
                          {m.homeTeam.score !== undefined ? m.homeTeam.score : "--"}
                        </span>
                      </div>

                      {/* Away Team */}
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => toggleFavoriteTeam(m.awayTeam.name)}
                            className="p-1 text-text-tertiary hover:text-amber-500 transition-colors"
                            aria-label={`Favorite ${m.awayTeam.name}`}
                          >
                            <Star className={`w-3.5 h-3.5 ${awayIsFav ? "fill-amber-500 text-amber-500" : ""}`} />
                          </button>
                          {m.awayTeam.crest && (
                            <img src={m.awayTeam.crest} alt="" className="w-5 h-5 object-contain" />
                          )}
                          <span className={`text-sm ${awayIsFav ? "font-bold text-accent" : "font-semibold text-text-primary"}`}>
                            {m.awayTeam.name}
                          </span>
                        </div>
                        <span className="text-sm font-bold text-text-primary tabular-nums">
                          {m.awayTeam.score !== undefined ? m.awayTeam.score : "--"}
                        </span>
                      </div>
                    </div>

                    {/* Status & Detail Toggle */}
                    <div className="flex items-center justify-between md:justify-end gap-3 pt-2 md:pt-0 border-t md:border-t-0 border-border/40">
                      <div className="text-right">
                        <div className="text-xs font-semibold text-text-primary">
                          {m.statusText}
                        </div>
                        {m.minuteOrSession && (
                          <div className="text-[11px] text-text-secondary tabular-nums">
                            {m.minuteOrSession}
                          </div>
                        )}
                      </div>

                      <button
                        onClick={() => setExpandedMatchId(isExpanded ? null : m.id)}
                        className="touch-target-44 px-3 py-1.5 rounded border border-border bg-surface hover:bg-muted text-xs font-medium text-text-secondary hover:text-text-primary flex items-center gap-1"
                        aria-expanded={isExpanded}
                      >
                        <span>{isExpanded ? "Less" : "Details"}</span>
                        {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                      </button>
                    </div>
                  </div>

                  {/* Expandable Match Details */}
                  {isExpanded && (
                    <div className="mt-3 pt-3 border-t border-border/60 text-xs bg-muted/20 p-3 rounded-lg space-y-2">
                      {m.details?.summary && (
                        <p className="text-text-secondary font-medium">
                          {m.details.summary}
                        </p>
                      )}
                      {m.details?.headToHead && (
                        <p className="text-[11px] text-text-tertiary">
                          <span className="font-semibold text-text-secondary">Head-to-head: </span>
                          {m.details.headToHead}
                        </p>
                      )}
                      {m.details?.events && m.details.events.length > 0 && (
                        <div className="space-y-1 pt-1">
                          <span className="font-semibold text-text-primary text-[11px] block">Key Match Events:</span>
                          {m.details.events.map((ev, i) => (
                            <div key={i} className="flex items-center gap-2 text-[11px] text-text-secondary">
                              <span className="font-bold text-accent tabular-nums">{ev.minute}</span>
                              <span className="capitalize">{ev.type}:</span>
                              <span className="font-medium text-text-primary">{ev.player}</span>
                              <span className="text-text-tertiary">({ev.team})</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
};
