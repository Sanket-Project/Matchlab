/**
 * Shared formatting utilities:
 * - Indian number system (Lakh, Crore) for INR
 * - International number grouping for USD/others
 * - IST (UTC+05:30) timezone date & time formatting
 * - Signed percentage format with accessible arrow
 */

/**
 * Format an INR number in Indian system (e.g. ₹1,23,456 or 12.5 Lakhs / 1.5 Crores)
 */
export function formatINR(value: number, options: { compact?: boolean; showSymbol?: boolean } = {}): string {
  const { compact = false, showSymbol = true } = options;
  const symbol = showSymbol ? "₹" : "";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";

  if (compact) {
    if (abs >= 10000000) { // 1 Crore = 10^7
      const cr = (abs / 10000000).toFixed(2);
      return `${sign}${symbol}${cr} Cr`;
    }
    if (abs >= 100000) { // 1 Lakh = 10^5
      const lakh = (abs / 100000).toFixed(2);
      return `${sign}${symbol}${lakh} L`;
    }
  }

  // Standard Indian comma grouping: 3 digits rightmost, then groups of 2
  const parts = abs.toFixed(2).split(".");
  let intPart = parts[0];
  const decPart = parts[1];

  if (intPart.length > 3) {
    const lastThree = intPart.substring(intPart.length - 3);
    const otherNumbers = intPart.substring(0, intPart.length - 3);
    const withCommas = otherNumbers.replace(/\B(?=(\d{2})+(?!\d))/g, ",");
    intPart = `${withCommas},${lastThree}`;
  }

  return `${sign}${symbol}${intPart}.${decPart}`;
}

/**
 * Format USD or standard international currency
 */
export function formatUSD(value: number, options: { compact?: boolean; showSymbol?: boolean } = {}): string {
  const { compact = false, showSymbol = true } = options;
  const symbol = showSymbol ? "$" : "";
  const abs = Math.abs(value);
  const sign = value < 0 ? "-" : "";

  if (compact) {
    if (abs >= 1000000000) {
      return `${sign}${symbol}${(abs / 1000000000).toFixed(2)}B`;
    }
    if (abs >= 1000000) {
      return `${sign}${symbol}${(abs / 1000000).toFixed(2)}M`;
    }
    if (abs >= 1000) {
      return `${sign}${symbol}${(abs / 1000).toFixed(1)}k`;
    }
  }

  return `${sign}${symbol}${abs.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/**
 * Format price according to currency
 */
export function formatPrice(price: number, currency: string = "USD"): string {
  if (currency.toUpperCase() === "INR") {
    return formatINR(price);
  }
  return formatUSD(price);
}

/**
 * Format percentage change with sign and direction arrow:
 * e.g. "+1.25% ▲" or "-0.80% ▼" or "0.00% ▬"
 */
export function formatPercentChange(changePct: number): {
  text: string;
  sign: "+" | "-" | "";
  arrow: "▲" | "▼" | "▬";
  direction: "up" | "down" | "flat";
} {
  if (Math.abs(changePct) < 0.001) {
    return {
      text: "0.00%",
      sign: "",
      arrow: "▬",
      direction: "flat",
    };
  }

  const isPositive = changePct > 0;
  const sign = isPositive ? "+" : "-";
  const arrow = isPositive ? "▲" : "▼";
  const absPct = Math.abs(changePct).toFixed(2);

  return {
    text: `${sign}${absPct}%`,
    sign,
    arrow,
    direction: isPositive ? "up" : "down",
  };
}

/**
 * Convert UTC / ISO date string to Asia/Kolkata (IST, UTC+05:30) date & time
 */
export function formatToIST(
  dateInput: string | Date | number,
  options: { includeDate?: boolean; includeSeconds?: boolean; timeOnly?: boolean } = {}
): string {
  const { includeDate = true, includeSeconds = false, timeOnly = false } = options;
  const date = typeof dateInput === "object" ? dateInput : new Date(dateInput);

  if (isNaN(date.getTime())) {
    return "Invalid date";
  }

  const istFormatter = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    year: timeOnly ? undefined : "numeric",
    month: timeOnly ? undefined : "short",
    day: timeOnly ? undefined : "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: includeSeconds ? "2-digit" : undefined,
    hour12: true,
  });

  const formatted = istFormatter.format(date);
  return `${formatted} IST`;
}

/**
 * Format relative time (e.g. "5m ago", "2h ago", "yesterday")
 */
export function formatRelativeTime(dateInput: string | Date | number, nowInput?: Date): string {
  const date = typeof dateInput === "object" ? dateInput : new Date(dateInput);
  const now = nowInput || new Date();
  const diffMs = now.getTime() - date.getTime();

  if (diffMs < 0) {
    const futureSec = Math.floor(-diffMs / 1000);
    if (futureSec < 60) return `in ${futureSec}s`;
    const futureMin = Math.floor(futureSec / 60);
    if (futureMin < 60) return `in ${futureMin}m`;
    const futureHr = Math.floor(futureMin / 60);
    if (futureHr < 24) return `in ${futureHr}h`;
    const futureDays = Math.floor(futureHr / 24);
    return `in ${futureDays}d`;
  }

  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return `${Math.max(1, diffSec)}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDays = Math.floor(diffHr / 24);
  return `${diffDays}d ago`;
}
