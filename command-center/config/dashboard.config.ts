export interface DashboardConfig {
  app: {
    name: string;
    tagline: string;
    version: string;
  };
  localization: {
    defaultTimezone: string;
    defaultCurrency: "INR" | "USD";
    numberFormat: "indian" | "international";
    fallbackLocale: string;
  };
  markets: {
    indices: Array<{
      symbol: string;
      name: string;
      region: "IN" | "US" | "UK" | "JP" | "HK";
      exchange: string;
    }>;
    commoditiesAndFx: Array<{
      symbol: string;
      name: string;
      category: "commodity" | "fx" | "crypto";
    }>;
  };
  sports: {
    football: {
      competitions: Array<{
        id: string;
        name: string;
        shortName: string;
        endpoint: string;
        country: string;
      }>;
      defaultFavoriteTeams: string[];
    };
    cricket: {
      scoreboardEndpoint: string;
      competitions: Array<{
        name: string;
        category: "international" | "franchise" | "domestic";
      }>;
      defaultFavoriteTeams: string[];
    };
    f1: {
      jolpicaBaseUrl: string;
      openF1BaseUrl: string;
    };
  };
  feeds: {
    aiNews: Array<{
      name: string;
      url: string;
      type: "feed" | "hn";
      category?: string;
    }>;
    modelCatalogUrl: string;
  };
  cacheTTL: {
    marketsActiveSeconds: number; // during market hours
    marketsIdleSeconds: number;   // outside market hours
    newsSeconds: number;
    modelsSeconds: number;
    briefingSeconds: number;
    eventsSeconds: number;
    f1Seconds: number;
    matchesLiveSeconds: number;
    matchesUpcomingSeconds: number;
  };
}

export const config: DashboardConfig = {
  app: {
    name: "Command Center",
    tagline: "Founder's Morning Briefing",
    version: "1.0.0",
  },
  localization: {
    defaultTimezone: "Asia/Kolkata",
    defaultCurrency: "INR",
    numberFormat: "indian",
    fallbackLocale: "en-IN",
  },
  markets: {
    indices: [
      { symbol: "^NSEI", name: "NIFTY 50", region: "IN", exchange: "NSE" },
      { symbol: "^BSESN", name: "SENSEX", region: "IN", exchange: "BSE" },
      { symbol: "^GSPC", name: "S&P 500", region: "US", exchange: "NYSE/NASDAQ" },
      { symbol: "^IXIC", name: "Nasdaq Composite", region: "US", exchange: "NASDAQ" },
      { symbol: "^DJI", name: "Dow Jones Industrial", region: "US", exchange: "NYSE" },
      { symbol: "^FTSE", name: "FTSE 100", region: "UK", exchange: "LSE" },
      { symbol: "^N225", name: "Nikkei 225", region: "JP", exchange: "JPX" },
      { symbol: "^HSI", name: "Hang Seng", region: "HK", exchange: "HKEX" },
    ],
    commoditiesAndFx: [
      { symbol: "BZ=F", name: "Brent Crude", category: "commodity" },
      { symbol: "GC=F", name: "Gold (10g / oz)", category: "commodity" },
      { symbol: "SI=F", name: "Silver", category: "commodity" },
      { symbol: "INR=X", name: "USD / INR", category: "fx" },
      { symbol: "BTC-USD", name: "Bitcoin", category: "crypto" },
      { symbol: "ETH-USD", name: "Ethereum", category: "crypto" },
    ],
  },
  sports: {
    football: {
      competitions: [
        {
          id: "eng.1",
          name: "Premier League",
          shortName: "EPL",
          endpoint: "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard",
          country: "England",
        },
        {
          id: "uefa.champions",
          name: "UEFA Champions League",
          shortName: "UCL",
          endpoint: "https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.champions/scoreboard",
          country: "Europe",
        },
        {
          id: "esp.1",
          name: "La Liga",
          shortName: "LaLiga",
          endpoint: "https://site.api.espn.com/apis/site/v2/sports/soccer/esp.1/scoreboard",
          country: "Spain",
        },
      ],
      defaultFavoriteTeams: ["Manchester City", "Arsenal", "Real Madrid", "Barcelona", "Liverpool"],
    },
    cricket: {
      scoreboardEndpoint: "https://site.web.api.espn.com/apis/v2/scoreboard/header?sport=cricket",
      competitions: [
        { name: "India tour of New Zealand", category: "international" },
        { name: "Border-Gavaskar Trophy", category: "international" },
        { name: "Indian Premier League", category: "franchise" },
        { name: "ICC Champions Trophy", category: "international" },
      ],
      defaultFavoriteTeams: ["India", "Royal Challengers Bengaluru", "Mumbai Indians", "Chennai Super Kings"],
    },
    f1: {
      jolpicaBaseUrl: "https://api.jolpi.ca/ergast/f1",
      openF1BaseUrl: "https://api.openf1.org/v1",
    },
  },
  feeds: {
    aiNews: [
      { name: "OpenAI", url: "https://openai.com/news/rss.xml", type: "feed", category: "frontier-lab" },
      { name: "Google DeepMind", url: "https://deepmind.google/blog/rss.xml", type: "feed", category: "frontier-lab" },
      { name: "Hugging Face", url: "https://huggingface.co/blog/feed.xml", type: "feed", category: "open-source" },
      { name: "TechCrunch AI", url: "https://techcrunch.com/category/artificial-intelligence/feed/", type: "feed", category: "industry" },
      { name: "The Verge AI", url: "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", type: "feed", category: "industry" },
      { name: "Hacker News AI", url: "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=40", type: "hn", category: "developer" },
    ],
    modelCatalogUrl: "https://openrouter.ai/api/v1/models",
  },
  cacheTTL: {
    marketsActiveSeconds: 60,
    marketsIdleSeconds: 900,
    newsSeconds: 600,
    modelsSeconds: 1800,
    briefingSeconds: 10800,
    eventsSeconds: 1800,
    f1Seconds: 21600,
    matchesLiveSeconds: 30,
    matchesUpcomingSeconds: 300,
  },
};
