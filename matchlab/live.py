"""Link fetched fixtures to local datasets. Pure local logic; no network access."""
import re
import unicodedata
from datetime import datetime

# Source display name -> local dataset name, where simple normalisation is not enough.
ALIASES = {
    "baseball": {
        "Los Angeles Angels": "ANA", "Arizona Diamondbacks": "ARI", "Atlanta Braves": "ATL", "Baltimore Orioles": "BAL",
        "Boston Red Sox": "BOS", "Chicago White Sox": "CHA", "Chicago Cubs": "CHN", "Cincinnati Reds": "CIN",
        "Cleveland Guardians": "CLE", "Colorado Rockies": "COL", "Detroit Tigers": "DET", "Houston Astros": "HOU",
        "Kansas City Royals": "KCA", "Los Angeles Dodgers": "LAN", "Miami Marlins": "MIA", "Milwaukee Brewers": "MIL",
        "Minnesota Twins": "MIN", "New York Yankees": "NYA", "New York Mets": "NYN", "Oakland Athletics": "OAK",
        "Athletics": "OAK", "Philadelphia Phillies": "PHI", "Pittsburgh Pirates": "PIT", "San Diego Padres": "SDN",
        "Seattle Mariners": "SEA", "San Francisco Giants": "SFN", "St. Louis Cardinals": "SLN", "Tampa Bay Rays": "TBA",
        "Texas Rangers": "TEX", "Toronto Blue Jays": "TOR", "Washington Nationals": "WAS",
    },
    "rugby": {
        "Queensland Reds": "Reds", "New South Wales Waratahs": "Waratahs", "NSW Waratahs": "Waratahs",
        "Western Force": "Force", "Melbourne Rebels": "Rebels", "ACT Brumbies": "Brumbies",
    },
    "cricket": {
        "Royal Challengers Bangalore": "Royal Challengers Bengaluru",
    },
}
DROP = {"fc", "afc", "cf", "sc", "the"}


def name_key(name):
    """Comparison key: accents, punctuation, club suffixes and dataset id tags removed."""
    text = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    text = re.sub(r"\s*\[[^\]]*\]\s*$", "", text).lower().replace("&", " and ")
    return " ".join(t for t in re.findall(r"[a-z0-9]+", text) if t not in DROP)


def annotate(payload, datasets, race_engine=None):
    """Add local_team/local_opponent/analyzable/history_through to every fixture.

    A fixture is analyzable only when both sides exist in the local dataset for
    that sport. Nothing is guessed: unknown sides are reported by name.
    """
    lookups = {}
    for sport, matches in (payload.get("sports") or {}).items():
        if sport == "f1":
            for fixture in matches:
                race = next((race for race in race_engine.races if race["start"] == datetime.fromisoformat(fixture["start"])), None) if race_engine else None
                fixture["analyzable"] = race is not None
                if race is None:
                    fixture["unavailable_reason"] = "Grand Prix is missing from the local calendar"
                    continue
                fixture.update(season=race["season"], round=race["round"], race_id=race["race_id"],
                               history_through=race_engine.completed[-1]["date"])
            continue
        ds = datasets.get(sport)
        if ds is not None and sport not in lookups:
            table = {name_key(t): t for t in ds.teams}
            for source, local in ALIASES.get(sport, {}).items():
                if local in ds.teams:
                    table[name_key(source)] = local
            lookups[sport] = table
        for m in matches:
            m["analyzable"], m["local_team"], m["local_opponent"] = False, None, None
            if ds is None:
                m["unavailable_reason"] = "No local dataset for this sport"
                continue
            m["history_through"] = ds.matches[-1]["date"]
            a, b = (lookups[sport].get(name_key(m.get(k))) for k in ("team", "opponent"))
            m["local_team"], m["local_opponent"] = a, b
            missing = [m.get(k) for k, found in (("team", a), ("opponent", b)) if not found]
            if missing:
                m["unavailable_reason"] = "No local history for " + " or ".join(str(x) for x in missing)
            elif a == b:
                m["unavailable_reason"] = "Both sides map to the same local record"
            else:
                m["analyzable"] = True
    return payload


def team_key(name):
    key = name_key(re.sub(r"\s+\([^)]*\)\s*$", "", str(name or "")))      # "Kathmandu Gorkhas (NPL)"
    for suffix in (" women", " w"):
        if key.endswith(suffix):
            key = key[: -len(suffix)]
    return {"royal challengers bangalore": "royal challengers bengaluru", "delhi daredevils": "delhi capitals",
            "kings xi punjab": "punjab kings", "usa": "united states of america", "uae": "united arab emirates",
            "u a e": "united arab emirates", "png": "papua new guinea"}.get(key, key)
