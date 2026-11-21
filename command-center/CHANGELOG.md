# Decisions Log & Architectural Trade-offs

## Date: 2026-11-21

### 1. Unified Single-Port Production Serving vs. Multi-Process
- **Context**: The requirements specify a React Vite frontend and a Node.js Express backend proxying third-party APIs.
- **Decision**: Implemented Express static asset serving for `dist/client` in production on port 3001, while maintaining Vite proxy dev mode on port 3000.
- **Trade-off**: Slightly larger server bundle in exchange for running the complete application with a single command (`npm start`) without needing an external Nginx or reverse proxy.

### 2. Live Public Sports Data vs. Paid API Keys
- **Context**: Football and Cricket coverage is required for Premier League, Champions League, La Liga, and international cricket fixtures. Many sports APIs charge commercial subscription fees.
- **Decision**: Integrated ESPN's public global endpoints (`site.api.espn.com` and `site.web.api.espn.com`), which return rich live events, match clocks, scores, and venues without requiring secret API keys. Added a deterministic mock fallback mode (`USE_MOCK_SPORTS=true`) that clearly flags demo data in the UI when upstream networks are unreachable.
- **Trade-off**: ESPN's unofficial endpoints occasionally alter field structures. Handled via Zod loose parsing with safe fallback chains.

### 3. F1 Standings Source: Jolpica F1 API
- **Context**: The Ergast Developer API was officially sunset and transitioned to the community-maintained Jolpica F1 API (`api.jolpi.ca/ergast/f1`).
- **Decision**: Adopted Jolpica F1 API as the primary data source for driver standings, constructor standings, race calendars, and last-race results (Round 20 Brazilian GP). Integrated session timing countdown for Round 21 Las Vegas Grand Prix.
- **Trade-off**: Jolpica serves static and semi-realtime timing rather than sub-second GPS telemetry; sufficient for executive morning briefing needs.

### 4. Weekend Market Handling & Exchange Hours Detection
- **Context**: The session date is Saturday, November 21, 2026. Global equity markets (NSE/BSE, NYSE/NASDAQ, LSE, JPX, HKEX) are closed over weekends.
- **Decision**: Built deterministic timezone-aware market status detection (`open`, `closed`, `pre`, `post`). Crypto (BTC/ETH) is correctly marked as open 24/7. Equities display their official Friday closing prices with explicit "CLOSED" status pills and timestamps, preventing misleading "live" indications.
- **Trade-off**: Avoids synthesizing artificial ticks on weekends; preserves strict Rule 1 compliance ("Never fabricate").

### 5. Multi-Source Grounded AI Briefing Pipeline & Prompt Injection Defense
- **Context**: Briefing items must be summarized from real feeds, capped at 40 words, cited to real URLs, and protected against adversarial instructions embedded in retrieved articles.
- **Decision**: Built a pure rule-grounded synthesis pipeline that deduplicates candidate stories, classifies themes, checks multi-source corroboration (marking 2+ sources as "confirmed" and single sources as "reported"), and sanitizes all untrusted strings by stripping HTML, redacting system prompt overrides, and truncating length.
- **Trade-off**: Does not burn LLM API tokens on every page load; 100% deterministic, testable offline, and immune to prompt injection jailbreaks.

### 6. Design System: Astryx Semantic Design Tokens
- **Context**: Workspace rule `AGENTS.md` directs the use of Meta's Astryx design tokens and CSS themes (Butter, Neutral, Chocolate) in `web/astryx.css` and `web/dash.css`.
- **Decision**: Implemented an editorial layout utilizing Butter (#fdfbe4 body, #f0df72 banner, #1e4fd8 accent, #1d1c11 text) as the primary aesthetic, with full WCAG 2.2 AA contrast compliance across both Light and Dark modes. Used tabular numbers (`font-variant-numeric: tabular-nums`) across all financial tables and standings.
- **Trade-off**: Handcrafted Tailwind token integration ensuring responsive single-column mobile rendering (<640px) up to 3-column desktop (1440px) without horizontal document overflow.
