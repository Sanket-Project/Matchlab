# Command Center — Executive Morning Briefing Dashboard

> A calm, high-density, editorial personal dashboard for a technology founder in India (IST, UTC+05:30), uniting Global Markets, AI Intelligence, Formula 1 Championship, and Sports Radar into a single command center.

Built with **React 18**, **TypeScript**, **Node.js Express**, **TanStack Query**, and **Astryx Semantic Design Tokens**.

---

## 1. Quick Start (Run in 3 Commands)

```bash
# 1. Navigate to project directory
cd "command-center"

# 2. Build client and server bundles
npm run build

# 3. Start unified production server (serves UI & API on port 3001)
npm start
```
*Open [http://localhost:3001](http://localhost:3001) in your browser.*

For active local development with hot reload:
```bash
npm run dev
# Vite runs on http://localhost:3000, proxying API to backend on :3001
```

---

## 2. Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                       FOUNDER'S VIEWPORT (Client)                           │
│  React 18 + Vite + Tailwind CSS + Astryx Tokens + TanStack Query + PWA      │
│  - Top Bar: Live IST Clock (UTC+05:30), Data Freshness, Currency, Theme    │
│  - Navigation: Desktop Tabs / Mobile Bottom Bar (44px min touch targets)   │
│  - Overview: "Today at a Glance" Hero Card                                  │
│  - Sections: [WORLD] (5 Modules)  |  [FORMULA 1]  |  [MATCHES]              │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP / JSON (Port 3001 / Vite :3000)
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                    NODE.JS EXPRESS BACKEND SERVICE                          │
│  Security Headers (CSP, NoSniff) · Structured Logger · Circuit Breakers     │
│  Request Deduplication · In-Memory Resilient Cache with Per-Source TTLs     │
├─────────────────────────────────────────────────────────────────────────────┤
│ Services:                                                                   │
│  - markets.ts:  Yahoo Finance Chart API (^NSEI, ^BSESN, BTC, Commodities)   │
│  - briefing.ts: Grounded Multi-Source Synthesizer & Prompt Injection Shield │
│  - events.ts:   Confirmed IST Schedule for Today + 48h Outlook              │
│  - models.ts:   OpenRouter Official Model Catalogue                         │
│  - news.ts:     RSS & HN Feed Aggregator (OpenAI, DeepMind, TechCrunch)     │
│  - f1.ts:       Jolpica Ergast F1 API (Standings, Round 21 Las Vegas GP)    │
│  - matches.ts:  ESPN Football & Cricket Scoreboards (Live/Upcoming/FullTime)│
│  - health.ts:   Observability & /health Status Reporting                    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ External API Calls (Parallel Fetchers)
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                     UPSTREAM VERIFIED DATA SOURCES                          │
│  • Yahoo Finance (^NSEI, ^BSESN, ^GSPC, ^IXIC, ^DJI, ^FTSE, ^N225, ^HSI,    │
│                    BZ=F, GC=F, SI=F, INR=X, BTC-USD, ETH-USD)              │
│  • Jolpica F1 API (api.jolpi.ca/ergast/f1) & OpenF1                         │
│  • ESPN Sports APIs (Premier League, Champions League, La Liga, Cricket)    │
│  • OpenRouter Public Registry (openrouter.ai/api/v1/models)                 │
│  • Verified RSS Feeds (OpenAI, Google DeepMind, Hugging Face, Hacker News)  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Data Sources, Limits & Licensing Terms

| Domain | Upstream Source | Endpoints / Protocol | Terms & Rate Limits | Cache TTL |
| :--- | :--- | :--- | :--- | :--- |
| **Indices & FX** | Yahoo Finance | `query1.finance.yahoo.com/v8/finance/chart/{ticker}` | Free public tier. Respects unofficial chart limits. Server throttles calls. | 60s active / 15m idle |
| **Formula 1** | Jolpica F1 API | `api.jolpi.ca/ergast/f1/current/...` | Free community API (Ergast successor). MIT licensed data. | 6 hours |
| **Football & Cricket** | ESPN Global Scoreboard | `site.api.espn.com` & `site.web.api.espn.com` | Public scoreboard feeds. No API key required. | 30s live / 5m upcoming |
| **Model Releases** | OpenRouter Model Registry | `openrouter.ai/api/v1/models` | Free public registry endpoint. | 30 minutes |
| **AI News & HN** | Official Lab RSS & Algolia HN | OpenAI, DeepMind, HF, TechCrunch, The Verge, HN API | Standard public RSS/XML and JSON endpoints. | 10 minutes |

---

## 4. How to Switch to Mock Mode

If you are developing offline or during an external upstream network outage:
1. Open `.env` (or copy from `.env.example`).
2. Set:
   ```env
   USE_MOCK_SPORTS=true
   ```
3. Restart the server: `npm start`.
4. The dashboard will immediately display deterministic fixture data and visibly display a `"Demo Data Mode"` badge in the header of the Sports section.

---

## 5. How to Edit the Dashboard Configuration

All competitions, watched tickers, favorite teams, timezone, currencies, and refresh rates live in a single typed configuration file:
👉 **`config/dashboard.config.ts`**

### Modifying Watched Indices:
```typescript
markets: {
  indices: [
    { symbol: "^NSEI", name: "NIFTY 50", region: "IN", exchange: "NSE" },
    { symbol: "^BSESN", name: "SENSEX", region: "IN", exchange: "BSE" },
    // Add additional Yahoo Finance tickers here...
  ],
}
```

### Adding Favorite Teams & Competitions:
```typescript
sports: {
  football: {
    defaultFavoriteTeams: ["Manchester City", "Arsenal", "Real Madrid", "Barcelona", "Liverpool"],
  },
  cricket: {
    defaultFavoriteTeams: ["India", "Royal Challengers Bengaluru", "Mumbai Indians"],
  }
}
```

---

## 6. Verification & Test Suite Results

The project undergoes rigorous verification before every release:
- **Unit Tests**: Currency formatting (INR lakh/crore, USD grouping), IST date/time conversions, and Zod schema validations.
- **Market Hours Logic**: Weekends correctly closed, Indian exchange pre/open/post-market transitions, US market hours, 24/7 crypto trading.
- **AI Briefing Defense**: Prompt injection neutralizing, HTML stripping, maximum 40-word length enforcement, multi-source corroboration check.
- **Offline Evaluation Suite**: 25 benchmark news articles testing classification accuracy, adversarial jailbreak rejection, and hallucination defense.
- **Integration Tests**: Supertest suite testing all `/api/` endpoints, security headers, and stale fallback upon upstream timeout.
- **Responsive Viewport Verification**: Playwright test suite validating zero horizontal document scroll across 360px, 390px, 430px, 768px, 1024px, and 1440px.

```bash
# Run the test suite:
npm test

# Run TypeScript typecheck / lint:
npm run lint

# Run visual verification and capture screenshots:
node tests/capture-screenshots.mjs
```

### Verified Test Summary:
- **Test Suites**: 5 passed (100%)
- **Total Tests**: 34 passed (100%)
- **Lint Errors**: 0
- **Responsive Breakpoints Verified**: 360px, 390px, 430px, 768px, 1024px, 1440px (All passed with 0 horizontal overflow).
- **Screenshots Captured**: 12 verified screenshots saved in `docs/screenshots/`.

---

## 7. Known Limitations & Next Planned Improvements

1. **Jolpica Live Telemetry Frequency**: Jolpica F1 updates classifications at session conclusions. Sub-second live lap telemetry during race sessions requires OpenF1 streaming WebSocket integration.
2. **Yahoo Finance Official SLA**: The Yahoo Finance chart endpoint is community-accessible without SLA; fallback stale snapshots protect against temporary rate limits.
3. **Historical Head-to-Head Stats**: Detailed multi-decade sports head-to-head records require licensed commercial sports providers (e.g. Sportmonks or Opta).
