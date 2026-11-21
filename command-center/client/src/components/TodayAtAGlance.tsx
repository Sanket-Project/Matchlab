import React from "react";
import { TrendingUp, TrendingDown, Cpu, Flag, Trophy, Calendar, ArrowRight } from "lucide-react";
import { TodayAtAGlance as GlanceData } from "@shared/types.js";
import { formatPercentChange, formatINR, formatUSD } from "@shared/formatters.js";
import { Skeleton } from "./common/Skeleton.js";

interface TodayAtAGlanceProps {
  glance?: GlanceData | null;
  isLoading: boolean;
  currency: "INR" | "USD";
  onNavigateTab: (tab: "world" | "f1" | "matches") => void;
}

export const TodayAtAGlance: React.FC<TodayAtAGlanceProps> = ({
  glance,
  isLoading,
  currency,
  onNavigateTab,
}) => {
  if (isLoading) {
    return (
      <section className="mb-6 rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
        <Skeleton className="h-6 w-48 mb-4" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <Skeleton className="h-24 rounded-lg" count={4} />
        </div>
      </section>
    );
  }

  if (!glance) return null;

  const marketChange = glance.marketLeader ? formatPercentChange(glance.marketLeader.changePct) : null;

  return (
    <section aria-labelledby="today-glance-heading" className="mb-6 rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
      <div className="flex items-center justify-between mb-3 border-b border-border/60 pb-2">
        <div className="flex items-center gap-2">
          <h2 id="today-glance-heading" className="text-sm font-bold uppercase tracking-wider text-text-primary">
            Today At A Glance
          </h2>
          <span className="text-[10px] bg-accent/10 text-accent font-semibold px-2 py-0.5 rounded">
            Founder Summary
          </span>
        </div>
        <span className="text-xs text-text-secondary hidden sm:inline">
          High-conviction signals across your three pillars
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {/* 1. Market Pulse */}
        <div
          onClick={() => onNavigateTab("world")}
          className="p-3.5 rounded-lg border border-border/80 bg-muted/30 hover:bg-muted/70 active:scale-[0.99] transition-all cursor-pointer flex flex-col justify-between"
        >
          <div className="flex items-center justify-between text-xs text-text-secondary mb-1">
            <span className="flex items-center gap-1 font-semibold uppercase text-[11px]">
              <TrendingUp className="w-3.5 h-3.5 text-accent" />
              Markets
            </span>
            <span className="text-text-tertiary">Top Mover</span>
          </div>

          {glance.marketLeader ? (
            <div>
              <div className="flex items-baseline justify-between">
                <span className="text-sm font-bold text-text-primary">{glance.marketLeader.name}</span>
                <span
                  className={`text-xs font-semibold tabular-nums flex items-center gap-0.5 ${
                    marketChange?.direction === "up" ? "text-positive" : "text-negative"
                  }`}
                >
                  {marketChange?.arrow} {marketChange?.text}
                </span>
              </div>
              <div className="text-xs text-text-secondary mt-1 tabular-nums">
                {currency === "INR" && glance.marketLeader.currency === "INR"
                  ? formatINR(glance.marketLeader.price)
                  : formatUSD(glance.marketLeader.price)}
              </div>
            </div>
          ) : (
            <p className="text-xs text-text-tertiary">Markets closed for weekend.</p>
          )}

          <div className="mt-2 pt-2 border-t border-border/50 flex items-center justify-between text-[11px] text-accent font-medium">
            <span>View 14 Tickers</span>
            <ArrowRight className="w-3 h-3" />
          </div>
        </div>

        {/* 2. Top AI Headline */}
        <div
          onClick={() => onNavigateTab("world")}
          className="p-3.5 rounded-lg border border-border/80 bg-muted/30 hover:bg-muted/70 active:scale-[0.99] transition-all cursor-pointer flex flex-col justify-between"
        >
          <div className="flex items-center justify-between text-xs text-text-secondary mb-1">
            <span className="flex items-center gap-1 font-semibold uppercase text-[11px]">
              <Cpu className="w-3.5 h-3.5 text-accent" />
              AI Intelligence
            </span>
            <span className="text-text-tertiary">{glance.topHeadline?.source || "Frontier"}</span>
          </div>

          <div>
            <h4 className="text-xs font-semibold text-text-primary line-clamp-2 leading-snug">
              {glance.topHeadline?.title || "Monitoring frontier model releases & infrastructure"}
            </h4>
            <p className="text-[11px] text-text-secondary mt-1 line-clamp-1 italic">
              {glance.topHeadline?.whyItMatters || "Strategic ecosystem development"}
            </p>
          </div>

          <div className="mt-2 pt-2 border-t border-border/50 flex items-center justify-between text-[11px] text-accent font-medium">
            <span>Read 8 Bullets</span>
            <ArrowRight className="w-3 h-3" />
          </div>
        </div>

        {/* 3. F1 Next Session */}
        <div
          onClick={() => onNavigateTab("f1")}
          className="p-3.5 rounded-lg border border-border/80 bg-muted/30 hover:bg-muted/70 active:scale-[0.99] transition-all cursor-pointer flex flex-col justify-between"
        >
          <div className="flex items-center justify-between text-xs text-text-secondary mb-1">
            <span className="flex items-center gap-1 font-semibold uppercase text-[11px]">
              <Flag className="w-3.5 h-3.5 text-accent" />
              Formula 1
            </span>
            <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-accent/10 text-accent">
              Round 21
            </span>
          </div>

          <div>
            <div className="text-xs font-bold text-text-primary">
              {glance.nextF1Session?.sessionName || "Las Vegas Grand Prix"}
            </div>
            <div className="text-xs text-text-secondary mt-1 flex items-center gap-1.5">
              <span className="font-semibold text-text-primary">
                {glance.nextF1Session?.dateIST || "22 Nov, 09:30 AM IST"}
              </span>
            </div>
            <span className="text-[11px] font-medium text-warning tabular-nums">
              Starts {glance.nextF1Session?.countdown || "tomorrow morning"}
            </span>
          </div>

          <div className="mt-2 pt-2 border-t border-border/50 flex items-center justify-between text-[11px] text-accent font-medium">
            <span>Standings & Podium</span>
            <ArrowRight className="w-3 h-3" />
          </div>
        </div>

        {/* 4. Matches Next/Live */}
        <div
          onClick={() => onNavigateTab("matches")}
          className="p-3.5 rounded-lg border border-border/80 bg-muted/30 hover:bg-muted/70 active:scale-[0.99] transition-all cursor-pointer flex flex-col justify-between"
        >
          <div className="flex items-center justify-between text-xs text-text-secondary mb-1">
            <span className="flex items-center gap-1 font-semibold uppercase text-[11px]">
              <Trophy className="w-3.5 h-3.5 text-accent" />
              Sports Radar
            </span>
            {glance.nextMatch?.isLive && (
              <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-red-500 text-white animate-pulse">
                LIVE
              </span>
            )}
          </div>

          <div>
            <div className="text-xs font-bold text-text-primary line-clamp-1">
              {glance.nextMatch?.matchName || "Man City vs Fulham / India vs NZ"}
            </div>
            <div className="text-[11px] text-text-secondary mt-1">
              {glance.nextMatch?.competition || "Premier League & International Cricket"}
            </div>
            <div className="text-[11px] text-text-tertiary tabular-nums mt-0.5">
              {glance.nextMatch?.kickoffTimeIST || "Today"}
            </div>
          </div>

          <div className="mt-2 pt-2 border-t border-border/50 flex items-center justify-between text-[11px] text-accent font-medium">
            <span>Scoreboard & Odds</span>
            <ArrowRight className="w-3 h-3" />
          </div>
        </div>
      </div>
    </section>
  );
};
