import { config } from "../../../config/dashboard.config.js";
import { MarketQuote, MarketsResponse } from "../../../shared/types.js";
import { globalCache } from "./cache.js";

/**
 * Determine market operating status (open, closed, pre, post)
 * based on exchange, day of week, local market hours, and holidays.
 */
export function getMarketStatus(exchange: string, date: Date = new Date()): "open" | "closed" | "pre" | "post" {
  // Crypto exchanges operate 24/7
  if (exchange.toUpperCase() === "CRYPTO") {
    return "open";
  }

  // Weekends check in UTC
  const dayOfWeek = date.getUTCDay(); // 0 = Sun, 6 = Sat
  if (dayOfWeek === 0 || dayOfWeek === 6) {
    return "closed";
  }

  // Exchange specific checks
  const ex = exchange.toUpperCase();

  // 1. Indian Markets (NSE / BSE) - IST is UTC+05:30
  if (ex.includes("NSE") || ex.includes("BSE") || ex.includes("INDIA")) {
    const istMinutes = (date.getUTCHours() * 60 + date.getUTCMinutes() + 330) % 1440;
    // 09:00 IST = 540 min, 09:15 IST = 555 min, 15:30 IST = 930 min
    if (istMinutes >= 540 && istMinutes < 555) {
      return "pre";
    }
    if (istMinutes >= 555 && istMinutes < 930) {
      return "open";
    }
    if (istMinutes >= 930 && istMinutes < 960) {
      return "post";
    }
    return "closed";
  }

  // 2. US Markets (NYSE / NASDAQ) - Eastern Time (UTC-5 in winter / EST)
  if (ex.includes("NYSE") || ex.includes("NASDAQ") || ex.includes("US")) {
    const etMinutes = (date.getUTCHours() * 60 + date.getUTCMinutes() - 300 + 1440) % 1440;
    // 04:00 ET = 240, 09:30 ET = 570, 16:00 ET = 960, 20:00 ET = 1200
    if (etMinutes >= 240 && etMinutes < 570) {
      return "pre";
    }
    if (etMinutes >= 570 && etMinutes < 960) {
      return "open";
    }
    if (etMinutes >= 960 && etMinutes < 1200) {
      return "post";
    }
    return "closed";
  }

  // 3. Tokyo (JPX / Nikkei) - JST is UTC+9
  if (ex.includes("JPX") || ex.includes("TOKYO") || ex.includes("NIKKEI")) {
    const jstMinutes = (date.getUTCHours() * 60 + date.getUTCMinutes() + 540) % 1440;
    // 09:00 to 15:00 JST = 540 to 900
    if (jstMinutes >= 540 && jstMinutes < 900) {
      return "open";
    }
    return "closed";
  }

  // 4. London (LSE / FTSE) - GMT is UTC+0
  if (ex.includes("LSE") || ex.includes("FTSE")) {
    const gmtMinutes = date.getUTCHours() * 60 + date.getUTCMinutes();
    // 08:00 to 16:30 GMT = 480 to 990
    if (gmtMinutes >= 480 && gmtMinutes < 990) {
      return "open";
    }
    return "closed";
  }

  // 5. Hong Kong (HKEX / Hang Seng) - HKT is UTC+8
  if (ex.includes("HKEX") || ex.includes("HK")) {
    const hktMinutes = (date.getUTCHours() * 60 + date.getUTCMinutes() + 480) % 1440;
    // 09:30 to 16:00 HKT = 570 to 960
    if (hktMinutes >= 570 && hktMinutes < 960) {
      return "open";
    }
    return "closed";
  }

  return "closed";
}

/**
 * Fetch quote and historical sparkline series from Yahoo Finance
 */
export async function fetchYahooQuote(
  symbol: string,
  displayName: string,
  category: "index" | "commodity" | "fx" | "crypto",
  exchangeName: string
): Promise<MarketQuote> {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=7d&interval=1d`;
  const response = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      Accept: "application/json",
    },
    signal: AbortSignal.timeout(8000),
  });

  if (!response.ok) {
    throw new Error(`Yahoo Finance HTTP ${response.status} for ${symbol}`);
  }

  const json: any = await response.json();
  const result = json?.chart?.result?.[0];
  if (!result || !result.meta) {
    throw new Error(`Invalid response structure from Yahoo Finance for ${symbol}`);
  }

  const meta = result.meta;
  const price = meta.regularMarketPrice ?? meta.previousClose ?? 0;
  const prevClose = meta.chartPreviousClose ?? meta.previousClose ?? price;
  const change = price - prevClose;
  const changePct = prevClose > 0 ? (change / prevClose) * 100 : 0;

  // Extract closing price series for sparkline
  const timestamps = result.timestamp || [];
  const closes = result.indicators?.quote?.[0]?.close || [];
  const validSeries: number[] = [];

  for (let i = 0; i < closes.length; i++) {
    const val = closes[i];
    if (typeof val === "number" && !isNaN(val) && val > 0) {
      validSeries.push(Number(val.toFixed(2)));
    }
  }

  // Fallback series if single point returned
  const series = validSeries.length >= 2 ? validSeries : [prevClose, price];

  const asOf = meta.regularMarketTime
    ? new Date(meta.regularMarketTime * 1000).toISOString()
    : new Date().toISOString();

  const marketStatus = getMarketStatus(category === "crypto" ? "CRYPTO" : exchangeName);

  return {
    symbol,
    name: displayName,
    price: Number(price.toFixed(2)),
    change: Number(change.toFixed(2)),
    changePct: Number(changePct.toFixed(2)),
    currency: meta.currency || "USD",
    dayHigh: meta.regularMarketDayHigh ? Number(meta.regularMarketDayHigh.toFixed(2)) : null,
    dayLow: meta.regularMarketDayLow ? Number(meta.regularMarketDayLow.toFixed(2)) : null,
    asOf,
    series,
    marketStatus,
    exchange: meta.exchangeName || exchangeName,
    source: "Yahoo Finance",
    category,
  };
}

/**
 * Fetch all indices and commodities/FX in parallel with per-ticker resilience
 */
export async function getMarketsData(): Promise<MarketsResponse> {
  const isWeekend = [0, 6].includes(new Date().getUTCDay());
  const ttl = isWeekend ? config.cacheTTL.marketsIdleSeconds : config.cacheTTL.marketsActiveSeconds;

  const result = await globalCache.getOrFetch(
    "markets:all",
    async () => {
      // 1. Fetch indices
      const indexPromises = config.markets.indices.map(async (item) => {
        try {
          return await fetchYahooQuote(item.symbol, item.name, "index", item.exchange);
        } catch (err: any) {
          console.warn(`[Markets] Error fetching index ${item.symbol}: ${err.message}`);
          return null;
        }
      });

      // 2. Fetch commodities and FX
      const commPromises = config.markets.commoditiesAndFx.map(async (item) => {
        try {
          return await fetchYahooQuote(item.symbol, item.name, item.category, item.category === "crypto" ? "CRYPTO" : "COMMODITY");
        } catch (err: any) {
          console.warn(`[Markets] Error fetching commodity/fx ${item.symbol}: ${err.message}`);
          return null;
        }
      });

      const [indexResults, commResults] = await Promise.all([
        Promise.all(indexPromises),
        Promise.all(commPromises),
      ]);

      const indices = indexResults.filter((q): q is MarketQuote => q !== null);
      const commoditiesAndFx = commResults.filter((q): q is MarketQuote => q !== null);

      if (indices.length === 0 && commoditiesAndFx.length === 0) {
        throw new Error("Unable to fetch any market quotes from Yahoo Finance");
      }

      return {
        ok: true,
        indices,
        commoditiesAndFx,
        checkedAt: new Date().toISOString(),
      };
    },
    ttl
  );

  return {
    ...result.data,
    isStale: result.isStale,
    lastGoodAt: result.lastGoodAt,
  };
}
