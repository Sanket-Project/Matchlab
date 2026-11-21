import { XMLParser } from "fast-xml-parser";
import { config } from "../../../config/dashboard.config.js";
import { AINewsCard, AINewsResponse } from "../../../shared/types.js";
import { formatRelativeTime } from "../../../shared/formatters.js";
import { globalCache } from "./cache.js";

const xmlParser = new XMLParser({
  ignoreAttributes: false,
  attributeNamePrefix: "@_",
});

interface RawArticle {
  title: string;
  url: string;
  source: string;
  published: string;
  summary: string;
  labs: string[];
}

/**
 * Determine AI theme based on headline / summary content
 */
export function categorizeTheme(title: string, summary: string = ""): string {
  const text = `${title} ${summary}`.toLowerCase();
  if (text.includes("policy") || text.includes("regulation") || text.includes("safety") || text.includes("distillation") || text.includes("adversarial") || text.includes("compliance") || text.includes("guidelines") || text.includes("copyright") || text.includes("lawsuit") || text.includes("ftc") || text.includes("white house") || text.includes("antitrust") || text.includes("probe") || text.includes("inquiry")) {
    return "Policy & Safety";
  }
  if (text.includes("data center") || text.includes("datacenter") || text.includes("nuclear") || text.includes("chip") || text.includes("infrastructure") || text.includes("tpu") || text.includes("gpu") || text.includes("cluster") || text.includes("interconnect") || text.includes("fiber") || text.includes("cable") || text.includes("compute")) {
    return "Infrastructure & Compute";
  }
  if (text.includes("fund") || text.includes("ipo") || text.includes("valuation") || text.includes("billion") || text.includes("stock") || text.includes("wipeout") || text.includes("shares") || text.includes("venture") || text.includes("series")) {
    return "Funding & Markets";
  }
  if (text.includes("model") || text.includes("release") || text.includes("launch") || text.includes("weights") || text.includes("open-source") || text.includes("gemini") || text.includes("claude") || text.includes("gpt") || text.includes("transformer") || text.includes("checkpoint")) {
    return "Frontier Models";
  }
  return "Industry & Applications";
}

/**
 * Generate a concise 'why it matters' line
 */
export function generateWhyItMatters(title: string, theme: string): string {
  const text = title.toLowerCase();
  if (text.includes("ipo") || text.includes("anthropic")) {
    return "Sets valuation and public liquidity benchmarks for frontier AI labs amidst broader tech sector market swings.";
  }
  if (text.includes("gemini") || text.includes("gpt") || text.includes("model")) {
    return "Directly impacts developer API capabilities, inference pricing, and latency benchmarks for production applications.";
  }
  if (text.includes("safety") || text.includes("distillation") || text.includes("adversarial")) {
    return "Highlights model extraction risks and defensive measures for enterprises deploying proprietary weights and fine-tunes.";
  }
  if (theme === "Infrastructure & Compute") {
    return "Critical bottleneck indicator for training clusters and next-generation inference capacity.";
  }
  return "Signals strategic shifts in commercial adoption, enterprise workflows, and developer ecosystem tools.";
}

/**
 * Detect lab affiliations
 */
export function detectLabs(text: string): string[] {
  const lower = text.toLowerCase();
  const labs: string[] = [];
  if (lower.includes("openai") || lower.includes("chatgpt")) labs.push("OpenAI");
  if (lower.includes("anthropic") || lower.includes("claude")) labs.push("Anthropic");
  if (lower.includes("google") || lower.includes("deepmind") || lower.includes("gemini")) labs.push("Google DeepMind");
  if (lower.includes("meta") || lower.includes("llama")) labs.push("Meta");
  if (lower.includes("mistral")) labs.push("Mistral");
  if (lower.includes("hugging face")) labs.push("Hugging Face");
  return labs;
}

/**
 * Parse an RSS / Atom feed into normalized RawArticles
 */
export function parseXmlFeed(xmlText: string, sourceName: string): RawArticle[] {
  const parsed = xmlParser.parse(xmlText);
  const items: RawArticle[] = [];

  // Channel items (RSS 2.0)
  const channelItems = parsed?.rss?.channel?.item || parsed?.feed?.entry || [];
  const list = Array.isArray(channelItems) ? channelItems : [channelItems];

  for (const item of list) {
    if (!item) continue;
    const title = (item.title || "").toString().replace(/<[^>]*>/g, "").trim();
    let url = item.link || item.guid || "";
    if (typeof url === "object") {
      url = url["@_href"] || url["#text"] || "";
    }
    const pubDate = item.pubDate || item.published || item.updated || new Date().toISOString();
    const summary = (item.description || item.summary || item.content || "").toString().replace(/<[^>]*>/g, "").slice(0, 300);

    if (title && url) {
      items.push({
        title,
        url: url.toString().trim(),
        source: sourceName,
        published: new Date(pubDate).toISOString(),
        summary,
        labs: detectLabs(`${title} ${summary}`),
      });
    }
  }

  return items;
}

/**
 * Parse Hacker News Algolia response
 */
export function parseHnResponse(json: any): RawArticle[] {
  const hits = json?.hits || [];
  const articles: RawArticle[] = [];

  for (const hit of hits) {
    const title = hit.title || "";
    const url = hit.url || `https://news.ycombinator.com/item?id=${hit.objectID}`;
    const pubDate = hit.created_at || new Date().toISOString();
    const points = hit.points || 0;

    // Filter for AI related topics if coming from general HN front page
    const lower = title.toLowerCase();
    const isAi = lower.includes("ai") || lower.includes("llm") || lower.includes("gpt") || lower.includes("claude") || lower.includes("model") || lower.includes("agent") || lower.includes("neural");
    if (isAi && points >= 20) {
      articles.push({
        title,
        url,
        source: "Hacker News",
        published: new Date(pubDate).toISOString(),
        summary: `${points} points on Hacker News`,
        labs: detectLabs(title),
      });
    }
  }

  return articles;
}

/**
 * Fetch a single feed with timeout
 */
async function fetchSingleFeed(feed: { name: string; url: string; type: "feed" | "hn" }): Promise<RawArticle[]> {
  const response = await fetch(feed.url, {
    headers: {
      "User-Agent": "Mozilla/5.0 (compatible; FounderCommandCenter/1.0)",
      Accept: feed.type === "hn" ? "application/json" : "application/rss+xml, application/xml, text/xml",
    },
    signal: AbortSignal.timeout(6000),
  });

  if (!response.ok) {
    throw new Error(`Feed HTTP ${response.status}`);
  }

  if (feed.type === "hn") {
    const json = await response.json();
    return parseHnResponse(json);
  } else {
    const xml = await response.text();
    return parseXmlFeed(xml, feed.name);
  }
}

/**
 * Deduplicate articles by normalized title similarity
 */
export function deduplicateArticles(articles: RawArticle[]): AINewsCard[] {
  const cards: AINewsCard[] = [];
  const seenClusters: Array<{ keyWords: Set<string>; card: AINewsCard }> = [];

  // Sort newest first
  const sorted = [...articles].sort((a, b) => new Date(b.published).getTime() - new Date(a.published).getTime());

  for (const art of sorted) {
    // Generate simple token bag (ignoring stop words)
    const words = art.title.toLowerCase().replace(/[^a-z0-9\s]/g, "").split(/\s+/).filter(w => w.length > 3);
    const wordSet = new Set(words);

    let matchedCluster: { keyWords: Set<string>; card: AINewsCard } | null = null;
    for (const cluster of seenClusters) {
      let intersection = 0;
      for (const w of wordSet) {
        if (cluster.keyWords.has(w)) intersection++;
      }
      const similarity = intersection / Math.max(1, Math.min(wordSet.size, cluster.keyWords.size));
      if (similarity >= 0.55) {
        matchedCluster = cluster;
        break;
      }
    }

    if (matchedCluster) {
      // Add as duplicate source
      matchedCluster.card.sourceCount++;
      matchedCluster.card.sources.push({ name: art.source, url: art.url });
    } else {
      const theme = categorizeTheme(art.title, art.summary);
      const card: AINewsCard = {
        id: `news-${cards.length + 1}-${Date.parse(art.published)}`,
        title: art.title,
        url: art.url,
        source: art.source,
        published: art.published,
        publishedRelative: formatRelativeTime(art.published),
        labs: art.labs,
        whyItMatters: generateWhyItMatters(art.title, theme),
        theme,
        sourceCount: 1,
        sources: [{ name: art.source, url: art.url }],
      };
      cards.push(card);
      seenClusters.push({ keyWords: wordSet, card });
    }
  }

  return cards.slice(0, 30);
}

/**
 * Get all AI news aggregated across sources
 */
export async function getAINewsData(): Promise<AINewsResponse> {
  const result = await globalCache.getOrFetch(
    "news:ai",
    async () => {
      const sourcesStatus: Array<{ source: string; ok: boolean }> = [];
      const fetchJobs = config.feeds.aiNews.map(async (feed) => {
        try {
          const items = await fetchSingleFeed(feed);
          sourcesStatus.push({ source: feed.name, ok: true });
          return items;
        } catch (err: any) {
          console.warn(`[News] Failed to fetch feed ${feed.name}: ${err.message}`);
          sourcesStatus.push({ source: feed.name, ok: false });
          return [];
        }
      });

      const feedBatches = await Promise.all(fetchJobs);
      const allArticles = feedBatches.flat();

      if (allArticles.length === 0) {
        throw new Error("Failed to retrieve news from all feeds");
      }

      const deduplicated = deduplicateArticles(allArticles);

      return {
        ok: true,
        items: deduplicated,
        checkedAt: new Date().toISOString(),
        sourcesStatus,
      };
    },
    config.cacheTTL.newsSeconds
  );

  return {
    ...result.data,
    isStale: result.isStale,
  };
}
