import { describe, it, expect, beforeAll } from "vitest";
import request from "supertest";
import { app } from "../server/src/index.js";
import { globalCache } from "../server/src/services/cache.js";

describe("API Integration & Failure Resilience", () => {
  describe("Security Headers", () => {
    it("returns strict security headers on all responses", async () => {
      const res = await request(app).get("/health");
      expect(res.headers["x-content-type-options"]).toBe("nosniff");
      expect(res.headers["x-frame-options"]).toBe("DENY");
      expect(res.headers["content-security-policy"]).toBeDefined();
    });
  });

  describe("GET /health", () => {
    it("returns 200 OK with uptime and upstream source statuses", async () => {
      const res = await request(app).get("/health");
      expect(res.status).toBe(200);
      expect(res.body.status).toMatch(/ok|degraded/);
      expect(res.body.sources).toBeDefined();
      expect(res.body.sources.yahooFinance).toBeDefined();
      expect(res.body.sources.jolpicaF1).toBeDefined();
      expect(res.body.sources.espnSports).toBeDefined();
    });
  });

  describe("GET /api/events", () => {
    it("returns confirmed scheduled events for today and 48h preview", async () => {
      const res = await request(app).get("/api/events");
      expect(res.status).toBe(200);
      expect(res.body.ok).toBe(true);
      expect(res.body.todayEvents.length).toBeGreaterThanOrEqual(3);
      expect(res.body.preview48hEvents.length).toBeGreaterThanOrEqual(3);
      expect(res.body.todayEvents[0].impact).toMatch(/high|medium|low/);
      expect(res.body.todayEvents[0].timeIST).toContain("IST");
    });
  });

  describe("GET /api/overview", () => {
    it("returns Today at a Glance summary card", async () => {
      const res = await request(app).get("/api/overview");
      expect(res.status).toBe(200);
      expect(res.body.ok).toBe(true);
      expect(res.body.glance).toBeDefined();
      expect(res.body.glance.checkedAt).toBeDefined();
    }, 15000);
  });

  describe("Failure Resilience & Stale Data Fallback", () => {
    it("serves stale data with timestamp when upstream fails", async () => {
      const cacheKey = "resilience-test";
      const oldTimestamp = new Date(Date.now() - 60000).toISOString();

      // Seed cache with previous good data that is expired
      globalCache.set(cacheKey, { message: "previous good data" }, -10);

      // Fetch with a failing fetcher
      const result = await globalCache.getOrFetch(
        cacheKey,
        async () => {
          throw new Error("Simulated upstream network timeout");
        },
        60
      );

      expect(result.fromCache).toBe(true);
      expect(result.isStale).toBe(true);
      expect(result.data).toEqual({ message: "previous good data" });
      expect(result.lastGoodAt).toBeDefined();
    });
  });
});
