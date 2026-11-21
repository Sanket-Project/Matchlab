import React, { useState } from "react";
import { Layers, ExternalLink, Zap, Clock, DollarSign } from "lucide-react";
import { ModelReleaseResponse, ModelRelease } from "@shared/types.js";
import { formatToIST, formatRelativeTime } from "@shared/formatters.js";
import { Skeleton } from "../common/Skeleton.js";
import { StaleBadge } from "../common/StaleBadge.js";
import { ErrorState } from "../common/ErrorState.js";

interface ModelsModuleProps {
  data?: ModelReleaseResponse;
  isLoading: boolean;
  isError: boolean;
  error?: Error | null;
  onRetry: () => void;
}

export const ModelsModule: React.FC<ModelsModuleProps> = ({
  data,
  isLoading,
  isError,
  error,
  onRetry,
}) => {
  const [labFilter, setLabFilter] = useState<string>("all");

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
          <Layers className="w-4 h-4 text-accent" />
          Newer Model Releases
        </h3>
        <ErrorState
          title="Model Registry Offline"
          message={error?.message || "Failed to fetch official model catalogue from OpenRouter."}
          onRetry={onRetry}
        />
      </div>
    );
  }

  const items = data.items || [];
  const uniqueLabs = ["all", ...Array.from(new Set(items.map((m) => m.lab)))];

  const displayed = labFilter === "all" ? items : items.filter((m) => m.lab === labFilter);

  return (
    <section aria-labelledby="models-heading" className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4 border-b border-border/60 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 id="models-heading" className="text-base font-bold text-text-primary flex items-center gap-2">
              <Layers className="w-4 h-4 text-accent" />
              Newer Model Releases
            </h3>
            {data.isStale && <StaleBadge />}
          </div>
          <p className="text-xs text-text-secondary mt-0.5">
            Reverse-chronological verified catalogue from official registries · Checked {formatToIST(data.checkedAt)}
          </p>
        </div>

        {/* Lab Filter */}
        <div className="flex items-center gap-1 overflow-x-auto pb-1 max-w-full">
          {uniqueLabs.slice(0, 6).map((lab) => (
            <button
              key={lab}
              onClick={() => setLabFilter(lab)}
              className={`touch-target-44 px-2.5 py-1 text-xs rounded-md font-medium whitespace-nowrap capitalize transition-all ${
                labFilter === lab
                  ? "bg-accent text-white font-semibold shadow-xs"
                  : "bg-muted/60 text-text-secondary hover:text-text-primary"
              }`}
            >
              {lab}
            </button>
          ))}
        </div>
      </div>

      {/* Models Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {displayed.map((m) => (
          <div
            key={m.id}
            className="p-3.5 rounded-lg border border-border/80 bg-elevated hover:border-border-focus transition-all flex flex-col justify-between"
          >
            <div>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-accent">
                    {m.lab}
                  </span>
                  <h4 className="text-sm font-bold text-text-primary leading-tight mt-0.5">
                    {m.name}
                  </h4>
                </div>

                {/* Status Badge */}
                <span
                  className={`text-[9px] uppercase font-bold px-1.5 py-0.5 rounded tracking-wide ${
                    m.releaseStatus === "released"
                      ? "bg-positive/10 text-positive border border-positive/30"
                      : m.releaseStatus === "preview"
                      ? "bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/30"
                      : "bg-amber-500/10 text-warning border border-amber-500/30"
                  }`}
                >
                  {m.releaseStatus}
                </span>
              </div>

              <p className="text-xs text-text-secondary mt-2 line-clamp-2 leading-relaxed">
                {m.blurb}
              </p>

              {/* Context and Pricing Specs */}
              <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] bg-muted/30 p-2 rounded border border-border/50 tabular-nums">
                <div>
                  <span className="text-text-tertiary block">Context</span>
                  <span className="font-semibold text-text-primary">
                    {m.contextWindow ? `${Math.round(m.contextWindow / 1024)}k tokens` : "N/A"}
                  </span>
                </div>
                <div>
                  <span className="text-text-tertiary block">Pricing (In/Out)</span>
                  <span className="font-semibold text-text-primary">
                    {m.isFree ? "Free tier" : `$${m.priceIn} / $${m.priceOut}`}
                  </span>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="mt-3 pt-2 border-t border-border/50 flex items-center justify-between text-[11px] text-text-tertiary">
              <span className="tabular-nums">
                Listed {formatRelativeTime(m.releasedAt)}
              </span>
              <a
                href={m.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-accent font-medium hover:underline"
              >
                <span>Specs & Docs</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
};
