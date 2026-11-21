import React from "react";
import { Cpu, ExternalLink, ShieldCheck, CheckCircle2 } from "lucide-react";
import { AIBriefingResponse } from "@shared/types.js";
import { formatToIST } from "@shared/formatters.js";
import { Skeleton } from "../common/Skeleton.js";
import { StaleBadge } from "../common/StaleBadge.js";
import { ErrorState } from "../common/ErrorState.js";

interface AIBriefingModuleProps {
  data?: AIBriefingResponse;
  isLoading: boolean;
  isError: boolean;
  error?: Error | null;
  onRetry: () => void;
}

export const AIBriefingModule: React.FC<AIBriefingModuleProps> = ({
  data,
  isLoading,
  isError,
  error,
  onRetry,
}) => {
  if (isLoading) {
    return (
      <div className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
        <Skeleton className="h-6 w-48 mb-4" />
        <div className="space-y-3">
          <Skeleton className="h-20 rounded-lg" count={5} />
        </div>
      </div>
    );
  }

  if (isError || !data?.ok) {
    return (
      <div className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
        <h3 className="text-base font-bold text-text-primary mb-3 flex items-center gap-2">
          <Cpu className="w-4 h-4 text-accent" />
          AI Briefing (Daily Synthesis)
        </h3>
        <ErrorState
          title="AI Synthesis Pipeline Unavailable"
          message={error?.message || "Could not generate or retrieve verified daily briefing bullets."}
          lastGoodAt={data?.lastGoodAt}
          onRetry={onRetry}
        />
      </div>
    );
  }

  const items = data.items || [];

  return (
    <section aria-labelledby="ai-briefing-heading" className="rounded-xl border border-border bg-surface p-4 sm:p-5 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4 border-b border-border/60 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 id="ai-briefing-heading" className="text-base font-bold text-text-primary flex items-center gap-2">
              <Cpu className="w-4 h-4 text-accent" />
              Executive AI Briefing
            </h3>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-positive/10 text-positive border border-positive/30 flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" />
              Multi-Source Grounded
            </span>
            {data.isStale && <StaleBadge lastGoodAt={data.lastGoodAt} />}
          </div>
          <p className="text-xs text-text-secondary mt-0.5">
            5 to 8 overnight & daily developments synthesized and verified · Generated {formatToIST(data.generatedAt)}
          </p>
        </div>

        <div className="text-[11px] text-text-tertiary">
          Rule-enforced: &le;40 words · No hallucinations
        </div>
      </div>

      {/* Bullets List */}
      <div className="space-y-3">
        {items.map((bullet, idx) => (
          <article
            key={bullet.id || idx}
            className="p-3.5 rounded-lg border border-border/80 bg-elevated hover:border-border-focus transition-all"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1">
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-muted text-text-secondary border border-border">
                    {bullet.category}
                  </span>
                  <span
                    className={`text-[10px] font-semibold px-2 py-0.5 rounded flex items-center gap-1 ${
                      bullet.confidence === "confirmed"
                        ? "bg-positive/10 text-positive"
                        : "bg-amber-500/10 text-warning"
                    }`}
                  >
                    <ShieldCheck className="w-3 h-3" />
                    {bullet.confidence === "confirmed" ? "Confirmed (2+ Sources)" : "Reported (Single Source)"}
                  </span>
                </div>

                <h4 className="text-sm font-bold text-text-primary leading-snug">
                  {bullet.headline}
                </h4>

                <p className="text-xs text-text-secondary mt-1.5 leading-relaxed">
                  {bullet.summary}
                </p>

                {/* Why It Matters */}
                <div className="mt-2.5 p-2 rounded bg-muted/40 border-l-2 border-accent text-xs">
                  <span className="font-semibold text-accent">Why it matters: </span>
                  <span className="text-text-primary">{bullet.whyItMatters}</span>
                </div>
              </div>
            </div>

            {/* Citations Footer */}
            <div className="mt-3 pt-2 border-t border-border/50 flex flex-wrap items-center justify-between text-[11px] text-text-tertiary gap-2">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="font-medium text-text-secondary">Sources:</span>
                {bullet.sourceUrls.map((url, uIdx) => {
                  let hostname = "source";
                  try {
                    hostname = new URL(url).hostname.replace("www.", "");
                  } catch (e) {}
                  return (
                    <a
                      key={uIdx}
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-0.5 text-accent hover:underline"
                    >
                      <span>{hostname}</span>
                      <ExternalLink className="w-2.5 h-2.5" />
                    </a>
                  );
                })}
              </div>
              <span className="tabular-nums">{formatToIST(bullet.published, { timeOnly: true })}</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
};
