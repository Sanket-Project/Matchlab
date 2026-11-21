import React from "react";
import { formatRelativeTime } from "@shared/formatters.js";

interface StaleBadgeProps {
  lastGoodAt?: string;
}

export const StaleBadge: React.FC<StaleBadgeProps> = ({ lastGoodAt }) => {
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium bg-amber-500/10 text-warning border border-amber-500/20"
      title={lastGoodAt ? `Data as of ${lastGoodAt}` : "Cached data"}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
      Stale {lastGoodAt ? `(${formatRelativeTime(lastGoodAt)})` : ""}
    </span>
  );
};
