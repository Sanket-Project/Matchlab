import { config } from "../../../config/dashboard.config.js";
import { ModelRelease, ModelReleaseResponse } from "../../../shared/types.js";
import { globalCache } from "./cache.js";

interface OpenRouterModel {
  id: string;
  name: string;
  created: number; // Unix timestamp
  description?: string;
  context_length?: number;
  pricing?: {
    prompt: string;
    completion: string;
  };
  architecture?: {
    modality?: string;
    tokenizer?: string;
    instruct_type?: string;
  };
}

export function parseModelStatus(id: string, name: string): "released" | "announced" | "preview" | "deprecated" {
  const lower = `${id} ${name}`.toLowerCase();
  if (lower.includes("deprecated")) return "deprecated";
  if (lower.includes("preview") || lower.includes("beta") || lower.includes("exp") || lower.includes("experimental")) return "preview";
  if (lower.includes("announced") || lower.includes("coming-soon")) return "announced";
  return "released";
}

export function parseLabFromModelId(id: string, name: string): string {
  const parts = id.split("/");
  if (parts.length > 1) {
    const org = parts[0].toLowerCase();
    if (org === "google") return "Google";
    if (org === "openai") return "OpenAI";
    if (org === "anthropic") return "Anthropic";
    if (org === "meta") return "Meta";
    if (org === "mistralai") return "Mistral";
    if (org === "thinkingmachines") return "Thinking Machines";
    if (org === "radixark") return "RadixArk";
    if (org === "liquid") return "LiquidAI";
    if (org === "baidu") return "Baidu";
    if (org === "qwen") return "Alibaba Qwen";
    return parts[0].charAt(0).toUpperCase() + parts[0].slice(1);
  }
  return "Independent";
}

/**
 * Fetch official model catalogue from OpenRouter
 */
export async function getModelReleasesData(): Promise<ModelReleaseResponse> {
  const result = await globalCache.getOrFetch(
    "models:catalog",
    async () => {
      const response = await fetch(config.feeds.modelCatalogUrl, {
        headers: {
          "User-Agent": "Mozilla/5.0 (compatible; FounderCommandCenter/1.0)",
          Accept: "application/json",
        },
        signal: AbortSignal.timeout(8000),
      });

      if (!response.ok) {
        throw new Error(`OpenRouter HTTP ${response.status}`);
      }

      const json: any = await response.json();
      const rawModels: OpenRouterModel[] = json.data || [];

      // Sort newest created first
      const sorted = [...rawModels].sort((a, b) => (b.created || 0) - (a.created || 0));

      const nowSec = Math.floor(Date.now() / 1000);
      const items: ModelRelease[] = [];

      for (const m of sorted) {
        // Skip variants like :batch or :free if parent exists, or normalize
        const createdMs = (m.created || nowSec) * 1000;
        const ageDays = Math.floor((Date.now() - createdMs) / (1000 * 60 * 60 * 24));
        const lab = parseLabFromModelId(m.id, m.name);
        const releaseStatus = parseModelStatus(m.id, m.name);

        const priceInPerMillion = m.pricing?.prompt ? parseFloat(m.pricing.prompt) * 1000000 : 0;
        const priceOutPerMillion = m.pricing?.completion ? parseFloat(m.pricing.completion) * 1000000 : 0;
        const isFree = priceInPerMillion === 0 && priceOutPerMillion === 0;

        const blurb = (m.description || `${m.name} from ${lab}.`)
          .replace(/<[^>]*>/g, "")
          .trim()
          .slice(0, 200);

        items.push({
          id: m.id,
          name: m.name || m.id,
          lab,
          releaseStatus,
          releasedAt: new Date(createdMs).toISOString(),
          ageDays,
          isNew: ageDays <= 7,
          contextWindow: m.context_length || 128000,
          priceIn: Number(priceInPerMillion.toFixed(2)),
          priceOut: Number(priceOutPerMillion.toFixed(2)),
          isFree,
          blurb,
          url: `https://openrouter.ai/${m.id}`,
          officialSource: "OpenRouter Verified Model Registry",
        });

        if (items.length >= 25) break;
      }

      return {
        ok: true,
        items,
        source: "OpenRouter Official Model Catalogue",
        checkedAt: new Date().toISOString(),
      };
    },
    config.cacheTTL.modelsSeconds
  );

  return {
    ...result.data,
    isStale: result.isStale,
  };
}
