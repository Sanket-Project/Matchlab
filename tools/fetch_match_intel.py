"""Fetch one cricket match's toss, playing XIs, venue and live score from ESPN.

python tools/fetch_match_intel.py <league id> <event id>   -> JSON on stdout
Free and unmetered. Runs as a short-lived process so the dashboard server stays offline.
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone

URL = "https://site.web.api.espn.com/apis/site/v2/sports/cricket/{league}/summary?event={event}"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
WANTED = {"runs", "ballsFaced", "batted", "battingPosition", "wickets", "overs", "conceded", "bowled", "outs"}


def player_stats(player):
    stats = {}
    for period in player.get("linescores") or []:
        row = {}
        for line in period.get("linescores") or []:
            for category in (line.get("statistics") or {}).get("categories") or []:
                for stat in category.get("stats") or []:
                    if stat.get("name") in WANTED and isinstance(stat.get("value"), (int, float)):
                        row[stat["name"]] = stat["value"]
        if row.get("batted") or row.get("bowled"):
            stats[str(period.get("period"))] = row
    return stats


def summarize(data):
    header = (data.get("header") or {}).get("competitions") or [{}]
    comp = header[0]
    status = comp.get("status") or {}
    kind = status.get("type") or {}
    venue = (data.get("gameInfo") or {}).get("venue") or {}
    address = venue.get("address") or {}
    rosters = {str((r.get("team") or {}).get("id")): r.get("roster") or [] for r in data.get("rosters") or []}
    teams = []
    for side in comp.get("competitors") or []:
        team = side.get("team") or {}
        roster = rosters.get(str(side.get("id")), [])
        starters = [p for p in roster if p.get("starter")] or roster
        teams.append({
            "id": str(side.get("id")), "name": team.get("displayName") or "", "score": side.get("score") or "",
            "winner": str(side.get("winner")).lower() == "true",
            "innings": [{"period": line.get("period"), "runs": line.get("runs"), "wickets": line.get("wickets"),
                         "overs": line.get("overs"), "target": line.get("target") or 0, "current": bool(line.get("isCurrent"))}
                        for line in side.get("linescores") or [] if line.get("isBatting")],
            "xi": [{"id": str((p.get("athlete") or {}).get("id") or ""), "name": (p.get("athlete") or {}).get("displayName") or "",
                    "captain": bool(p.get("captain")), "stats": player_stats(p)} for p in starters],
        })
    toss = None
    for note in data.get("notes") or []:
        if note.get("type") == "toss" and note.get("text"):
            text = note["text"]
            winner = re.split(r"\s*,", text)[0].strip()
            toss = {"text": re.sub(r"\s+,", ",", text), "winner": winner,
                    "decision": "field" if re.search(r"field|bowl", text, re.I) else "bat"}
    weather = (data.get("gameInfo") or {}).get("weather") or None
    return {
        "ok": True, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "state": kind.get("state"), "status_text": status.get("summary") or kind.get("description") or "",
        "start": comp.get("date"), "reduced_overs": str(comp.get("reducedOvers")).lower() == "true",
        "class": (comp.get("class") or {}).get("generalClassCard") or "", "limited": bool(comp.get("limitedOvers")),
        "venue": {"name": venue.get("fullName") or "", "city": address.get("city") or "", "country": address.get("country") or ""},
        "weather": weather if isinstance(weather, dict) else None, "toss": toss, "teams": teams,
    }


def fetch_intel(league, event):
    if not (str(league).isalnum() and str(event).isdecimal()):
        return {"ok": False, "error": "bad match reference"}
    request = urllib.request.Request(URL.format(league=league, event=event), headers=HEADERS)
    with urllib.request.urlopen(request, timeout=12) as response:
        return summarize(json.loads(response.read().decode("utf-8")))


def main():
    league, event = sys.argv[1], sys.argv[2]
    return fetch_intel(league, event)


if __name__ == "__main__":
    try:
        print(json.dumps(main()))
    except Exception as exc:  # reported to the server as data; never a traceback
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
