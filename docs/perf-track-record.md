# Track Record performance

Date: 2026-11-21. Data: the real prediction log (31 saved events: 23 cricket, 7 tennis, 1 F1; 344 KB on disk).
Tools: `tools/ui-checks/record-perf.cjs` (headless Chromium, fresh context per run, 1280×900), a keep-alive HTTP
timer for the API, and in-page `fetch` timing in a real browser for the hosted site. "Before" is commit `3dd42a1`
run from a separate worktree on port 8768 against a copy of the same log. "After" is the current `main`.

## Profile before any change

| Step | Time | Note |
|---|---|---|
| `predictions.json` read + parse | 4.0 ms median, 5.2 ms p95 | 344 KB |
| `tracker._read` (with the Supabase attempt, blocked offline) | 3.7 ms median | the network attempt failed fast because of the offline guard |
| `tracker.track_record` (grading summary) | 12.8 ms median, 19.1 ms p95 | read the log three times (rows, plus calibration for two sports) |
| `/api/track-record`, **first call** after start | **2,352 ms** | grades pending events *before* replying: one `fetch_match_intel.py` subprocess per pending event, about 2.1 s each, up to six in a row (about 12 s worst case) |
| `/api/track-record`, warm | 40–59 ms median, 64 ms p95 | 81,543 B, every row sent twice (top level and per sport) |
| Front end | spinner text only until the reply; whole table drawn (up to 100 rows per sport) | |
| Hosted site | **never loaded** | every API call returned 403 (see `live-vs-local-diff.md`) |

The cost was not the grading maths. It was the synchronous feed reads in front of the reply, plus a doubled payload.

## Changes

1. **Reply first, grade in the background** (`app.py`). The endpoint returns the record at once and starts one
   background thread for pending events. The reply carries `grading: true`; the page re-asks once after 8 s and
   patches itself in place.
2. **Cached aggregates** (`matchlab/tracker.py`). The summary is computed once per version of the log file
   (path, mtime, size) and the cache is cleared on every write. Calibration reuses the same parsed data instead of
   re-reading the file.
3. **Summaries, not history**. The duplicate top-level row list is removed. Each sport sends 25 rows plus a `total`;
   the rest load with "Show more" (`/api/track-record?sport=…&offset=…`).
4. **Skeleton at once** (`web/dash.js`). The hero, the counter and three stat blocks are drawn before the request,
   in their final positions, so nothing shifts when the numbers arrive.
5. **Hosted: CDN-cacheable**. `/api/track-record` on the mirror sends `s-maxage=300, stale-while-revalidate=3600`
   and an ETag. The snapshot only changes on a deploy, so this is safe.
6. **Hosted cold start**. The mirror imports only the tracker and world modules (standard library; numpy is no longer
   pulled in through `team_key`): about 45 ms instead of about 450 ms. `api/requirements.txt` is empty.

## Results

### API

| Endpoint | Before | After |
|---|---|---|
| Local `/api/track-record`, first call with a pending event | 2,352 ms | 33 ms (grading continues in the background) |
| Local `/api/track-record`, warm (n = 40, keep-alive) | 59 ms median, 64 ms p95 | **31 ms median, 43 ms p95** |
| Payload | 81,543 B | 43,117 B (39,597 B on the mirror) |
| Hosted `/api/track-record`, CDN hit (n = 8, browser in India) | 403 | **27–40 ms** (first request 138 ms) |
| Hosted `/api/track-record`, CDN miss, function runs (n = 10, cache-busting query) | 403 | **241–283 ms, p95 ≈ 283 ms** |

The hosted function runs in `iad1` (Washington). From India most of the uncached 250 ms is the network round trip.
Real traffic is served from the CDN cache.

### First meaningful paint of `#record` (headless Chromium, 1280 px, n = 5 fresh contexts)

| | FCP median | Shell on screen | Numbers on screen, median / p95 | API in page |
|---|---|---|---|---|
| Local before (`3dd42a1`, grading cache warm) | 124 ms | 122 ms ("Grading finished events…" text) | 218 / 268 ms | 56 ms |
| Local after | 104 ms | 102 ms (skeleton) | **168 / 179 ms** | 38 ms |
| Hosted after (the one run that passed Vercel's bot check; see below) | 176 ms | 394 ms | **673 ms** | 267 ms (CDN miss) |

Targets: first meaningful paint of `#record` under 1 s on the hosted site is **met** (673 ms in the measured run).
API p95 under 300 ms is **met**: about 40 ms from the CDN and about 283 ms uncached.

### A measurement caveat

After about 300 scripted requests from this machine, Vercel's automatic bot mitigation started answering this IP with
its "Security Checkpoint" (HTTP 403 with `X-Vercel-Mitigated: challenge`, solved by a browser's JavaScript). Four
of the five headless hosted runs stalled on that page. A real browser passes it once and keeps a cookie. This is
Vercel's platform behaviour, not the app's, but if it is ever on for everyone it adds a round trip to the first
visit. It is worth checking in the project's Firewall settings (owner).

Lighthouse was not run: it is not installed on this machine, and installing it needs a download that was not
approved. Command for the owner: `npx lighthouse https://matchlab-ten.vercel.app/#record --view`.
