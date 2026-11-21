import { Router, Request, Response } from "express";
import { getMarketsData } from "../services/markets.js";
import { getAIBriefingData } from "../services/briefing.js";
import { getEventsData } from "../services/events.js";
import { getModelReleasesData } from "../services/models.js";
import { getAINewsData } from "../services/news.js";
import { getF1Data } from "../services/f1.js";
import { getMatchesData } from "../services/matches.js";
import { TodayAtAGlance } from "../../../shared/types.js";
import { globalCache } from "../services/cache.js";

export const apiRouter = Router();

// 1. Markets
apiRouter.get("/markets", async (req: Request, res: Response) => {
  try {
    if (req.query.refresh === "1") {
      globalCache.invalidate("markets:all");
    }
    const data = await getMarketsData();
    res.json(data);
  } catch (error: any) {
    res.status(500).json({ ok: false, error: error.message, checkedAt: new Date().toISOString() });
  }
});

// 2. AI Briefing
apiRouter.get("/briefing", async (req: Request, res: Response) => {
  try {
    if (req.query.refresh === "1") {
      globalCache.invalidate("briefing:daily");
    }
    const data = await getAIBriefingData();
    res.json(data);
  } catch (error: any) {
    res.status(500).json({ ok: false, error: error.message, generatedAt: new Date().toISOString() });
  }
});

// 3. What Happens Today
apiRouter.get("/events", async (req: Request, res: Response) => {
  try {
    if (req.query.refresh === "1") {
      globalCache.invalidate("events:schedule");
    }
    const data = await getEventsData();
    res.json(data);
  } catch (error: any) {
    res.status(500).json({ ok: false, error: error.message, checkedAt: new Date().toISOString() });
  }
});

// 4. Model Releases
apiRouter.get("/models", async (req: Request, res: Response) => {
  try {
    if (req.query.refresh === "1") {
      globalCache.invalidate("models:catalog");
    }
    const data = await getModelReleasesData();
    res.json(data);
  } catch (error: any) {
    res.status(500).json({ ok: false, error: error.message, checkedAt: new Date().toISOString() });
  }
});

// 5. AI News
apiRouter.get("/news", async (req: Request, res: Response) => {
  try {
    if (req.query.refresh === "1") {
      globalCache.invalidate("news:ai");
    }
    const data = await getAINewsData();
    res.json(data);
  } catch (error: any) {
    res.status(500).json({ ok: false, error: error.message, checkedAt: new Date().toISOString() });
  }
});

// 6. Formula 1
apiRouter.get("/f1", async (req: Request, res: Response) => {
  try {
    if (req.query.refresh === "1") {
      globalCache.invalidate("f1:current");
    }
    const data = await getF1Data();
    res.json(data);
  } catch (error: any) {
    res.status(500).json({ ok: false, error: error.message, checkedAt: new Date().toISOString() });
  }
});

// 7. Matches
apiRouter.get("/matches", async (req: Request, res: Response) => {
  try {
    if (req.query.refresh === "1") {
      globalCache.invalidate("matches:all");
    }
    const data = await getMatchesData();
    res.json(data);
  } catch (error: any) {
    res.status(500).json({ ok: false, error: error.message, checkedAt: new Date().toISOString() });
  }
});

// 8. Overview: Today at a glance
apiRouter.get("/overview", async (_req: Request, res: Response) => {
  try {
    const [markets, news, f1, matches, events] = await Promise.allSettled([
      getMarketsData(),
      getAINewsData(),
      getF1Data(),
      getMatchesData(),
      getEventsData(),
    ]);

    // Top market mover
    let marketLeader = null;
    if (markets.status === "fulfilled" && markets.value.indices.length > 0) {
      const sorted = [...markets.value.indices].sort((a, b) => Math.abs(b.changePct) - Math.abs(a.changePct));
      marketLeader = {
        symbol: sorted[0].symbol,
        name: sorted[0].name,
        changePct: sorted[0].changePct,
        price: sorted[0].price,
        currency: sorted[0].currency,
      };
    }

    // Top headline
    let topHeadline = null;
    if (news.status === "fulfilled" && news.value.items.length > 0) {
      const topNews = news.value.items[0];
      topHeadline = {
        title: topNews.title,
        source: topNews.source,
        whyItMatters: topNews.whyItMatters,
      };
    }

    // Next F1 session
    let nextF1Session = null;
    if (f1.status === "fulfilled" && f1.value.session) {
      nextF1Session = {
        sessionName: f1.value.session.nextSessionName,
        countdown: f1.value.session.nextSessionCountdown,
        dateIST: f1.value.session.nextSessionDateIST,
      };
    }

    // Next or live match
    let nextMatch = null;
    if (matches.status === "fulfilled" && matches.value.matches.length > 0) {
      const live = matches.value.matches.find(m => m.status === "live");
      const chosen = live || matches.value.matches[0];
      nextMatch = {
        matchName: `${chosen.homeTeam.name} vs ${chosen.awayTeam.name}`,
        competition: chosen.competitionName,
        kickoffTimeIST: chosen.kickoffTimeIST,
        isLive: chosen.status === "live",
      };
    }

    // Key today event
    let keyTodayEvent = null;
    if (events.status === "fulfilled" && events.value.todayEvents.length > 0) {
      const ev = events.value.todayEvents[0];
      keyTodayEvent = {
        title: ev.title,
        timeIST: ev.timeIST,
        impact: ev.impact,
      };
    }

    const glance: TodayAtAGlance = {
      marketLeader,
      topHeadline,
      nextF1Session,
      nextMatch,
      keyTodayEvent,
      checkedAt: new Date().toISOString(),
    };

    res.json({ ok: true, glance });
  } catch (error: any) {
    res.status(500).json({ ok: false, error: error.message });
  }
});
