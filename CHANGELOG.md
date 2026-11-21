# Changelog

## 2026-11-21

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
