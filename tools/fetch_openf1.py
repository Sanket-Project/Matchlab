"""Fetch a race weekend's finished sessions from OpenF1 (free, no key; finished sessions only).

python tools/fetch_openf1.py <race start ISO>   -> JSON on stdout
At most about a dozen requests, paced under OpenF1's free limit of 3 a second and 30 a minute.
Runs as a short-lived process so the dashboard server stays offline.
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from matchlab import openf1  # noqa: E402

BASE = "https://api.openf1.org/v1"
HEADERS = {"User-Agent": "MatchLab/1.0", "Accept": "application/json"}


def get(path, query):
    time.sleep(0.4)
    url = f"{BASE}/{path}?{urllib.parse.urlencode(query, safe='<>=')}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 404:       # OpenF1's answer when a filter matches nothing
            return []
        raise
    return data if isinstance(data, list) else []


def fetch(race_start):
    now = datetime.now(timezone.utc)
    window = {"year": race_start.year, "date_start>": (race_start - timedelta(days=4)).strftime("%Y-%m-%d"),
              "date_start<": (race_start + timedelta(days=1)).strftime("%Y-%m-%d")}
    sessions = openf1.weekend(get("sessions", window), race_start)
    if not sessions:
        return {"ok": False, "error": "OpenF1 has not published this weekend's sessions yet."}
    details, latest = {}, None
    for session in sessions:
        if not openf1.finished(session, now):
            continue
        key = session["session_key"]
        details[key] = {"results": get("session_result", {"session_key": key}), "weather": get("weather", {"session_key": key})}
        latest = key
    drivers = get("drivers", {"session_key": latest}) if latest else []
    return openf1.summary(sessions, details, drivers, now)


if __name__ == "__main__":
    try:
        print(json.dumps(fetch(openf1.stamp(sys.argv[1]))))
    except Exception as exc:  # reported to the server as data; never a traceback
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
