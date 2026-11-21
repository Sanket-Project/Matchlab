# Hosting decision: a read-only public mirror

Date: 2026-11-21. Applies to https://matchlab-ten.vercel.app/.

## What was wrong (summary; evidence in `live-vs-local-diff.md`)

1. Vercel treated the root `app.py` as the project's Python entrypoint. Every request that was not a static
   file reached `app.py`'s `Handler`, whose `_local_request()` guard allows only `Host: 127.0.0.1:<port>`. So
   every `/api/*` route, and every unknown path, answered `403 {"error": "Local same-origin requests only"}`.
   The response headers carry `app.py`'s exact CSP, so this is not a guess.
2. `api/index.py` (a hand-made second copy of the server, backed by Supabase) never ran, because `app.py`
   shadowed it.
3. `/` served `public/index.html`, a copy of the legacy lab page. In Vercel's routing, a static file wins over a
   rewrite, so `"rewrites": [{"source": "/", "destination": "/dash.html"}]` never applied. `public/` was a
   hand-kept copy of `web/` (its `app.js` had already drifted).
4. `data/local/` (the prediction log) is git-ignored, so the hosted site could never have shown the track record.

## Options considered

| Option | What it means | Verdict |
|---|---|---|
| A. Full app on Vercel functions | Wrap `app.py`'s handlers. Run forecasts, AI checks and schedule refreshes on Vercel. | **Rejected.** It needs a writable, shared store for the prediction log and the budget ledger. Without one, each instance keeps its own `/tmp` copy, so budgets are not enforced and locks are lost. Forecasts need the 80 MB+ cricket archive and the model stack (numpy/scipy/sklearn), which means slow cold starts. Most importantly, anyone with the URL could create, replace or grade forecasts and spend OpenRouter and CricketData quota. |
| B. Supabase-backed copy (the existing `api/index.py`) | Forecasts and state stored in Supabase through its anon key. | **Rejected and removed.** The anon key was hard-coded in the repo. `POST /api/openrouter-key` had no authentication, so anyone could replace or clear the key. The key was then stored in a table readable with that public anon key. The budget ledger was also read from and written to that shared table, so anyone holding the key could reset it. Prediction sync pushed only the last 10 entries. |
| **C. Read-only mirror (chosen)** | Same `web/dash.html`, `dash.js` and `dash.css`. The API serves a published snapshot of the owner's schedule and prediction log, plus the free public feeds (F1, World). Every write route answers 403. | **Chosen.** |

## Chosen architecture

```
Browser ──> Vercel CDN ──> /            web/dash.html   (static, CSP header)
                       ──> /dash.js…    web/*           (static, explicit whitelist)
                       ──> /images/…    web/images/*.jpg, web/images/players/*.webp
                       ──> /api/*       api/index.py    (Python function, read-only)
                                          ├─ data/public/today_matches.json   snapshot
                                          ├─ data/public/predictions.json     snapshot (read-only)
                                          ├─ data/public/world_brief.json     snapshot
                                          └─ tools/fetch_world.py, fetch_f1_*.py   free feeds, cached
```

- `vercel.json` uses explicit `builds` and `routes`. This stops Vercel guessing an entrypoint from `app.py`, makes
  `/` serve `web/dash.html`, redirects `/lab` and `/dash` to `/`, and sends any other path to a JSON 404.
  `public/` is deleted, so there is one copy of the front end.
- `api/index.py` imports only `matchlab.tracker` and `matchlab.world`. These are standard library only, about 45 ms
  to import, because `team_key` moved out of the numpy module. `api/requirements.txt` is empty, so the function
  does not install the model stack.
- The function bundle excludes `app.py`, `web/`, `data/raw`, `data/real`, `data/local`, `models/`, docs and tests
  (`excludeFiles`).
- `tools/publish_snapshot.py` copies the three snapshot files into `data/public/`. It refuses anything that looks
  like a key, and writes `meta.json` with `published_at`. The owner runs it, commits and pushes, and Vercel
  redeploys.
- The dashboard detects `/api/session → hosted: true` and changes its behaviour:
  - It labels itself "Public read-only copy · Snapshot from N min ago".
  - It hides Refresh, the budgets and the lab link.
  - Match pages show the saved (locked) forecast, its grade and the saved live checks instead of computing one.
  - Settings shows only Appearance plus "About this copy".

## What is and is not private

| | Local (127.0.0.1) | Hosted mirror |
|---|---|---|
| Who can reach it | This computer only (bound to 127.0.0.1, Host and Origin checked, POST needs a token) | **Anyone with the URL.** No login. |
| Offline guard | On in the server process; network only in short-lived workers | **Not applicable.** The function and its feed workers use the network. |
| Prediction log | Read and written | **Published copy, readable by anyone through the API** (fixtures, saved win chances, grades, live checkpoints; AI texts are reduced to stage, shift and time) |
| OpenRouter key, CricketData key | On this computer (DPAPI, key file) | **Not present.** No key, so no metered call is possible. |
| Budget ledger | `data/local/api_budget.json`, enforced | Not present. There is nothing to meter. |
| `data/` files over HTTP | `/images/` and the dashboard files only | **None.** `data/` is not a static output. `/config.local.json`, `/app.py` and `/data/*` return 404. |

The local guarantees (localhost binding, offline guard, the POST token) do **not** apply to the hosted site, and
the hosted site does not claim them.

## Abuse and quota controls on the hosted site

- **No quota can be drained:** the deployment holds no OpenRouter or CricketData key. All POST, PUT, PATCH and
  DELETE routes return 403 before reading the body beyond 1 MB.
- **Rate limit:** 60 requests per minute per client IP, per instance (`X-Forwarded-For`), then 429 with
  `Retry-After`. This is in-memory, so a determined client spread across instances gets more. If abuse appears,
  add a Vercel Firewall rate-limit rule (owner decision; it is a project setting, not code).
- **Upstream protection:** at most two feed workers per instance. Each feed is cached in memory: F1 for 120 s,
  timing for 20 s, World sections per their own TTL. Every GET also carries `s-maxage` /
  `stale-while-revalidate`, so the Vercel CDN answers repeat requests without invoking the function.

## Trade-offs accepted

- The mirror is **not live** for scores and match states. They are as fresh as the last snapshot, and every view
  says how old it is. Making it live would mean running the ESPN schedule worker on Vercel. That is possible
  without a key (ESPN is free), but it needs a writable store for the result. Left for the owner (see Risks).
- The prediction log becomes public when published. It holds only public sports fixtures and the model's numbers.
  Owner decision.
- `builds` in `vercel.json` is Vercel's older configuration style. It was chosen because it pins the entrypoint and
  the outputs regardless of the project's dashboard settings, which caused this bug.

## Local workflow (unchanged)

`start.cmd`, `start.ps1` and `restart.ps1` still run `app.py` on 127.0.0.1 with the offline guard. The local server
gained only read endpoints (`/api/saved-forecast`, paged `/api/track-record`) and lock marks on the schedule.
`python tools/mirror_preview.py` runs the hosted layout locally on port 8767 to check it before publishing.
