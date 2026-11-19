"""Fetch one tennis match's live set scores from ESPN's scoreboard.

python tools/fetch_tennis_intel.py <atp|wta> <competition id> <yyyymmdd>   -> JSON on stdout
Free and unmetered. Runs as a short-lived process so the dashboard server stays offline.
Sides are returned in the feed's order, which is the order the fixture list uses.
"""
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

URL = "https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/scoreboard?dates={day}"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def summarize(comp):
    kind = (comp.get("status") or {}).get("type") or {}
    sides = comp.get("competitors") or []
    lines = [side.get("linescores") or [] for side in sides]
    sets = []
    for index in range(min(len(lines[0]), len(lines[1])) if len(lines) == 2 else 0):
        a, b = lines[0][index], lines[1][index]
        if isinstance(a.get("value"), (int, float)) and isinstance(b.get("value"), (int, float)):
            sets.append({"a": int(a["value"]), "b": int(b["value"]), "done": bool(a.get("winner") or b.get("winner"))})
    note = next((n.get("text") for n in comp.get("notes") or [] if n.get("text")), "")
    return {"ok": True, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "state": kind.get("state") or "pre", "status": kind.get("shortDetail") or kind.get("description") or "",
            "names": [(side.get("athlete") or {}).get("displayName") or "" for side in sides],
            "ranks": [(side.get("curatedRank") or {}).get("current") for side in sides],
            "winner": next((i for i, side in enumerate(sides) if side.get("winner")), None),
            "sets": sets, "note": note, "round": (comp.get("round") or {}).get("displayName") or ""}


def fetch_tennis(tour, event, day):
    if tour not in ("atp", "wta") or not str(event).isdecimal() or not (str(day).isdecimal() and len(str(day)) == 8):
        return {"ok": False, "error": "bad match reference"}
    start = datetime.strptime(str(day), "%Y%m%d")
    for offset in (0, 1, -1):       # the feed's day boundary is not always the fixture's
        stamp = (start + timedelta(days=offset)).strftime("%Y%m%d")
        request = urllib.request.Request(URL.format(tour=tour, day=stamp), headers=HEADERS)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
            for tournament in data.get("events") or []:
                for group in tournament.get("groupings") or []:
                    for comp in group.get("competitions") or []:
                        if str(comp.get("id")) == str(event):
                            return summarize(comp)
        except Exception:
            continue
    return {"ok": False, "error": "This match is not on the scoreboard right now."}


def main():
    tour, event, day = sys.argv[1], sys.argv[2], sys.argv[3]
    return fetch_tennis(tour, event, day)


if __name__ == "__main__":
    try:
        print(json.dumps(main()))
    except Exception as exc:  # reported to the server as data; never a traceback
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
