"""Read race results and lap timing in a network worker."""
import json
import sys
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

JOLPICA = "https://api.jolpi.ca/ergast/f1"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/racing/f1/scoreboard"
HEADERS = {"User-Agent": "MatchLab/1.0", "Accept": "application/json"}


def get(url):
    with urlopen(Request(url, headers=HEADERS), timeout=6) as response:
        return json.load(response)


def results(season, round_number):
    races = get(f"{JOLPICA}/{season}/{round_number}/results.json?limit=30")["MRData"]["RaceTable"]["Races"]
    return races[0] if races else {}


def winner(season, round_number):
    for row in results(season, round_number).get("Results", []):
        if row["position"] == "1":
            driver = row["Driver"]
            return f"{driver['givenName']} {driver['familyName']}"
    return None


def recorded_laps(season, round_number):
    endpoint = f"{JOLPICA}/{season}/{round_number}/laps.json"
    laps, offset = {}, 0
    while True:
        page = get(f"{endpoint}?limit=100&offset={offset}")["MRData"]
        races = page["RaceTable"]["Races"]
        if not races:
            break
        count = 0
        for lap in races[0].get("Laps", []):
            split = laps.setdefault(int(lap["number"]), {})
            for row in lap["Timings"]:
                split[row["driverId"]] = row
                count += 1
        offset += count
        if not count or offset >= int(page["total"]):
            break
    return laps


def lap_seconds(value):
    minutes, seconds = value.split(":")
    return int(minutes) * 60 + float(seconds)


def recorded(season, round_number, race):
    drivers = {row["Driver"]["driverId"]: f"{row['Driver']['givenName']} {row['Driver']['familyName']}"
               for row in race.get("Results", [])}
    output = []
    for number, split in sorted(recorded_laps(season, round_number).items()):
        field = sorted(split.values(), key=lambda row: int(row["position"]))
        fastest = min(field, key=lambda row: lap_seconds(row["time"]))
        output.append({"lap": number,
                       "order": [drivers.get(row["driverId"], row["driverId"]) for row in field],
                       "positions": {drivers.get(row["driverId"], row["driverId"]): int(row["position"]) for row in field},
                       "fastest": {"driver": drivers.get(fastest["driverId"], fastest["driverId"]),
                                   "time": fastest["time"]}})
    return {"state": "post", "source": "Jolpica F1", "laps": output}


def live_snapshot(start):
    day = start.strftime("%Y%m%d")
    data = get(f"{ESPN}?dates={day}")
    for event in data.get("events", []):
        for race in event.get("competitions", []):
            if (race.get("type") or {}).get("abbreviation") != "Race":
                continue
            scheduled = datetime.fromisoformat(race["date"].replace("Z", "+00:00"))
            if abs(scheduled - start) > timedelta(hours=2):
                continue
            status = race.get("status") or {}
            state = (status.get("type") or {}).get("state")
            if state != "in" or not status.get("period"):
                continue
            ranked = [(side["order"], side["athlete"]["displayName"]) for side in race["competitors"]
                      if isinstance(side.get("order"), int) and side["order"] > 0
                      and (side.get("athlete") or {}).get("displayName")]
            if sorted(pos for pos, _ in ranked) != list(range(1, len(ranked) + 1)):
                continue
            order = [name for _, name in sorted(ranked)]
            if order:
                return [{"lap": status["period"], "order": order, "positions": {name: pos for pos, name in ranked}}]
    return []


def fetch(season, round_number):
    race = results(season, round_number)
    if race.get("Results"):
        return recorded(season, round_number, race)
    endpoint = f"{JOLPICA}/{season}/{round_number}.json"
    races = get(endpoint)["MRData"]["RaceTable"]["Races"]
    if not races or not races[0].get("time"):
        return {"state": "unavailable", "laps": []}
    race = races[0]
    start = datetime.fromisoformat((race["date"] + "T" + race["time"]).replace("Z", "+00:00"))
    if datetime.now(timezone.utc) < start:
        return {"state": "pre", "laps": []}
    return {"state": "in", "source": "ESPN", "laps": live_snapshot(start)}


if __name__ == "__main__":
    try:
        season, round_number = map(int, sys.argv[1:3])
        if sys.argv[3:] == ["winner"]:
            print(json.dumps(winner(season, round_number)))
        else:
            print(json.dumps(fetch(season, round_number)))
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps(None))
