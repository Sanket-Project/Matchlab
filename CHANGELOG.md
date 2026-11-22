# Changelog

## 2026-11-22

### The public site is live, not a snapshot
- **Why it was 11–12 hours behind:** the hosted site only served `data/public/today_matches.json`, which changed only
  when the owner ran `tools/publish_snapshot.py` and pushed. Nothing on the site refreshed it.
- `/api/today-matches` on the hosted site now reads ESPN's free cricket, tennis and F1 scoreboards on request
  (`tools/fetch_today_matches.py --stdout` with `MATCHLAB_HOSTED=1`: free feeds only, no keys, no AI search, nothing
  written). Cached 20 s while anything is live, 45 s otherwise, and at the CDN for 20 s. "Today" is the owner's day
  (`MATCHLAB_TZ`, default Asia/Kolkata). Saved forecasts still attach: a fixture the owner's MatchLab listed under a
  CricketData id keeps that id. If ESPN fails, the published schedule is shown with a note and it retries.
- New `/api/cricket-live`: score, toss, venue and playing XIs from ESPN's free match summary, every 15 s while live.
  Tennis live scores now work for matches that are not in the published snapshot too.
- The dashboard checks the schedule by itself: every 30 s (60 s with nothing live) on the hosted site, every 2–5 min
  on the owner's MatchLab, and again when a background tab is opened. The hosted site has a Refresh button again.
  Freshness labels say "Live scores · checked …"; the header says when forecasts were last published.
- Fixed (local): when the background watcher and the page refreshed at the same time, the page got the old schedule
  back and kept it until its next check. It now waits for the refresh that is already running.
- **Forecasts publish themselves.** While MatchLab runs, `matchlab/autopublish.py` checks every minute and, when a
  forecast is saved or graded (or the World briefing changes), runs `tools/publish_snapshot.py`, commits only
  `data/public/` and pushes: at most every 15 minutes, live timelines alone every 3 hours (Vercel's free plan allows
  100 deployments a day). It never pushes your own unpushed commits, does nothing off `main` or during a merge or
  rebase, never prompts for credentials, and retries a failed push after 5 minutes. Settings → Public site shows the
  status and has **Publish now**. Off with `app.py --no-publish` or `MATCHLAB_AUTO_PUBLISH=0`.

### AI web search when sports feeds hit their limit
- When CricketData.org reaches its daily limit (or every feed for a sport fails), Gemini with Google Search grounding
  looks up today's fixtures and scores. It only adds missing fixtures and fills blank scores, keeps only answers that
  cite web pages, is metered (`gemini_search`, 100 a day) and cached, and is labelled "AI web search" on each card.
  AI-only fixtures are not saved to Track record. A CricketData "limit exceeded" reply now also counts as the limit.
- Status: the current Gemini key has no Google Search grounding quota (free tier), so the lookup is dormant and
  says so under Settings → Request budgets. It turns on by itself once grounding is enabled for the key.

### Fixes after the API key check
- **CricketData.org was silently off.** `tools/fetch_today_matches.py` read `os.environ` without importing `os`;
  the `NameError` was caught and every refresh fell back to ESPN only. Fixed; the `.env` lookup now uses the
  project root, so tests stay isolated from your real `.env`.
- **AI requests survive a dead saved key.** The AI worker (`tools/fetch_openrouter_preview.py`, used by AI checks,
  summaries, previews and the World briefing) retries once with `OPENROUTER_API_KEY` from the environment or `.env`
  when OpenRouter rejects the key it was given, then falls back to Google Gemini (`GEMINI_API_KEY`) if OpenRouter
  still cannot answer. Each request is still metered once in the OpenRouter ledger. The answer's `model` shows
  `google/…` when Gemini replied.
- Two tennis data tests now check archive rows and local supplement rows by their own documented rules
  (supplement rows carry no entry rankings and use the match day as availability date).

## 2026-11-21

### New data feeds (chosen from the public-apis list)
- **Weather at the start** on cricket, tennis and Formula 1 pages, from [Open-Meteo](https://open-meteo.com/) (free, no
  key, non-commercial). Shown as context only; the forecast models do not use it. `tools/fetch_weather.py`,
  `matchlab/conditions.py`, `GET /api/conditions`, cached 30 minutes.
- **Race weekend so far** on the F1 page: finished practice and qualifying classifications and track weather from
  [OpenF1](https://openf1.org/) (free tier; live timing during a session is paid, so a session shows once it ends).
  `tools/fetch_openf1.py`, `matchlab/openf1.py`, `GET /api/f1-weekend`, cached 10 minutes.
- **AcesAPI second view** on tennis pages: both players' surface Elo and full head-to-head from
  [AcesAPI](https://acesapi.com/), with your own key (Settings; saved with Windows DPAPI). Asked only on a button
  press, 7 credits, saved for a day. The budget ledger now meters monthly credits (`acesapi`: 500, 20 held back).
- SportScore was left out: its site refuses automated access.

### Hosting
- The Vercel site now serves the real dashboard at `/` as a **read-only public mirror** of the owner's MatchLab.
  Previously `/` was the legacy lab and every API call returned 403 (Vercel ran `app.py` and its localhost guard).
  See `docs/hosting-decision.md` and `docs/live-vs-local-diff.md`.
- `vercel.json` pins the entrypoint (`api/index.py`) and whitelists the static files. `public/` (a drifting copy of
  `web/`) is removed.
- New: `tools/publish_snapshot.py` (publish schedule, prediction log and briefing to `data/public/`) and
  `tools/mirror_preview.py` (run the hosted layout locally on port 8767).

### Security
- Removed the Supabase adapter and its hard-coded key. The API budget ledger is local again, so a shared table can
  no longer reset it. **Rotate that key**: it is still in git history.
- The hosted API holds no keys and refuses every write (403). Rate limit: 60 requests per minute per client.

### Track Record
- Replies at once (2.35 s → 33 ms on the first call); finished events are graded in the background.
- Cached summary, 25 rows per sport with "Show more", payload 81 KB → 43 KB, loading skeleton.
- Calibration table (n per bin). The AI-check rate is shown next to the model's rate on the same forecasts.
- A forecast counts only if both its saved copy and its grade say it was saved before the start.
- A failed save now raises instead of passing silently.
- `tools/verify_track_record.py` recomputes every number independently; all match.

### Dashboard
- Match cards say whether the forecast is locked ("Locked 6:14 PM") and show the locked pick.
- The owner's F1 and tennis portraits: faces on tennis cards and in the F1 standings, a leader portrait with the gap
  to P2, and portraits on tennis match pages. WebP with `srcset`, explicit sizes, lazy loading, initials fallback.
- Hosted wording everywhere: snapshot age, no Refresh, read-only Settings.
- Busy buttons stay readable (contrast fix).

### AI
- A stored AI check is capped at ±5 points where it is applied, not only when it is parsed.

### Tests
- `tests/test_track_record.py` (15 tests): counting rules, bins, shared samples, paging, read-only mode, locks,
  the mirror (403 on writes, 404 on files, 429 on bursts), the AI cap, and stripping of uncited briefing sentences.
