import React, { useState, useEffect } from "react";
import { RefreshCw, Sun, Moon, Palette } from "lucide-react";
import { formatToIST, formatRelativeTime } from "@shared/formatters.js";

interface HeaderProps {
  lastUpdated?: string;
  onRefreshAll: () => void;
  isRefreshing: boolean;
  theme: "light" | "dark";
  onToggleTheme: () => void;
  astryxTheme: "butter" | "neutral" | "chocolate";
  onChangeAstryxTheme: (theme: "butter" | "neutral" | "chocolate") => void;
  currency: "INR" | "USD";
  onToggleCurrency: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  lastUpdated,
  onRefreshAll,
  isRefreshing,
  theme,
  onToggleTheme,
  astryxTheme,
  onChangeAstryxTheme,
  currency,
  onToggleCurrency,
}) => {
  const [currentISTTime, setCurrentISTTime] = useState<string>(formatToIST(new Date(), { includeSeconds: true }));

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentISTTime(formatToIST(new Date(), { includeSeconds: true }));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <header className="border-b border-border bg-surface sticky top-0 z-40 px-4 py-3 sm:px-6 shadow-sm">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-3">
        {/* Brand & Live IST Clock */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-md bg-accent flex items-center justify-center text-white font-bold text-base shadow-sm">
              C
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base sm:text-lg font-bold tracking-tight text-text-primary">
                  Command Center
                </h1>
                <span className="text-[10px] uppercase font-semibold tracking-wider px-1.5 py-0.5 rounded bg-muted text-text-secondary border border-border">
                  Founder Ed.
                </span>
              </div>
              <p className="text-xs text-text-secondary flex items-center gap-1.5 tabular-nums">
                <span className="inline-block w-2 h-2 rounded-full bg-positive" />
                <span className="font-medium text-text-primary">{currentISTTime}</span>
              </p>
            </div>
          </div>

          {/* Mobile Fast Action Buttons */}
          <div className="flex md:hidden items-center gap-1">
            <button
              onClick={onRefreshAll}
              disabled={isRefreshing}
              className="touch-target-44 p-2 rounded text-text-secondary hover:text-text-primary active:bg-muted"
              aria-label="Refresh dashboard data"
            >
              <RefreshCw className={`w-4 h-4 ${isRefreshing ? "animate-spin text-accent" : ""}`} />
            </button>
            <button
              onClick={onToggleTheme}
              className="touch-target-44 p-2 rounded text-text-secondary hover:text-text-primary active:bg-muted"
              aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
            >
              {theme === "light" ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* Global Controls & Freshness Status */}
        <div className="flex items-center justify-between md:justify-end gap-2.5 sm:gap-4 text-xs">
          {/* Last Updated Pill */}
          <div className="text-text-secondary flex items-center gap-1.5 bg-muted/60 px-2.5 py-1.5 rounded border border-border/80">
            <span className="text-text-tertiary">Data age:</span>
            <span className="font-medium text-text-primary tabular-nums">
              {lastUpdated ? formatRelativeTime(lastUpdated) : "just now"}
            </span>
          </div>

          {/* Currency Toggle */}
          <button
            onClick={onToggleCurrency}
            className="touch-target-44 px-3 py-1 rounded border border-border bg-muted/40 hover:bg-muted active:scale-95 transition-all text-text-primary font-medium flex items-center gap-1"
            title="Toggle default currency view"
          >
            <span className="text-text-tertiary">Curr:</span>
            <span className="font-bold text-accent">{currency}</span>
          </button>

          {/* Theme Selector (Astryx Theme) */}
          <div className="hidden sm:flex items-center gap-1 bg-muted/40 p-1 rounded border border-border">
            <Palette className="w-3.5 h-3.5 text-text-tertiary ml-1" />
            {(["butter", "neutral"] as const).map((t) => (
              <button
                key={t}
                onClick={() => onChangeAstryxTheme(t)}
                className={`px-2 py-1 rounded text-xs capitalize transition-colors ${
                  astryxTheme === t
                    ? "bg-surface font-semibold text-text-primary shadow-xs"
                    : "text-text-secondary hover:text-text-primary"
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          {/* Desktop Light/Dark and Manual Refresh */}
          <div className="hidden md:flex items-center gap-1.5">
            <button
              onClick={onToggleTheme}
              className="touch-target-44 px-2.5 py-1.5 rounded border border-border bg-surface hover:bg-muted text-text-secondary hover:text-text-primary transition-colors flex items-center gap-1"
              aria-label="Toggle dark mode"
            >
              {theme === "light" ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />}
            </button>

            <button
              onClick={onRefreshAll}
              disabled={isRefreshing}
              className="touch-target-44 px-3 py-1.5 rounded bg-accent text-white font-medium hover:opacity-90 active:scale-95 transition-all flex items-center gap-1.5 shadow-sm"
              aria-label="Refresh all data"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin" : ""}`} />
              <span>{isRefreshing ? "Updating..." : "Refresh"}</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};
