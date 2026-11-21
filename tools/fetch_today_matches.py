"""Fetch today's scheduled, live and finished matches from public scoreboards.

Runs on demand (dashboard "Check updates") or before starting MatchLab. Returns
real fixtures only: a sport with no fixtures, or whose source failed, stays
empty and the failure is recorded under "sources". Nothing is invented.

"Today" is the local calendar day of this machine. Fixtures are kept when they
start today (local time) or are in progress right now (e.g. a multi-day Test).
"""
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from matchlab import budget  # noqa: E402
from matchlab.cricket_sim import team_key  # noqa: E402
OUTPUT_FILE = ROOT / "data" / "today_matches.json"
CRICKETDATA_KEY_FILE = ROOT / "data" / "local" / "cricketdata.key"
BASE = "https://site.api.espn.com/apis/site/v2/sports"
CRICKET_URL = "https://site.web.api.espn.com/apis/personalized/v2/scoreboard/header?sport=cricket&lang=en"
CRICKETDATA_URL = "https://api.cricapi.com/v1/currentMatches"
CRICKETDATA_SCOREBOARD = "https://cricketdata.org/cricket-data-formats/matches/"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
TIMEOUT = 10
SPORTS = ["cricket", "tennis", "f1"]
AHEAD = timedelta(hours=30)  # also list fixtures starting within this window

# (sport, label, path, parser). Team scoreboards share one layout; tennis nests
# matches inside tournaments.
SCOREBOARDS = [
    ("tennis", "ATP", "tennis/atp", "tennis"),
    ("tennis", "WTA", "tennis/wta", "tennis"),
    ("f1", "Formula 1", "racing/f1", "race"),
]


def get_json(url):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_time(value):
    """Scoreboard timestamps are UTC, with or without seconds."""
    text = str(value or "").replace("Z", "+00:00")
    try:
        when = datetime.fromisoformat(text)
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def keep(start, state, today):
    if state == "in" or start is None:
        return state == "in"
    soon = state == "pre" and datetime.now(timezone.utc) <= start <= datetime.now(timezone.utc) + AHEAD
    return start.astimezone().date() == today or soon


def record(sport, mid, tournament, home, away, start, state, status, venue, home_score="", away_score="", detail=""):
    return {"id": f"{sport}-{mid}", "sport": sport, "tournament": tournament, "team": home, "opponent": away,
            "team_score": str(home_score or ""), "opponent_score": str(away_score or ""),
            "start": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if start else "",
            "state": state if state in ("pre", "in", "post") else "pre", "status": status or "Scheduled",
            "venue": venue or "", "detail": detail or ""}


def parse_team_board(sport, label, data, today):
    league = (data.get("leagues") or [{}])[0].get("name") or label
    found = []
    for event in data.get("events", []):
        comp = (event.get("competitions") or [{}])[0]
        sides = comp.get("competitors") or []
        if len(sides) != 2:
            continue
        home = next((s for s in sides if s.get("homeAway") == "home"), sides[0])
        away = next((s for s in sides if s is not home), sides[1])
        names = [(s.get("team") or {}).get("displayName") for s in (home, away)]
        if not all(names):
            continue
        kind = (event.get("status") or {}).get("type") or {}
        start, state = parse_time(event.get("date")), kind.get("state", "pre")
        if not keep(start, state, today):
            continue
        scored = state != "pre"
        found.append(record(sport, event.get("id"), league, names[0], names[1], start, state,
                            kind.get("shortDetail") if state == "in" else kind.get("description"),
                            (comp.get("venue") or {}).get("fullName"),
                            home.get("score") if scored else "", away.get("score") if scored else ""))
    return found


def parse_tennis(sport, label, data, today):
    found = []
    for event in data.get("events", []):
        for group in event.get("groupings", []):
            draw = (group.get("grouping") or {}).get("displayName", "")
            if "Singles" not in draw:
                continue
            for comp in group.get("competitions", []):
                names = [(s.get("athlete") or {}).get("displayName") for s in comp.get("competitors") or []]
                if len(names) != 2 or not all(names):
                    continue  # draw slot not decided yet
                kind = (comp.get("status") or {}).get("type") or {}
                start, state = parse_time(comp.get("date")), kind.get("state", "pre")
                if not keep(start, state, today):
                    continue
                venue = comp.get("venue") or {}
                place = ", ".join(x for x in (venue.get("court"), venue.get("fullName")) if x)
                found.append(record(sport, comp.get("id"), f"{label} · {event.get('name', '')}", names[0], names[1], start, state,
                                    kind.get("description"), place, detail=(comp.get("round") or {}).get("displayName", "")))
    return found


def parse_cricket(data, today):
    found = []
    for sport_block in data.get("sports", []):
        for league in sport_block.get("leagues", []):
            for event in league.get("events", []):
                sides = event.get("competitors") or []
                if len(sides) != 2:
                    continue
                home = next((s for s in sides if s.get("homeAway") == "home"), sides[0])
                away = next((s for s in sides if s is not home), sides[1])
                if not home.get("displayName") or not away.get("displayName"):
                    continue
                state = ((event.get("fullStatus") or {}).get("type") or {}).get("state") or event.get("status") or "pre"
                start = parse_time(event.get("date"))
                if not keep(start, state, today):
                    continue
                form = (event.get("class") or {}).get("generalClassCard", "")
                match = record("cricket", event.get("id"), league.get("name", "Cricket").strip(), home["displayName"], away["displayName"],
                               start, state, event.get("summary"), event.get("location"),
                               home.get("score"), away.get("score"), detail=form)
                match["espn"] = {"league": str(league.get("id") or ""), "event": str(event.get("id") or "")}
                found.append(match)
    return found


class BudgetSpent(Exception):
    pass


def fetch_cricketdata(today):
    key = os.environ.get("CRICKETDATA_API_KEY", "").strip()
    if not key:
        try:
            from matchlab.openrouter_key import env_file_value
            key = env_file_value("CRICKETDATA_API_KEY")
        except Exception:
            pass
    if not key and CRICKETDATA_KEY_FILE.is_file():
        try:
            key = CRICKETDATA_KEY_FILE.read_text(encoding="utf-8-sig").strip()
        except OSError:
            key = ""
    if not key:
        return None

    cache = budget.Cache(ROOT, "cricketdata_current")
    events = cache.get(budget.refresh_interval(ROOT))
    if events is None:
        if not budget.spend(ROOT, "cricketdata", "fixture list"):
            raise BudgetSpent()
        query = urlencode({"apikey": key, "offset": 0})
        response = get_json(f"{CRICKETDATA_URL}?{query}")
        info = response.get("info") or {}
        budget.sync(ROOT, "cricketdata", info.get("hitsToday"), info.get("hitsLimit"))
        events = response.get("data")
        if response.get("status") != "success" or not isinstance(events, list):
            raise ValueError("CricketData.org did not return a match list")
        cache.put(events)

    found = []
    for event in events:
        teams = event.get("teams") or []
        start = parse_time(event.get("dateTimeGMT"))
        if not event.get("id") or len(teams) != 2 or not all(teams) or start is None:
            continue
        state = "pre"
        if event.get("matchEnded") is True:
            state = "post"
        elif event.get("matchStarted") is True:
            state = "in"
        if not keep(start, state, today):
            continue

        scores, lines = {}, []
        for innings in event.get("score") or []:
            team, separator, _ = (innings.get("inning") or "").rpartition(" Inning ")
            runs, wickets = innings.get("r"), innings.get("w")
            if separator and runs is not None and wickets is not None:
                scores.setdefault(team.strip().casefold(), []).append(f"{runs}/{wickets}")
                lines.append({"team": team.strip(), "runs": runs, "wickets": wickets, "overs": innings.get("o")})
        home, away = teams
        match = record("cricket", f"cricapi-{event['id']}", event.get("name") or "Cricket",
                       home, away, start, state, event.get("status"), event.get("venue"),
                       " & ".join(scores.get(home.casefold(), [])),
                       " & ".join(scores.get(away.casefold(), [])), detail=event.get("matchType"))
        match["source_url"] = CRICKETDATA_SCOREBOARD
        match["innings"] = lines
        found.append(match)
    return found


def fetch_cricket(today):
    """CricketData.org (metered, cached) merged with ESPN (free). ESPN adds the match
    summary link used for the toss, playing XIs and live scores."""
    sources, listed = [], []
    try:
        listed = fetch_cricketdata(today)
    except BudgetSpent:
        sources.append({"sport": "cricket", "name": "CricketData.org", "ok": True, "matches": 0,
                        "error": "Daily request budget reached; using ESPN only until it resets (midnight UTC)."})
    except Exception:
        # The request URL and provider response can contain the key.
        sources.append({"sport": "cricket", "name": "CricketData.org", "ok": False, "matches": 0,
                        "error": "Check the CricketData.org key, daily quota, and connection."})
    else:
        if listed is not None:
            sources.append({"sport": "cricket", "name": "CricketData.org", "ok": True, "matches": len(listed), "error": None})
    listed = listed or []
    try:
        espn = parse_cricket(get_json(CRICKET_URL), today)
        error = None
    except Exception as exc:
        espn, error = [], f"{type(exc).__name__}: {exc}"
    sources.append({"sport": "cricket", "name": "ESPN Cricket", "ok": error is None, "matches": len(espn), "error": error})

    def pair(match):
        return frozenset(team_key(match[k]) for k in ("team", "opponent"))

    progression = {"pre": 0, "in": 1, "post": 2}
    for match in espn:
        start = parse_time(match["start"])
        twin = next((m for m in listed if start is not None and "espn" not in m and pair(m) == pair(match)
                     and abs(parse_time(m["start"]) - start) < timedelta(hours=36)), None)
        if twin is None:
            listed.append(match)
        else:
            twin["espn"] = match["espn"]
            twin["espn_class"] = match["detail"]
            twin["venue"] = twin["venue"] or match["venue"]
            # CricketData may still be cached when ESPN reports play or a result.
            if progression[match["state"]] > progression[twin["state"]]:
                scores = {team_key(match[side]): match[f"{side}_score"] for side in ("team", "opponent")}
                twin.update(state=match["state"], status=match["status"], innings=[],
                            team_score=scores[team_key(twin["team"])],
                            opponent_score=scores[team_key(twin["opponent"])])
    return listed, sources


def parse_racing(sport, label, data, today):
    found = []
    for event in data.get("events", []):
        for comp in event.get("competitions", []):
            if (comp.get("type") or {}).get("abbreviation", "").lower() != "race":
                continue
            kind = (comp.get("status") or {}).get("type") or {}
            start, state = parse_time(comp.get("date")), kind.get("state", "pre")
            if start is None or not keep(start, state, today):
                continue
            venue = (comp.get("venue") or event.get("venue") or {}).get("fullName")
            found.append(record(sport, comp["id"], label, event["name"], "", start, state,
                                kind.get("description"), venue, detail="Grand Prix"))
    return found


def fetch_scoreboard(job, today):
    sport, label, path, parser = job
    seen = {}
    # The scoreboard's own day boundary is not this machine's: ask for the
    # neighbouring days too, then keep only fixtures that are really today here.
    for offset in (-1, 0, 1):
        day = (today + timedelta(days=offset)).strftime("%Y%m%d")
        data = get_json(f"{BASE}/{path}/scoreboard?dates={day}")
        parse = {"tennis": parse_tennis, "race": parse_racing, "team": parse_team_board}[parser]
        parsed = parse(sport, label, data, today)
        for match in parsed:
            seen[match["id"]] = match
    return list(seen.values())


def fetch_matches(now=None):
    today = (now or datetime.now().astimezone()).date()
    schedule = {sport: [] for sport in SPORTS}
    sources = []

    def run(job):
        try:
            return job, fetch_scoreboard(job, today), None
        except Exception as exc:  # recorded per source; never hidden
            return job, [], f"{type(exc).__name__}: {exc}"

    with ThreadPoolExecutor(max_workers=8) as pool:
        cricket_job = pool.submit(fetch_cricket, today)
        for (sport, label, _, _), matches, error in pool.map(run, SCOREBOARDS):
            schedule[sport].extend(matches)
            sources.append({"sport": sport, "name": label, "ok": error is None, "matches": len(matches), "error": error})
        matches, cricket_sources = cricket_job.result()
        schedule["cricket"] = matches
        sources.extend(cricket_sources)

    order = {"in": 0, "pre": 1, "post": 2}
    for matches in schedule.values():
        matches.sort(key=lambda m: (order[m["state"]], m["start"], m["id"]))
    everything = [m for matches in schedule.values() for m in matches]
    reachable = any(s["ok"] for s in sources)
    failed = [s["name"] for s in sources if not s["ok"]]
    total = len(everything)
    if not reachable:
        status = "Could not reach any schedule source; check the internet connection"
    elif total:
        status = f"{total} matches today"
    else:
        status = "No matches found for today"
    payload = {
        "date": today.isoformat(),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "connected_to_internet": reachable,
        "status": status,
        "total_matches": total,
        "counts": {state: sum(m["state"] == state for m in everything) for state in ("in", "pre", "post")},
        "failed_sources": failed,
        "sources": sources,
        "budget": budget.status(ROOT),
        "sports": schedule,
    }
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(OUTPUT_FILE)
    return payload


if __name__ == "__main__":
    result = fetch_matches()
    print(f"{result['date']}: {result['status']}")
    for sport, matches in result["sports"].items():
        live = sum(m["state"] == "in" for m in matches)
        print(f"  {sport:10s} {len(matches):3d} matches ({live} live)")
    for source in result["sources"]:
        if not source["ok"]:
            print(f"  ! {source['name']}: {source['error']}")
    print(f"Saved to {OUTPUT_FILE}")
