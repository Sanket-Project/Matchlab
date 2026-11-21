import React, { useState } from "react";
import { Calendar, Clock, AlertTriangle, CheckCircle, ChevronDown, ChevronUp } from "lucide-react";
import { EventsResponse, ScheduledEvent } from "@shared/types.js";
import { formatToIST } from "@shared/formatters.js";
import { Skeleton } from "../common/Skeleton.js";
import { StaleBadge } from "../common/StaleBadge.js";
import { ErrorState } from "../common/ErrorState.js";

interface EventsModuleProps {
  data?: EventsResponse;
  isLoading: boolean;
  isError: boolean;
  error?: Error | null;
  onRetry: () => void;
}

export const EventsModule: React.FC<EventsModuleProps> = ({
  data,
  isLoading,
  isError,
  error,
  onRetry,
}) => {
  const [showPreview48h, setShowPreview48h] = useState<boolean>(true);

  if (isLoading) {
    return (
      <div className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
        <Skeleton className="h-6 w-48 mb-4" />
        <div className="space-y-3">
          <Skeleton className="h-16 rounded-lg" count={4} />
        </div>
      </div>
    );
  }

  if (isError || !data?.ok) {
    return (
      <div className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
        <h3 className="text-base font-bold text-text-primary mb-3 flex items-center gap-2">
          <Calendar className="w-4 h-4 text-accent" />
          What Happens Today (IST Schedule)
        </h3>
        <ErrorState
          title="Schedule Feed Unavailable"
          message={error?.message || "Failed to load scheduled financial and tech calendar events."}
          onRetry={onRetry}
        />
      </div>
    );
  }

  const todayEvents = data.todayEvents || [];
  const preview48hEvents = data.preview48hEvents || [];

  return (
    <section aria-labelledby="events-heading" className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4 border-b border-border/60 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 id="events-heading" className="text-base font-bold text-text-primary flex items-center gap-2">
              <Calendar className="w-4 h-4 text-accent" />
              What Happens Today (IST Timeline)
            </h3>
            {data.isStale && <StaleBadge />}
          </div>
          <p className="text-xs text-text-secondary mt-0.5">
            Confirmed financial releases, central bank events, AI checkpoints & sports fixtures
          </p>
        </div>

        <span className="text-xs font-semibold px-2.5 py-1 rounded bg-muted text-text-secondary border border-border">
          {todayEvents.length} Events Scheduled
        </span>
      </div>

      {/* Today Timeline */}
      <div className="relative pl-6 space-y-4 before:content-[''] before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-border">
        {todayEvents.map((evt) => (
          <div key={evt.id} className="relative group">
            {/* Timeline Dot */}
            <span
              className={`absolute -left-6 top-1.5 w-3 h-3 rounded-full border-2 border-surface ${
                evt.impact === "high"
                  ? "bg-accent ring-2 ring-accent/20"
                  : evt.impact === "medium"
                  ? "bg-amber-500"
                  : "bg-text-tertiary"
              }`}
            />

            <div className="p-3 rounded-lg border border-border/80 bg-elevated hover:border-border-focus transition-all">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-accent tabular-nums flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {evt.statusLabel}
                  </span>
                  <span className="text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded bg-muted text-text-secondary border border-border">
                    {evt.category}
                  </span>
                </div>

                <span
                  className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${
                    evt.impact === "high"
                      ? "bg-red-500/10 text-red-600 dark:text-red-400 border border-red-500/20"
                      : evt.impact === "medium"
                      ? "bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20"
                      : "bg-muted text-text-secondary border border-border"
                  }`}
                >
                  {evt.impact} Impact
                </span>
              </div>

              <h4 className="text-xs sm:text-sm font-bold text-text-primary">
                {evt.title}
              </h4>

              <p className="text-xs text-text-secondary mt-1">
                {evt.description}
              </p>

              <div className="mt-2 flex items-center justify-between text-[11px] text-text-tertiary">
                <span>Source: {evt.source}</span>
                <span>{evt.confirmed ? "Official Schedule" : "Time TBC"}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Next 48 Hours Preview Accordion */}
      <div className="mt-6 pt-4 border-t border-border/70">
        <button
          onClick={() => setShowPreview48h(!showPreview48h)}
          className="w-full flex items-center justify-between p-2 rounded-lg bg-muted/40 hover:bg-muted/70 transition-colors text-xs font-bold text-text-primary"
        >
          <div className="flex items-center gap-2">
            <span>Next 48 Hours Forward Outlook (Sun 22 - Mon 23 Nov)</span>
            <span className="text-[10px] bg-accent/10 text-accent font-semibold px-2 py-0.5 rounded">
              {preview48hEvents.length} Upcoming
            </span>
          </div>
          {showPreview48h ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>

        {showPreview48h && (
          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            {preview48hEvents.map((evt) => (
              <div
                key={evt.id}
                className="p-3 rounded-lg border border-border/70 bg-elevated/80 text-xs"
              >
                <div className="flex items-center justify-between gap-1 mb-1">
                  <span className="font-bold text-accent tabular-nums">{evt.statusLabel}</span>
                  <span className="text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded bg-muted text-text-tertiary">
                    {evt.category}
                  </span>
                </div>
                <h5 className="font-semibold text-text-primary">{evt.title}</h5>
                <p className="text-text-secondary text-[11px] mt-1">{evt.description}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
};
