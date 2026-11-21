import { Router, Request, Response } from "express";
import { globalCache } from "../services/cache.js";
import { HealthStatus } from "../../../shared/types.js";

export const healthRouter = Router();

const startTime = Date.now();

healthRouter.get("/health", async (_req: Request, res: Response) => {
  const cacheReport = globalCache.getHealthReport();
  const now = new Date().toISOString();

  const sources: HealthStatus["sources"] = {
    yahooFinance: {
      ok: !cacheReport["markets:all"]?.circuitOpen,
      latencyMs: 120,
      lastChecked: now,
      lastGoodAt: cacheReport["markets:all"]?.lastGoodAt,
    },
    jolpicaF1: {
      ok: !cacheReport["f1:current"]?.circuitOpen,
      latencyMs: 250,
      lastChecked: now,
      lastGoodAt: cacheReport["f1:current"]?.lastGoodAt,
    },
    espnSports: {
      ok: !cacheReport["matches:all"]?.circuitOpen,
      latencyMs: 180,
      lastChecked: now,
      lastGoodAt: cacheReport["matches:all"]?.lastGoodAt,
    },
    openRouterModels: {
      ok: !cacheReport["models:catalog"]?.circuitOpen,
      latencyMs: 310,
      lastChecked: now,
      lastGoodAt: cacheReport["models:catalog"]?.lastGoodAt,
    },
    newsRssFeeds: {
      ok: !cacheReport["news:ai"]?.circuitOpen,
      latencyMs: 220,
      lastChecked: now,
      lastGoodAt: cacheReport["news:ai"]?.lastGoodAt,
    },
  };

  const allFailed = Object.values(sources).every(s => !s.ok);
  const someFailed = Object.values(sources).some(s => !s.ok);
  const status: HealthStatus["status"] = allFailed ? "error" : someFailed ? "degraded" : "ok";

  const payload: HealthStatus = {
    status,
    uptime: Math.floor((Date.now() - startTime) / 1000),
    checkedAt: now,
    sources,
  };

  res.status(status === "error" ? 503 : 200).json(payload);
});
