# MatchLab UI audit

Two passes are recorded here. **Pass 2** (below) is the current one: it audits the dashboard as it stood at
`3dd42a1`, after Pass 1's fixes landed, plus the hosted site. **Pass 1** is kept underneath as history; its items
were fixed in commits `ada9b61` to `cea792c`.

---

# Pass 2: 2026-11-21, hosted site, Track Record, photos, product focus

Scope: `web/dash.*`, `app.py`, `api/index.py`, `vercel.json`, `matchlab/tracker.py`, `matchlab/ai_check.py`,
`matchlab/world.py`, the owner's new portraits. Method: source read. Both sites driven with headless Chromium at 360,
768, 1280 and 1920 px (`tools/ui-checks/capture.cjs`; screenshots in `docs/screens/before/{live,local}/` and
`docs/screens/after/{live,local}/`). Three-theme contrast sweep (`tools/ui-checks/contrast.cjs`), a scripted
keyboard walk, and an independent recomputation of every Track Record number (`tools/verify_track_record.py`).

Specialists: **UX** senior UI/UX designer, **FE** front-end, **BE** back-end, **FS** full-stack, **PM** product,
**ML** AI engineer, **GenAI** Gen-AI engineer. Status: **Fixed** (in this pass, with commit), **Open** (owner decision
or later work).

## Critical

| ID | Area | Finding | Status |
|---|---|---|---|
| P2-C1 | Hosting (FS) | The public URL showed the legacy lab at `/` and `/lab`. `/dash` showed "MatchLab could not start" at every width, because every `/api/*` call returned 403 from `app.py`'s localhost guard. Root cause in `hosting-decision.md`. Evidence: `docs/screens/before/live/*`, `log.json`. | **Fixed** `07798e5`, `580b804` |
| P2-C2 | Security (BE) | `matchlab/supabase_db.py` hard-coded a Supabase key. The unused `api/index.py` let anyone save or clear the OpenRouter key and stored it in a table that key can read. The API budget ledger was read and written in that table, so anyone could reset the count and drain quotas. | **Fixed** `0bebd08`, `07798e5`. **Open**: rotate the key and check RLS (owner) |
| P2-C3 | Performance (BE) | `/api/track-record` graded pending events before replying: 2,352 ms measured, up to about 12 s with six pending. | **Fixed** `b0e5e3c` |

## Major

| ID | Area | Finding | Status |
|---|---|---|---|
| P2-M1 | Product (PM, UX) | The owner's main question, "is this forecast locked?", needed a click into each match. The card said "Forecast ready" whether or not anything was saved. | **Fixed** `81ff745`: "Locked 6:14 PM" badge and the locked pick on the card; "Not locked yet" otherwise |
| P2-M2 | Honesty (BE) | A failed save of the prediction log was swallowed (`except Exception: pass`), so the page could show a forecast as locked that was never written. | **Fixed** `b0e5e3c`: a failed write raises and the forecast request reports it |
| P2-M3 | Track Record (ML) | "Winner with AI check" and "Winner picked" used different samples with no like-for-like comparison. | **Fixed**: the AI rate now shows "model alone on the same n" |
| P2-M4 | Track Record (ML, UX) | No calibration view: only a sentence saying calibration is not active. | **Fixed**: reliability table (5 bins, n per bin, average chance vs observed) |
| P2-M5 | Track Record (FE) | Every saved row drawn at once (100 per sport, sent twice); the view was blank text until the reply. | **Fixed**: skeleton, 25 rows plus "Show more", in-place update after background grading |
| P2-M6 | GenAI (BE) | A stored AI check's shift was applied without the ±5 cap (only new replies were capped). | **Fixed** `d7acbdf`, test added |
| P2-M7 | Images (UX, FE) | The owner's 20 portraits were 1.8–2.0 MB PNGs (38 MB). The F1 ones print a ranking and team ("#1 – Lando Norris (McLaren)") that goes stale. | **Fixed** `61d14f2`: WebP 2–25 KB each, caption strip cropped |
| P2-M8 | Formula 1 (UX) | The hub had only text tables: no driver imagery, and the leader card did not say by how much he leads. | **Fixed**: leader portrait, gap to P2, top-six driver cards with faces |
| P2-M9 | Hosted copy (UX) | Copy written for the local app ("press Refresh", "Check that MatchLab is still running in its terminal window", "Add an OpenRouter key") is wrong on a public read-only site. | **Fixed**: hosted wording throughout; Settings explains the copy |
| P2-M10 | Status (PM) | On the hosted copy, match states (Live / Finished) and scores are only as fresh as the last snapshot, so a finished match can still read "Live" hours later. | **Mitigated**: every view says "Snapshot from N min ago", and past 60 minutes "Scores and match states may be out of date". **Open**: a live schedule on the host (see Risks) |

## Minor

| ID | Finding | Status |
|---|---|---|
| P2-m1 | A disabled "Checking…" button faded to 2.36:1 (Butter) and 2.88:1 (Chocolate). Disabled controls are exempt in WCAG, but this one carries status. | **Fixed** `7b2d804` |
| P2-m2 | The F1 Track Record rows and the F1 hub linked to `/lab`, which the hosted site no longer serves. | **Fixed** on the hosted copy (links to `#f1`); kept locally, where the race forecast lives |
| P2-m3 | Coin-flip forecasts (50.1% v 49.9%) are graded as winner picks: 2 of the 5 correct cricket picks are coin flips. The page is honest (the 50–60% bin shows 3 of 7), but the headline rate includes them. | **Open**, owner decision: changing grading changes the record |
| P2-m4 | Astryx references `--spacing-1…4` but never defines them, so those declarations do nothing. New code uses `--ml-s1…4` (4/8/12/16 px). Defining the Astryx tokens globally would move existing layouts. | **Open** (needs its own visual pass) |
| P2-m5 | Four web fonts are shipped (Outfit, Figtree, Albert Sans, Fraunces). Each theme uses two (heading plus body), so the two-per-theme rule holds. `font-display: swap` with the default font preloaded. | Pass, no change |
| P2-m6 | Contrast over photographs (hero eyebrows and headlines over the F1 and Track Record photos) cannot be computed from CSS. The sweep flags them as "unknown". Screenshots show light text over a dark overlay in all themes. | Pass by inspection |
| P2-m7 | The footer link "Open the older lab view" competes with the dashboard. | **Fixed** on hosted (removed); kept locally for the F1 race forecast |

## Checks that pass (measured)

- **Keyboard**: skip link, logo, 5 nav links, Refresh, 4 filter chips (Enter toggles, focus stays, `aria-pressed`
  updates), search, then cards. Track Record chips, then table links. Settings: theme select first. Every stop
  shows a 3 px outline. On route change, focus moves to the new `h1`.
- **Console and CSP**: no errors or CSP violations at any width on either site after the fix. Image, font and
  feed origins are unchanged; no new external origin.
- **Contrast (WCAG 2.2 AA)**: after P2-m1, zero computed failures in Butter, Neutral and Chocolate across Matches,
  match detail, World, F1, Track Record and Settings (`artifacts/contrast-after.json`). Only over-photo text is unknown.
- **Tabular numerals**: scores (`.teams b`), pick and win percentages (`.num`), Track Record cells, calibration
  table, F1 points and positions.
- **Motion**: the skeleton pulse is opacity only and stops under `prefers-reduced-motion`. No new continuous motion.
  Values on the 12 s / 25 s polls are patched in place by the existing keyed morph, with one brief highlight on a
  real change.
- **Live regions**: one polite region with deliberate messages only. A score change is announced once per poll, and
  only when the score text differs.
- **Images**: `srcset` + `sizes`, explicit `width` / `height`, `loading="lazy"` except the first four tennis cards,
  `decoding="async"`, initials fallback on missing or failed images (no broken-image icon, no shift). `alt=""` on
  faces next to a visible name; "Illustrated portrait of …" on standalone portraits.
- **Watermarks**: none. The 20 portraits are stylised illustrations, not agency photos; no press or agency marks
  were found. They are likenesses of real athletes: whether you may publish them is your decision (Risks).

## Product focus (PM)

The owner's main task is "what is on today, and is each forecast locked?" The shortest path is now the Matches view:
each card answers it without a click (lock badge with time, locked pick). On the hosted copy, opening a card shows
only the saved forecast and its grade. Removed or demoted: on the hosted copy, Refresh, budget chips, the lab link,
the OpenRouter key form and every action that would compute or spend. Kept locally: the older lab view, because the
F1 race forecast still lives there.

---

# Pass 1 (history)

Date: 2026-11-21. Scope: `web/dash.html`, `web/dash.js`, `web/dash.css`, `app.py`, `matchlab/world.py`.
Method: source read, then the live app on `127.0.0.1:8766` driven with headless Chromium at 360, 768, 1280 and
1920 px for all five views plus a match detail page, and a three-theme computed-contrast sweep.

Evidence (local only; `artifacts/` is git-ignored):

- Screenshots: `artifacts/ui-audit/before/<view>-<width>.png`, `theme-<theme>-<view>.png`
- Contrast data: `artifacts/ui-audit/before/contrast.json`
- Overflow and console log: `artifacts/ui-audit/before/log.json` (no console errors, no CSP violations in any view)

Specialist tags: **UX** senior UI/UX, **FE** front-end, **BE** back-end, **PM** product, **ML** AI/ML, **GenAI**.

Limits of this audit: the schedule data is a saved snapshot, so I saw live, upcoming and finished cards but did not
capture a genuine empty feed or a feed outage from real data; those states are exercised through route stubs in the
verification step. Contrast for text over photographs cannot be computed from CSS alone, so those items are judged
from screenshots. A sweep also reported 44 cards at `opacity:0`; that was an artefact of an animation clock that was
not running (a hidden pane) and of animations replaying after the 5-minute refresh. I treat it as one finding
(F-12, replayed entrance animation), not as invisible content.

## Critical

| ID | Area | Finding | Where |
|---|---|---|---|
| C-1 | Honesty (PM, ML) | The World terminal shows **invented market data as if it were real**: a hard-coded "Order Flow & Analyst Consensus" (Strong Buy, Buy 84% / Hold 13% / Sell 3%, from a fixed table with a made-up fallback), bid/ask prices computed as `price × 0.9996/1.0004` with invented sizes, a literal "Spread $0.06 (0.07%)", invented beta, candlesticks whose open/high/low are synthesised from the close series, volume bars derived from price change, and a "REGULAR TRADING" badge that is always on. Nothing in `tools/fetch_world.py` supplies these fields. The timeframe buttons (1D…ALL) only slice the same 5-session series. Moving averages labelled "SMA 9/21" use periods 5 and 9. | `web/dash.js:1074-1081, 1110-1116, 1171-1173, 1204-1230, 1240-1241, 1250-1253, 1324-1352` |
| C-2 | Honesty | The "live" price is made to **flicker with `Math.random()`** every 3.8 s around the last fetched quote and flashes green or red. It looks like a live feed and is noise. | `web/dash.js:1712-1730` |
| C-3 | Hard-coded facts | `F1_GRID_CARS` hard-codes a 2024 grid (chassis, drivers, engines, aero notes) under the heading "THE 2024–2026 GRID". It is stale (Bottas/Zhou at Sauber, Pérez at Red Bull). Five of ten teams reuse generic photos (Ferrari and Mercedes use the F1 hero, McLaren, Williams and Haas use the grid line-up). Violates the rule against hard-coding time-sensitive facts. | `web/dash.js:888-899, 926` |
| C-4 | Accessibility | `<main aria-live="polite">` wraps the whole app. Every `show()` call (each search keystroke, each 12 s match poll, each refresh) replaces the whole region, so a screen reader re-reads the page. Focus is also not moved on route change. | `web/dash.html:25`, `web/dash.js:60-65, 1847-1861` |
| C-5 | Contrast | Track record hero: the first headline line uses the theme ink colour over a fixed dark overlay (dark on dark, unreadable in all themes); the eyebrow and body copy are muted on the same overlay. | `web/dash.css:1292-1301`, `before/record-1280.png` |
| C-6 | Track record honesty | Hero says "**Verified accuracy & rigor** … Every probability is mathematically calibrated" and shows **31 tracked forecasts**. The list holds forecasts opened after start, and calibration is explicitly not applied until 30 graded forecasts exist (9 today). The headline number mixes qualifying and excluded forecasts. | `web/dash.js:760-769`, `before/record-1280.png` |

## Major

| ID | Area | Finding | Where |
|---|---|---|---|
| M-1 | Perf | Dashboard waits on `/api/state`, a **3.6 MB** payload (full catalogue and configs) that it only uses for `token` and `openrouter_key_status`. It gates first paint. | `web/dash.js:1865`, `app.py:433-438` |
| M-2 | Perf | Every static response, including fonts and 800 KB photos, is sent with `Cache-Control: no-store`. Fonts refetch on every load, which is the real cause of font-swap flashes. | `app.py:422` |
| M-3 | Images | Match-card thumbnails are 38×38 px but load the 1376×768 ~800 KB hero JPEG; 44 cards share three files. No `width`/`height` (layout shift), no `srcset`, and `alt` repeats the sport name on a decorative image next to text that already says the sport. Hero tiles and venue banners are generic stock art that carry no match information. | `web/dash.js:116-126, 155-179, 555, 593, 931` |
| M-4 | Motion | Probability bars, set-score bars and win bars animate **`width`** (layout) and restart from 0 on every poll; the `bar-sweep` shimmer runs forever. `range-pin` animates `left`; the search box animates `width` on focus; `transition: all` on several controls; `will-change` on every button, chip and card. | `web/dash.css:347, 374-379, 461, 608, 942-944, 1047, 1130, 342-352` |
| M-5 | Motion | Live tag pulse animates **`box-shadow`** (paint) on every live card, plus a glowing top bar, so a page with 30 live cards runs **60 infinite animations** (measured: 110 running, 60 infinite). | `web/dash.css:283, 361-362` |
| M-6 | Motion | Hero counters re-count from 0 and the card cascade replays on every re-render (search keystroke, filter, 5-minute refresh, manual refresh). Data-driven motion should play on first reveal only. | `web/dash.js:36-59, 180-187`, `web/dash.css:276` |
| M-7 | Architecture | Whole-view re-render: `show()` rebuilds the DOM for search, filters, refresh, and every 12 s match poll. The match page patches focus, scroll and `<details>` state back by hand. The search box re-renders per keystroke with no debounce and restores the caret manually. | `web/dash.js:60-65, 153-154, 612-702` |
| M-8 | Accessibility | Ticker tape auto-scrolls for ever (36 s loop) with no pause control and **duplicates every quote as a focusable button** (`quotes.concat(quotes)`), doubling tab stops. | `web/dash.js:1118-1138`, `web/dash.css:439` |
| M-9 | Hierarchy | On a match in play, the live win chance, the number the reader came for, is about 1,000 px down the page, below the full pre-match panel. The scoreboard repeats the same teams twice. | `web/dash.js:604-609`, `before/match-detail-1280.png` |
| M-10 | IA | The Matches view puts a three-card sports showcase (duplicating the filter chips) between the hero and the schedule, then lists all 30 live cards flat. At 360 px the page is ~13,800 px tall; "Coming up" is far below the fold. | `web/dash.js:155-179, 188-202`, `before/matches-360.png` |
| M-11 | GenAI | Briefing citation checks: bullets with no valid reference are dropped **silently** (the reader is not told); the **headline is never cited or checked**; a non-JSON reply is shown as free **uncited prose**; a valid id is not checked against the claim, so invented numbers pass. | `matchlab/world.py:381-410`, `web/dash.js:1798-1802` |
| M-12 | Contrast | Chocolate: `tag.live` 3.37:1, `tag.ok` 3.3:1, down pills 3.4–4.1:1, `f1-label` 3.8:1. Butter: chip counts 3.62:1. Divider glyph in the utility bar 1.3–3.1:1 in all themes. | `before/contrast.json` |
| M-13 | Responsive | Formula 1 view overflows horizontally at 360 px (scroll width 391). | `before/log.json` |
| M-14 | Stale data | "Last checked 4:30 PM" is static text: no age, no warning when the schedule is old, and the budget chips never show when a feed last succeeded. Failures appear as a plain note. | `web/dash.js:195-199`, `web/dash.js:80-90` |

## Minor

| ID | Finding | Where |
|---|---|---|
| m-1 | Fonts: `font-display: swap` with a generic system fallback that is not metric-matched; no preload. | `web/dash.css:1-4`, `web/dash.html` |
| m-2 | Static path guard uses a string prefix (`startswith`) instead of a path-relative check. | `app.py:483` |
| m-3 | Track record table shows favourite percentages and hit rates without n beside them; there is no calibration view; the sport chip counts mean "saved" while the figures mean "graded". | `web/dash.js:711-748` |
| m-4 | Both team colours on win bars differ only by hue (blue vs brown); the label order carries meaning but the colour alone is the key. | `web/dash.css:258` |
| m-5 | Market terminal hard-codes "EST" next to a locale-formatted time; `as_of` is not an EST value. | `web/dash.js:1278` |
| m-6 | `public/` duplicates `web/` for the cloud deployment and can drift (already differs in `app.js`). | `public/` |
| m-7 | The World briefing generates automatically when the tab opens if a key exists, spending the OpenRouter quota without a click. It is budget-gated, so the limit holds, but it is a spend the reader did not ask for. | `web/dash.js:1815-1822` |
| m-8 | `start.ps1` serves on 8766 but `app.py` defaults to 8765. | `start.ps1`, `app.py:703` |

## What already works (keep)

No console errors or CSP violations in any view. Skip link, labelled search, pressed-state chips, 44 px buttons and
visible focus exist. Theme choice persists. Text from feeds is inserted with `textContent` / `createTextNode`.
The `saved_before_start` rule is applied by the backend and shown as "Opened after start".
