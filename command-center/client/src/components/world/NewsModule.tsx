import React, { useState } from "react";
import { Newspaper, ExternalLink, Filter, Layers } from "lucide-react";
import { AINewsResponse, AINewsCard } from "@shared/types.js";
import { formatToIST } from "@shared/formatters.js";
import { Skeleton } from "../common/Skeleton.js";
import { StaleBadge } from "../common/StaleBadge.js";
import { ErrorState } from "../common/ErrorState.js";

interface NewsModuleProps {
  data?: AINewsResponse;
  isLoading: boolean;
  isError: boolean;
  error?: Error | null;
  onRetry: () => void;
}

export const NewsModule: React.FC<NewsModuleProps> = ({
  data,
  isLoading,
  isError,
  error,
  onRetry,
}) => {
  const [themeFilter, setThemeFilter] = useState<string>("all");

  if (isLoading) {
    return (
      <div className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
        <Skeleton className="h-6 w-48 mb-4" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <Skeleton className="h-32 rounded-lg" count={6} />
        </div>
      </div>
    );
  }

  if (isError || !data?.ok) {
    return (
      <div className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
        <h3 className="text-base font-bold text-text-primary mb-3 flex items-center gap-2">
          <Newspaper className="w-4 h-4 text-accent" />
          Latest AI News & Analysis
        </h3>
        <ErrorState
          title="News Feeds Offline"
          message={error?.message || "Failed to aggregate feeds from OpenAI, DeepMind, TechCrunch, and Hacker News."}
          onRetry={onRetry}
        />
      </div>
    );
  }

  const items = data.items || [];
  const themes = ["all", "Funding & Markets", "Frontier Models", "Policy & Safety", "Infrastructure & Compute", "Industry & Applications"];

  const displayed = themeFilter === "all" ? items : items.filter((n) => n.theme === themeFilter);

  return (
    <section aria-labelledby="ai-news-heading" className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4 border-b border-border/60 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 id="ai-news-heading" className="text-base font-bold text-text-primary flex items-center gap-2">
              <Newspaper className="w-4 h-4 text-accent" />
              Latest AI News (48h Feed)
            </h3>
            {data.isStale && <StaleBadge />}
          </div>
          <p className="text-xs text-text-secondary mt-0.5">
            Deduplicated by event across 8 global sources · Checked {formatToIST(data.checkedAt)}
          </p>
        </div>

        {/* Theme Filter Chips */}
        <div className="flex items-center gap-1 overflow-x-auto pb-1 max-w-full">
          {themes.map((theme) => (
            <button
              key={theme}
              onClick={() => setThemeFilter(theme)}
              className={`touch-target-44 px-2.5 py-1 text-xs rounded-md font-medium whitespace-nowrap transition-all ${
                themeFilter === theme
                  ? "bg-accent text-white font-semibold shadow-xs"
                  : "bg-muted/60 text-text-secondary hover:text-text-primary"
              }`}
            >
              {theme === "all" ? "All Themes" : theme}
            </button>
          ))}
        </div>
      </div>

      {/* News Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {displayed.map((card) => (
          <article
            key={card.id}
            className="p-3.5 rounded-lg border border-border/80 bg-elevated hover:border-border-focus transition-all flex flex-col justify-between"
          >
            <div>
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-muted text-text-secondary border border-border">
                  {card.theme}
                </span>

                {card.sourceCount > 1 && (
                  <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-accent/10 text-accent border border-accent/20">
                    {card.sourceCount} sources reporting
                  </span>
                )}
              </div>

              <h4 className="text-sm font-bold text-text-primary leading-snug">
                <a
                  href={card.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-accent hover:underline"
                >
                  {card.title}
                </a>
              </h4>

              {/* Why It Matters */}
              <div className="mt-2 p-2 rounded bg-muted/40 border-l-2 border-accent/80 text-[11px] leading-relaxed">
                <span className="font-semibold text-accent">So what: </span>
                <span className="text-text-primary">{card.whyItMatters}</span>
              </div>
            </div>

            {/* Footer */}
            <div className="mt-3 pt-2 border-t border-border/50 flex items-center justify-between text-[11px] text-text-tertiary">
              <span className="font-medium text-text-secondary">{card.source}</span>
              <div className="flex items-center gap-1.5">
                <span className="tabular-nums">{card.publishedRelative}</span>
                <a
                  href={card.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-text-tertiary hover:text-accent"
                  aria-label={`Open article: ${card.title}`}
                >
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
};
