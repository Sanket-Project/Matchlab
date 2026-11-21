import React, { useState } from "react";
import { TrendingUp, RefreshCw, AlertCircle, ShieldCheck } from "lucide-react";
import { MarketsResponse, MarketQuote } from "@shared/types.js";
import { formatPercentChange, formatINR, formatUSD, formatToIST } from "@shared/formatters.js";
import { Sparkline } from "../common/Sparkline.js";
import { Skeleton } from "../common/Skeleton.js";
import { StaleBadge } from "../common/StaleBadge.js";
import { ErrorState } from "../common/ErrorState.js";

interface MarketsModuleProps {
  data?: MarketsResponse;
  isLoading: boolean;
  isError: boolean;
  error?: Error | null;
  onRetry: () => void;
  currency: "INR" | "USD";
}

export const MarketsModule: React.FC<MarketsModuleProps> = ({
  data,
  isLoading,
  isError,
  error,
  onRetry,
  currency,
}) => {
  const [filter, setFilter] = useState<"all" | "indices" | "commodities">("all");

  if (isLoading) {
    return (
      <div className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <Skeleton className="h-6 w-36" />
          <Skeleton className="h-6 w-24" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <Skeleton className="h-28 rounded-lg" count={8} />
        </div>
      </div>
    );
  }

  if (isError || !data?.ok) {
    return (
      <div className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
        <h3 className="text-sm font-bold text-text-primary mb-3 flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-accent" />
          Global Markets & FX
        </h3>
        <ErrorState
          title="Markets Feed Offline"
          message={error?.message || "Failed to receive live market quotes from Yahoo Finance."}
          lastGoodAt={data?.lastGoodAt}
          onRetry={onRetry}
        />
      </div>
    );
  }

  const indices = data.indices || [];
  const commoditiesAndFx = data.commoditiesAndFx || [];

  const displayedQuotes: MarketQuote[] =
    filter === "indices"
      ? indices
      : filter === "commodities"
      ? commoditiesAndFx
      : [...indices, ...commoditiesAndFx];

  return (
    <section aria-labelledby="markets-heading" className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4 border-b border-border/60 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 id="markets-heading" className="text-base font-bold text-text-primary flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-accent" />
              Markets, Commodities & FX
            </h3>
            {data.isStale && <StaleBadge lastGoodAt={data.lastGoodAt} />}
          </div>
          <p className="text-xs text-text-secondary mt-0.5">
            Realtime & official closes from Yahoo Finance · Checked {formatToIST(data.checkedAt)}
          </p>
        </div>

        {/* Filter Chips */}
        <div className="flex items-center gap-1.5 self-start sm:self-auto bg-muted/60 p-1 rounded-lg border border-border/60">
          {(["all", "indices", "commodities"] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => setFilter(mode)}
              className={`touch-target-44 px-3 py-1 text-xs rounded-md font-medium capitalize transition-all ${
                filter === mode
                  ? "bg-surface text-text-primary font-semibold shadow-xs"
                  : "text-text-secondary hover:text-text-primary"
              }`}
            >
              {mode === "all" ? "All (14)" : mode === "indices" ? "Indices (8)" : "Commodities/FX (6)"}
            </button>
          ))}
        </div>
      </div>

      {/* Market Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {displayedQuotes.map((q) => {
          const change = formatPercentChange(q.changePct);
          const isUp = change.direction === "up";
          const isDown = change.direction === "down";

          // Currency display conversion
          const isINR = q.currency.toUpperCase() === "INR";
          const formattedPrice = isINR
            ? formatINR(q.price)
            : currency === "INR"
            ? `${formatUSD(q.price)} (~${formatINR(q.price * 92.67, { compact: true })})`
            : formatUSD(q.price);

          return (
            <div
              key={q.symbol}
              className="p-3.5 rounded-lg border border-border/70 bg-elevated hover:border-border-focus transition-all flex flex-col justify-between"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-bold text-text-primary">{q.name}</span>
                    <span className="text-[10px] text-text-tertiary uppercase">{q.exchange}</span>
                  </div>
                  <span className="text-[10px] text-text-secondary">{q.symbol}</span>
                </div>

                {/* Market Status Pill */}
                <span
                  className={`text-[9px] uppercase font-bold px-1.5 py-0.5 rounded tracking-wide ${
                    q.marketStatus === "open"
                      ? "bg-positive/10 text-positive border border-positive/30"
                      : q.marketStatus === "pre" || q.marketStatus === "post"
                      ? "bg-amber-500/10 text-warning border border-amber-500/30"
                      : "bg-muted text-text-tertiary border border-border"
                  }`}
                >
                  {q.marketStatus}
                </span>
              </div>

              {/* Price & Change */}
              <div className="my-2">
                <div className="text-base sm:text-lg font-bold text-text-primary tabular-nums">
                  {formattedPrice}
                </div>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span
                    className={`text-xs font-semibold tabular-nums flex items-center gap-0.5 ${
                      isUp ? "text-positive" : isDown ? "text-negative" : "text-text-secondary"
                    }`}
                  >
                    <span>{change.arrow}</span>
                    <span>{change.text}</span>
                  </span>
                  <span className="text-[11px] text-text-tertiary tabular-nums">
                    ({q.change > 0 ? `+${q.change}` : q.change})
                  </span>
                </div>
              </div>

              {/* Sparkline & As Of */}
              <div className="pt-2 border-t border-border/50 flex items-center justify-between">
                <span className="text-[10px] text-text-tertiary tabular-nums">
                  {formatToIST(q.asOf, { timeOnly: true })}
                </span>
                <Sparkline data={q.series} width={90} height={24} isPositive={isUp} />
              </div>
            </div>
          );
        })}
      </div>

      {/* Market Note */}
      <div className="mt-3 text-[11px] text-text-tertiary flex items-center justify-between">
        <span>Weekend rule: Saturday/Sunday marked as CLOSED for equities. Commodities & Crypto trade per schedule.</span>
        <span className="hidden sm:inline">Source: Yahoo Finance Chart API</span>
      </div>
    </section>
  );
};
