"""MatchLab public mirror: the API behind https://matchlab-ten.vercel.app/.

This is not the owner's MatchLab. It serves the same dashboard (web/dash.html) from a published snapshot of the
owner's saved schedule and prediction log (data/public/, written by tools/publish_snapshot.py), plus the free public
feeds the dashboard reads directly (Formula 1, World Pulse headlines and quotes).

What it never does, by design:
- write anything: the prediction log is read-only (MATCHLAB_READ_ONLY=1), so nobody can add, replace or grade a forecast;
- call a metered service: it holds no OpenRouter or CricketData key, so a public URL cannot spend either daily quota;
- run the models: forecasts, AI checks, briefings and settings are POST routes and all answer 403 here.

It is public. There is no localhost binding and no offline guard here: anyone with the URL sees what it serves.
Abuse is bounded by a per-client rate limit, a cap on concurrent feed workers, and CDN caching of every GET.
"""
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "data" / "public"
os.environ["MATCHLAB_READ_ONLY"] = "1"
os.environ["MATCHLAB_TRACKER_FILE"] = "data/public/predictions.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from matchlab import tennis_forecast, tracker, world  # noqa: E402  (light imports only: no numpy, no models)

READ_ONLY = ("This public copy of MatchLab is read-only. Forecasts, AI checks and settings run on the owner's "
             "computer; this page shows what that MatchLab saved.")
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
       "font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
# Seconds a response may be served from the CDN, then for how long a stale copy may be served while it refreshes.
CDN = {"live": (5, 20), "snapshot": (300, 3600), "f1": (120, 600), "timing": (20, 600), "world": (300, 1800)}
WORKERS = threading.BoundedSemaphore(2)       # feed workers running at once in one instance
LIMIT, WINDOW = 60, 60.0                       # requests per client per minute
_hits, _hits_lock = {}, threading.Lock()
_cache, _cache_lock = {}, threading.Lock()
WORLD = world.Cache()


def _allowed(client):
    now = time.monotonic()
    with _hits_lock:
        recent = [t for t in _hits.get(client, ()) if now - t < WINDOW]
        if len(recent) >= LIMIT:
            _hits[client] = recent
            return False, int(WINDOW - (now - recent[0])) + 1
        recent.append(now)
        _hits[client] = recent
        if len(_hits) > 5000:                    # forget idle clients so the table stays small
            for key in [k for k, v in _hits.items() if not v or now - v[-1] > WINDOW]:
                del _hits[key]
        return True, 0


def _json(name, default=None):
    try:
        return json.loads((PUBLIC / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _meta():
    return _json("meta.json", {}) or {}


def _worker(script, *args, ttl=60, timeout=25):
    """Run one feed reader from tools/ (they print JSON and write nothing), cached for ttl seconds."""
    key = (script, args)
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.monotonic() < hit[0]:
            return hit[1]
    if not WORKERS.acquire(timeout=timeout):
        return hit[1] if hit else None
    try:
        done = subprocess.run([sys.executable, str(ROOT / "tools" / script), *map(str, args)], capture_output=True,
                              encoding="utf-8-sig", timeout=timeout, env={**os.environ, "MATCHLAB_ALLOW_NETWORK": "1"})
        data = json.loads(done.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        data = None
    finally:
        WORKERS.release()
    if data is None and hit:
        return hit[1]
    life = (ttl(data) if callable(ttl) else ttl) if data is not None else 60    # a failing feed is left alone for a minute
    with _cache_lock:
        _cache[key] = (time.monotonic() + life, data)
    return data


def today():
    schedule = _json("today_matches.json") or {"date": "", "sports": {"cricket": [], "tennis": [], "f1": []}, "total_matches": 0, "sources": []}
    tracker.attach_locks(schedule, tracker.locks(ROOT))
    schedule["hosted"] = {"published_at": _meta().get("published_at"), "note": READ_ONLY}
    schedule["budget"] = None
    return schedule


def brief_state():
    saved = _json("world_brief.json")
    ok = isinstance(saved, dict) and saved.get("version") == world.BRIEF_VERSION
    return {"saved": saved if ok else None, "age": None, "ttl": world.BRIEF_TTL, "min_gap": world.BRIEF_MIN_GAP,
            "has_key": False, "hosted": True, "budget": None}


def tennis_live(match_id):
    """The live set score from ESPN's free scoreboard, and the in-play win chance from the saved forecast's serve-point
    model. Read-only: nothing is saved here. Cached for a few seconds so many viewers cost one feed read."""
    if not str(match_id).startswith("tennis-"):
        return None
    schedule = _json("today_matches.json") or {}
    entry = tracker.entry(ROOT, match_id) or {}
    fixture = next((m for m in (schedule.get("sports") or {}).get("tennis") or [] if m.get("id") == match_id), None) or entry.get("fixture")
    if not fixture:
        return None
    tour = "wta" if str(fixture.get("tournament", "")).upper().startswith("WTA") else "atp"
    event, day = str(match_id).rpartition("-")[2], str(fixture.get("start", ""))[:10].replace("-", "")
    if not (event.isdecimal() and day.isdecimal()):
        return None
    intel = _worker("fetch_tennis_intel.py", tour, event, day, timeout=20, ttl=lambda d: 3600 if d.get("state") == "post" else 8)
    if not intel or not intel.get("ok"):
        return {"ok": False, "error": "The live score feed could not be read just now."}
    names = [fixture.get("team"), fixture.get("opponent")]
    intel = tennis_forecast.orient(intel, names)
    pre = entry.get("pre") or {}
    model = pre.get("model")
    teams = pre.get("teams") or []
    if not model and len(teams) == 2 and teams[0].get("win") is not None:
        # Saved before the serve model was stored: rebuild it from the saved win chance and the tour's average serve.
        need = 3 if "5" in str(pre.get("format", "")) else 2
        pa, pb = tennis_forecast.serve_points(teams[0]["win"], 2 * tennis_forecast.SERVE_AVERAGE[tour], need)
        model = {"pa": pa, "pb": pb, "need": need}
    return {"ok": True, "state": intel.get("state"), "status": intel.get("status"), "fetched_at": intel.get("fetched_at"),
            "names": names, "sets": intel.get("sets") or [], "winner": intel.get("winner"),
            "live": tennis_forecast.live_win(model, intel),
            "pre_win": [t.get("win") for t in pre.get("teams") or []] or None}


class handler(BaseHTTPRequestHandler):
    server_version = "MatchLab-mirror"

    def log_message(self, format, *args):
        pass

    def _client(self):
        forwarded = self.headers.get("X-Forwarded-For", "")
        return (forwarded.split(",")[0].strip() or self.headers.get("X-Real-Ip") or self.client_address[0] or "?")[:64]

    def _send(self, code, payload, cdn=None, extra=None):
        body = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")
        etag = '"' + hashlib.sha1(body).hexdigest()[:20] + '"'
        if code == 200 and self.headers.get("If-None-Match") == etag:
            code, body = 304, b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if cdn and code in (200, 304):
            fresh, stale = CDN[cdn]
            self.send_header("Cache-Control", f"public, max-age=0, s-maxage={fresh}, stale-while-revalidate={stale}")
            self.send_header("ETag", etag)
        else:
            self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _tennis_live(self, match_id):
        data = tennis_live(match_id)
        return self._send(200, data, cdn="live") if data else self._send(404, {"error": "No tennis match with that id."})

    def do_GET(self):
        ok, retry = _allowed(self._client())
        if not ok:
            return self._send(429, {"error": f"Too many requests. Try again in {retry} seconds."}, extra={"Retry-After": str(retry)})
        parts = urlsplit(self.path)
        route, query = parts.path.rstrip("/") or "/", parse_qs(parts.query)
        arg = lambda name, default="": (query.get(name) or [default])[0]  # noqa: E731
        if route == "/api/health":
            return self._send(200, {"ok": True, "hosted": True, "published_at": _meta().get("published_at")})
        if route == "/api/session":
            return self._send(200, {"token": "", "offline": False, "hosted": True, "read_only": True, "note": READ_ONLY,
                                    "published_at": _meta().get("published_at"), "openrouter_key_status": "missing"})
        if route == "/api/today-matches":
            return self._send(200, today(), cdn="snapshot")
        if route == "/api/track-record":
            sport = arg("sport")
            if sport:
                if sport not in ("cricket", "tennis", "f1"):
                    return self._send(400, {"error": "Choose cricket, tennis or f1."})
                try:
                    offset = max(0, int(arg("offset", "0")))
                except ValueError:
                    return self._send(400, {"error": "Offset must be a whole number."})
                return self._send(200, tracker.record_rows(ROOT, sport, offset), cdn="snapshot")
            record = tracker.track_record(ROOT)
            return self._send(200, {**record, "grading": False, "pending": 0, "published_at": _meta().get("published_at")}, cdn="snapshot")
        if route == "/api/saved-forecast":
            entry = tracker.entry(ROOT, arg("id"))
            return self._send(200, tracker.public_entry(entry), cdn="snapshot") if entry else self._send(404, {"error": "No forecast was saved for this event."})
        if route == "/api/tennis-live":
            return self._tennis_live(arg("id"))
        if route == "/api/world-brief":
            return self._send(200, brief_state(), cdn="snapshot")
        if route == "/api/world":
            name = arg("section")
            if name not in world.TTL:
                return self._send(400, {"error": "Choose markets, news, models or sports."})
            data = world.serve(name, lambda section: _worker("fetch_world.py", section, ttl=world.TTL[name], timeout=40) or {"error": "This feed is unavailable right now."}, WORLD)
            return self._send(200, data, cdn="world")
        if route == "/api/f1-dashboard":
            data = _worker("fetch_f1_dashboard.py", ttl=120, timeout=38)
            return self._send(200, data, cdn="f1") if data is not None else self._send(503, {"error": "Formula One data is unavailable. Please try again."})
        if route == "/api/f1-timing":
            try:
                season, round_number = int(arg("season")), int(arg("round"))
                if not (1950 <= season <= 2100 and 1 <= round_number <= 30):
                    raise ValueError()
            except ValueError:
                return self._send(400, {"error": "Choose a season and round."})
            data = _worker("fetch_f1_timing.py", season, round_number, timeout=40,
                           ttl=lambda d: 3600 if d.get("state") == "post" and d.get("laps") else 20)   # a finished race does not change
            return self._send(200, data, cdn="timing") if data is not None else self._send(503, {"error": "Lap timing is temporarily unavailable."})
        return self._send(404, {"error": "Not found"})

    def do_POST(self):
        size = int(self.headers.get("Content-Length") or 0)
        if 0 < size <= 1_000_000:
            self.rfile.read(size)
        return self._send(403, {"error": READ_ONLY, "hosted": True})

    def do_PUT(self):
        return self.do_POST()

    do_DELETE = do_PATCH = do_PUT
