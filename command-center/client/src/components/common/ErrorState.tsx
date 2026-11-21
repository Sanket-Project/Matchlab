import React from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { formatToIST } from "@shared/formatters.js";

interface ErrorStateProps {
  title?: string;
  message?: string;
  lastGoodAt?: string;
  onRetry?: () => void;
  isRetrying?: boolean;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = "Data Source Unavailable",
  message = "An error occurred while connecting to the upstream API service.",
  lastGoodAt,
  onRetry,
  isRetrying = false,
}) => {
  return (
    <div
      role="alert"
      className="p-4 rounded-lg border border-negative/30 bg-negative/5 text-text-primary flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="w-5 h-5 text-negative shrink-0 mt-0.5" aria-hidden="true" />
        <div>
          <h4 className="text-sm font-semibold text-text-primary">{title}</h4>
          <p className="text-xs text-text-secondary mt-0.5">{message}</p>
          {lastGoodAt && (
            <p className="text-xs text-text-tertiary mt-1">
              Last successful snapshot: {formatToIST(lastGoodAt)}
            </p>
          )}
        </div>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          disabled={isRetrying}
          className="touch-target-44 px-3 py-1.5 text-xs font-medium rounded border border-border bg-surface hover:bg-muted active:scale-95 transition-all text-text-primary flex items-center gap-1.5 shrink-0"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRetrying ? "animate-spin" : ""}`} />
          {isRetrying ? "Retrying..." : "Try again"}
        </button>
      )}
    </div>
  );
};
