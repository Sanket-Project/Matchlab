import { describe, it, expect } from "vitest";
import { getMarketStatus } from "../server/src/services/markets.js";

describe("Market Hours Logic", () => {
  it("marks crypto as open 24/7 regardless of day or hour", () => {
    // Saturday midnight
    const saturday = new Date("2026-11-21T00:00:00Z");
    expect(getMarketStatus("CRYPTO", saturday)).toBe("open");

    // Sunday midday
    const sunday = new Date("2026-11-22T12:00:00Z");
    expect(getMarketStatus("CRYPTO", sunday)).toBe("open");
  });

  it("marks stock exchanges as closed on weekends", () => {
    // Saturday Nov 21, 2026
    const saturday = new Date("2026-11-21T10:00:00Z");
    expect(getMarketStatus("NSE", saturday)).toBe("closed");
    expect(getMarketStatus("NYSE", saturday)).toBe("closed");
    expect(getMarketStatus("LSE", saturday)).toBe("closed");

    // Sunday Nov 22, 2026
    const sunday = new Date("2026-11-22T10:00:00Z");
    expect(getMarketStatus("NSE", sunday)).toBe("closed");
    expect(getMarketStatus("NASDAQ", sunday)).toBe("closed");
  });

  it("handles Indian market hours (NSE/BSE) on weekdays", () => {
    // Wednesday Nov 18, 2026
    // 09:05 AM IST = 03:35 UTC -> pre-market (09:00 - 09:15 IST)
    const preMarket = new Date("2026-11-18T03:35:00Z");
    expect(getMarketStatus("NSE", preMarket)).toBe("pre");

    // 11:30 AM IST = 06:00 UTC -> open (09:15 - 15:30 IST)
    const openMarket = new Date("2026-11-18T06:00:00Z");
    expect(getMarketStatus("NSE", openMarket)).toBe("open");

    // 15:40 PM IST = 10:10 UTC -> post-market (15:30 - 16:00 IST)
    const postMarket = new Date("2026-11-18T10:10:00Z");
    expect(getMarketStatus("NSE", postMarket)).toBe("post");

    // 18:00 PM IST = 12:30 UTC -> closed
    const nightTime = new Date("2026-11-18T12:30:00Z");
    expect(getMarketStatus("NSE", nightTime)).toBe("closed");
  });

  it("handles US market hours (NYSE/NASDAQ) on weekdays", () => {
    // Wednesday Nov 18, 2026
    // 08:00 ET = 13:00 UTC -> pre-market (04:00 - 09:30 ET)
    const preMarket = new Date("2026-11-18T13:00:00Z");
    expect(getMarketStatus("NYSE", preMarket)).toBe("pre");

    // 11:00 ET = 16:00 UTC -> open (09:30 - 16:00 ET)
    const openMarket = new Date("2026-11-18T16:00:00Z");
    expect(getMarketStatus("NASDAQ", openMarket)).toBe("open");

    // 17:00 ET = 22:00 UTC -> post-market (16:00 - 20:00 ET)
    const postMarket = new Date("2026-11-18T22:00:00Z");
    expect(getMarketStatus("NYSE", postMarket)).toBe("post");

    // 21:00 ET = 02:00 UTC (next day) -> closed
    const closedMarket = new Date("2026-11-19T02:00:00Z");
    expect(getMarketStatus("NYSE", closedMarket)).toBe("closed");
  });
});
