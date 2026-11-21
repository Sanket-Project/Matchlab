# Live vs local: what differed, and what differs now

Captured 2026-11-21 with `tools/ui-checks/capture.cjs` (headless Chromium, reduced motion) at 360, 768, 1280 and
1920 px for: `/`, `#matches`, `#match/tennis-187528`, `#world`, `#f1`, `#record`, `#settings` and `/lab`.
Each folder has `log.json`, with load time, `h1`, API status codes, console errors, failed requests and
horizontal overflow per page.

| Capture | Folder |
|---|---|
| Live, before (dashboard pages via `/dash`, since `/` was the lab) | `docs/screens/before/live/` |
| Local, before (`127.0.0.1:8766`, commit `3dd42a1`) | `docs/screens/before/local/` |
| Live, after | `docs/screens/after/live/` |
| Local, after | `docs/screens/after/local/` |

File names are `<page>-<width>.webp` (PNG captures converted to WebP to keep the repository small), for example `docs/screens/before/live/record-1280.webp`.

## Before: every difference

| # | Where | Local (`127.0.0.1:8766`) | Live (`matchlab-ten.vercel.app`) | Evidence |
|---|---|---|---|---|
| 1 | `/` | The dashboard (`web/dash.html`): Matches hero, filter chips, cards | **Legacy lab** "Who's going to win?" (`public/index.html`, 15,472 B) | `before/local/root-1280.webp` vs `before/live/root-1280.webp` |
| 2 | `/lab` | Legacy lab, working (`/api/state` 200) | Legacy lab, **broken** (`/api/state` 403, empty selects) | `before/live/lab-*.webp`, `log.json` |
| 3 | `#matches` … `#settings` | Each view renders | Only reachable at `/dash`; every view shows **"MatchLab could not start"**, with "The local server did not answer (Local same-origin requests only)…" | `before/live/{matches,world,f1,record,settings}-*.webp` |
| 4 | `/api/session`, `/api/today-matches`, `/api/track-record`, every `/api/*` | 200 | **403** `{"error": "Local same-origin requests only"}`, with `app.py`'s CSP header | `log.json`; `curl -D -` |
| 5 | Unknown paths (`/nope`, `/app.py`, `/config.local.json`, `/data/today_matches.json`) | 404 | 403 from the same `app.py` handler (not served, but answered by Python) | curl |
| 6 | Match detail | Forecast, live analysis, AI check | Error page | `before/live/match-*.webp` |
| 7 | Track Record | 17 counted, tables | Error page; and the prediction log was never deployed (`data/local/` is git-ignored) | `before/live/record-*.webp` |
| 8 | Front-end files | `web/` | `public/` copy: `dash.*` identical, `app.js` **different** | `cmp web/app.js public/app.js` |
| 9 | Fonts and images | Served by `app.py` with ETag | Served statically by Vercel (same bytes) | — |
| 10 | Console | No errors | Two 403 errors on every dashboard page; one on `/` and `/lab` | `log.json` |
| 11 | Overflow at 360 px | None | None (error page) | `log.json` |

## Root cause

`app.py` sits at the repository root. Vercel picked it as the project's Python entrypoint and routed every
non-static request to its `Handler`, whose localhost guard rejects any `Host` other than `127.0.0.1:<port>`. The
intended `api/index.py` never ran. `/` matched the static file `public/index.html` (the lab) before the rewrite to
`dash.html` could apply. Details and the fix: `hosting-decision.md`.

## After: intended differences only

Both sites now serve the same `web/dash.html`, `dash.js` and `dash.css`. The differences that remain are deliberate,
and the hosted page states each one on screen:

| Area | Local | Hosted |
|---|---|---|
| Label | Budget chips in the utility bar | "Public read-only copy · Snapshot from N min ago" |
| Schedule | Refreshed by the local worker every 5 minutes; Refresh button | Published snapshot; no Refresh; re-read every 5 minutes |
| Match page | Full forecast, live analysis, AI check | The saved (locked) forecast, its grade and saved live checks |
| Track Record | Live log; grades finished events in the background | Published log; same numbers at publish time |
| World briefing | Written on request (OpenRouter, metered) | Last published briefing, read-only |
| Settings | Theme, budgets, OpenRouter key | Theme, plus "About this copy" |
| `/lab` | Legacy lab (F1 race forecast) | Redirects to `/` |
| F1, World headlines | Live public feeds | Live public feeds (cached on the CDN) |

The after-capture logs (`docs/screens/after/*/log.json`) show 200 for every API call on both sites and no console
errors.
