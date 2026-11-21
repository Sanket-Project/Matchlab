import React, { useState } from "react";
import { Flag, Trophy, Clock, ExternalLink, Calendar, Award, ChevronRight } from "lucide-react";
import { F1Response } from "@shared/types.js";
import { formatToIST } from "@shared/formatters.js";
import { Skeleton } from "../common/Skeleton.js";
import { StaleBadge } from "../common/StaleBadge.js";
import { ErrorState } from "../common/ErrorState.js";

interface F1SectionProps {
  data?: F1Response;
  isLoading: boolean;
  isError: boolean;
  error?: Error | null;
  onRetry: () => void;
}

export const F1Section: React.FC<F1SectionProps> = ({
  data,
  isLoading,
  isError,
  error,
  onRetry,
}) => {
  const [activeTab, setActiveTab] = useState<"drivers" | "constructors" | "calendar">("drivers");

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
          <Skeleton className="h-6 w-48 mb-4" />
          <Skeleton className="h-24 w-full rounded-lg" />
        </div>
        <div className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
          <Skeleton className="h-48 w-full rounded-lg" />
        </div>
      </div>
    );
  }

  if (isError || !data?.ok) {
    return (
      <div className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
        <h3 className="text-base font-bold text-text-primary mb-3 flex items-center gap-2">
          <Flag className="w-4 h-4 text-accent" />
          Formula 1 World Championship
        </h3>
        <ErrorState
          title="F1 Jolpica Telemetry Offline"
          message={error?.message || "Failed to retrieve live standings and session data from api.jolpi.ca."}
          onRetry={onRetry}
        />
      </div>
    );
  }

  const { session, driverStandings, constructorStandings, raceCalendar, lastRaceResult } = data;

  return (
    <div className="space-y-6">
      {/* 1. Live / Next Session Telemetry Banner */}
      <section aria-labelledby="f1-session-heading" className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm relative overflow-hidden">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3 border-b border-border/60 pb-3">
          <div className="flex items-center gap-2">
            <h3 id="f1-session-heading" className="text-base font-bold text-text-primary flex items-center gap-2">
              <Flag className="w-4 h-4 text-accent" />
              Formula 1 Track Telemetry
            </h3>
            {session.isLive ? (
              <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-red-500 text-white flex items-center gap-1 animate-pulse">
                <span className="w-1.5 h-1.5 rounded-full bg-white" />
                LIVE SESSION
              </span>
            ) : (
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-muted text-text-secondary border border-border">
                Track Status: Clear
              </span>
            )}
            {data.isStale && <StaleBadge />}
          </div>

          <div className="text-xs text-text-secondary">
            Official Series: 2026 FIA Formula One World Championship
          </div>
        </div>

        {/* Hero Card for Next / Live Session */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-muted/30 p-4 rounded-lg border border-border/70">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-wider text-accent mb-1">
              Next Up · Round 21
            </div>
            <h4 className="text-lg sm:text-xl font-bold text-text-primary">
              {session.nextSessionName}
            </h4>
            <div className="text-xs text-text-secondary mt-1 flex items-center gap-2">
              <Clock className="w-3.5 h-3.5 text-text-tertiary" />
              <span className="font-semibold text-text-primary">{session.nextSessionDateIST}</span>
            </div>
            <div className="mt-2 inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-accent/10 text-accent font-bold text-xs tabular-nums">
              <span>Countdown:</span>
              <span>{session.nextSessionCountdown}</span>
            </div>
          </div>

          {/* Last Completed Race Box */}
          <div className="border-t md:border-t-0 md:border-l border-border/70 pt-3 md:pt-0 md:pl-4 flex flex-col justify-between">
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wider text-text-tertiary mb-1">
                Last Grand Prix Result
              </div>
              <h5 className="text-sm font-bold text-text-primary">
                {lastRaceResult.raceName}
              </h5>
              <p className="text-xs text-text-secondary mt-0.5">
                {lastRaceResult.circuit} · {lastRaceResult.dateIST}
              </p>
              <div className="mt-2 text-xs text-text-secondary">
                <span className="font-semibold text-text-primary">Podium: </span>
                {lastRaceResult.podium.map((p, i) => (
                  <span key={i} className="inline-block mr-2 font-medium">
                    {p.position}. {p.driver} ({p.team})
                  </span>
                ))}
              </div>
              {lastRaceResult.fastestLap && (
                <div className="text-[11px] text-text-tertiary mt-1">
                  Fastest Lap: {lastRaceResult.fastestLap.driver} ({lastRaceResult.fastestLap.time})
                </div>
              )}
            </div>

            <div className="mt-3">
              <a
                href={lastRaceResult.fullClassificationUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-accent font-medium hover:underline inline-flex items-center gap-1"
              >
                <span>Full FIA classification & timings</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* 2. Standings & Calendar Tabs */}
      <section aria-labelledby="f1-standings-heading" className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4 border-b border-border/60 pb-3">
          <div className="flex items-center gap-2">
            <h3 id="f1-standings-heading" className="text-base font-bold text-text-primary flex items-center gap-2">
              <Trophy className="w-4 h-4 text-accent" />
              Championship Standings & Schedule
            </h3>
          </div>

          <div className="flex items-center gap-1.5 self-start sm:self-auto bg-muted/60 p-1 rounded-lg border border-border/60">
            {(["drivers", "constructors", "calendar"] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`touch-target-44 px-3 py-1 text-xs rounded-md font-medium capitalize transition-all ${
                  activeTab === tab
                    ? "bg-surface text-text-primary font-semibold shadow-xs"
                    : "text-text-secondary hover:text-text-primary"
                }`}
              >
                {tab === "drivers"
                  ? "Drivers"
                  : tab === "constructors"
                  ? "Constructors"
                  : "2026 Calendar (23)"}
              </button>
            ))}
          </div>
        </div>

        {/* Tab Content: Drivers */}
        {activeTab === "drivers" && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs tabular-nums">
              <thead>
                <tr className="border-b border-border/70 text-text-tertiary uppercase text-[10px]">
                  <th className="py-2.5 px-3">Pos</th>
                  <th className="py-2.5 px-3">Driver</th>
                  <th className="py-2.5 px-3">Constructor</th>
                  <th className="py-2.5 px-3 text-right">Pts</th>
                  <th className="py-2.5 px-3 text-right">Gap</th>
                  <th className="py-2.5 px-3 text-right">Wins</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {driverStandings.map((d) => (
                  <tr key={d.driverCode} className="hover:bg-muted/40 transition-colors">
                    <td className="py-2.5 px-3 font-bold text-text-primary">{d.position}</td>
                    <td className="py-2.5 px-3 font-bold text-text-primary flex items-center gap-2">
                      <span
                        className="w-1.5 h-4 rounded-full inline-block shrink-0"
                        style={{ backgroundColor: d.teamColor }}
                      />
                      <span>{d.driverName}</span>
                      <span className="text-[10px] text-text-tertiary">{d.driverCode}</span>
                    </td>
                    <td className="py-2.5 px-3 text-text-secondary">{d.constructorName}</td>
                    <td className="py-2.5 px-3 text-right font-bold text-text-primary">{d.points}</td>
                    <td className="py-2.5 px-3 text-right text-text-tertiary">
                      {d.gapToLeader === 0 ? "LEADER" : `-${d.gapToLeader}`}
                    </td>
                    <td className="py-2.5 px-3 text-right text-text-secondary">{d.wins}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Tab Content: Constructors */}
        {activeTab === "constructors" && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs tabular-nums">
              <thead>
                <tr className="border-b border-border/70 text-text-tertiary uppercase text-[10px]">
                  <th className="py-2.5 px-3">Pos</th>
                  <th className="py-2.5 px-3">Constructor</th>
                  <th className="py-2.5 px-3 text-right">Points</th>
                  <th className="py-2.5 px-3 text-right">Gap to Leader</th>
                  <th className="py-2.5 px-3 text-right">Wins</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {constructorStandings.map((c) => (
                  <tr key={c.constructorName} className="hover:bg-muted/40 transition-colors">
                    <td className="py-2.5 px-3 font-bold text-text-primary">{c.position}</td>
                    <td className="py-2.5 px-3 font-bold text-text-primary flex items-center gap-2">
                      <span
                        className="w-1.5 h-4 rounded-full inline-block shrink-0"
                        style={{ backgroundColor: c.teamColor }}
                      />
                      <span>{c.constructorName}</span>
                    </td>
                    <td className="py-2.5 px-3 text-right font-bold text-text-primary">{c.points}</td>
                    <td className="py-2.5 px-3 text-right text-text-tertiary">
                      {c.gapToLeader === 0 ? "LEADER" : `-${c.gapToLeader}`}
                    </td>
                    <td className="py-2.5 px-3 text-right text-text-secondary">{c.wins}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Tab Content: Calendar */}
        {activeTab === "calendar" && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
            {raceCalendar.map((r) => (
              <div
                key={r.round}
                className={`p-3 rounded-lg border text-xs flex flex-col justify-between ${
                  r.isCompleted
                    ? "border-border/60 bg-muted/20 text-text-secondary"
                    : "border-border/90 bg-elevated text-text-primary shadow-xs"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between gap-1 mb-1">
                    <span className="font-bold text-accent text-[11px]">Round {r.round}</span>
                    <span
                      className={`text-[9px] font-bold uppercase px-1.5 py-0.2 rounded ${
                        r.isCompleted
                          ? "bg-muted text-text-tertiary"
                          : "bg-positive/10 text-positive border border-positive/30"
                      }`}
                    >
                      {r.isCompleted ? "Completed" : "Upcoming"}
                    </span>
                  </div>
                  <h4 className="font-bold text-text-primary">{r.raceName}</h4>
                  <p className="text-[11px] text-text-secondary mt-0.5">
                    {r.circuitName}, {r.country}
                  </p>
                </div>

                <div className="mt-2 pt-2 border-t border-border/40 flex items-center justify-between text-[11px] text-text-tertiary">
                  <span className="tabular-nums">{r.dateIST}</span>
                  {r.isSprint && (
                    <span className="font-bold text-warning text-[10px] uppercase">Sprint</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
};
