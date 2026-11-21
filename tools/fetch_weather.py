"""Fetch the hourly forecast around a match start from Open-Meteo (free, no key).

python tools/fetch_weather.py <sport> <start ISO> --venue "<published venue>"
python tools/fetch_weather.py <sport> <start ISO> --at <lat> <lon> "<place name>"
JSON on stdout. Runs as a short-lived process so the dashboard server stays offline.
Open-Meteo's free API is for non-commercial use: https://open-meteo.com/en/terms
"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from matchlab import conditions  # noqa: E402

GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
HEADERS = {"User-Agent": "MatchLab/1.0", "Accept": "application/json"}


def get(url, params):
    with urllib.request.urlopen(urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", headers=HEADERS), timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def locate(venue):
    hint = conditions.country_hint(venue).lower()
    for name in conditions.place_candidates(venue):
        found = get(GEOCODE, {"name": name, "count": 5, "language": "en", "format": "json"}).get("results") or []
        if hint:
            found = sorted(found, key=lambda row: str(row.get("country", "")).lower() != hint)
        if found:
            row = found[0]
            return {"name": row.get("name") or name, "country": row.get("country") or "",
                    "lat": float(row["latitude"]), "lon": float(row["longitude"])}
    return None


def fetch(sport, start, place):
    first = start + timedelta(hours=conditions.WINDOW[0] - 1)
    last = start + timedelta(hours=conditions.WINDOW[1] + 1)
    raw = get(FORECAST, {"latitude": f"{place['lat']:.4f}", "longitude": f"{place['lon']:.4f}", "hourly": ",".join(conditions.HOURLY),
                         "timezone": "UTC", "start_hour": first.strftime("%Y-%m-%dT%H:00"), "end_hour": last.strftime("%Y-%m-%dT%H:00")})
    return conditions.summarize(raw, place, start, sport)


def main(argv):
    sport, start = argv[0], conditions.parse_start(argv[1])
    if sport not in ("cricket", "tennis", "f1"):
        return {"ok": False, "error": "unsupported sport"}
    if argv[2] == "--venue":
        place = locate(argv[3])
        if place is None:
            return {"ok": False, "error": "The venue could not be found on the map."}
    elif argv[2] == "--at":
        lat, lon = float(argv[3]), float(argv[4])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return {"ok": False, "error": "bad coordinates"}
        place = {"name": argv[5] if len(argv) > 5 else "", "country": "", "lat": lat, "lon": lon}
    else:
        return {"ok": False, "error": "bad arguments"}
    return fetch(sport, start, place)


if __name__ == "__main__":
    try:
        print(json.dumps(main(sys.argv[1:])))
    except Exception as exc:  # reported to the server as data; never a traceback
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
