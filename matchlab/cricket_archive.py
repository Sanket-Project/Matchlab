"""Source-preserving match and innings records for the global cricket export."""

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile


CRICSHEET = "https://cricsheet.org/downloads/"
# Earlier names for the same IPL franchise.
CRICKET_TEAMS = {"Royal Challengers Bangalore": "Royal Challengers Bengaluru", "Delhi Daredevils": "Delhi Capitals",
                 "Kings XI Punjab": "Punjab Kings", "Rising Pune Supergiants": "Rising Pune Supergiant"}
FORMATS = {
    "Test": "Test", "MDM": "Multi-day", "ODI": "ODI", "ODM": "One-day",
    "T20": "T20", "IT20": "T20I", "T10": "T10",
}
ALIASES = {
    "IPL": "Indian Premier League",
    "BBL": "Big Bash League",
    "EPL": "Everest Premier League",
    "Abu Dhabi League": "Abu Dhabi T10",
    "Vitality Blast": "T20 Blast",
    "Vitality Blast Men": "T20 Blast",
    "NatWest T20 Blast": "T20 Blast",
    "Specsavers County Championship": "County Championship",
    "LV= County Championship": "County Championship",
    "Vitality Blast Women": "Women's T20 Blast",
    "The Hundred Men's Competition": "The Hundred",
    "The Hundred Women's Competition": "The Hundred",
    "Marsh Sheffield Shield": "Sheffield Shield",
    "The Marsh Cup": "One-Day Cup (Australia)",
    "Royal London One-Day Cup": "One-Day Cup",
    "Ram Slam T20 Challenge": "CSA T20 Challenge",
    "MiWAY T20 Challenge": "CSA T20 Challenge",
    "Women's T20 Blaze": "T20 Blaze",
    "CG United Women's Super50": "Super 50",
    "Women's Super Smash": "Super Smash",
    "New Zealand Cricket Women's Twenty20": "Super Smash",
    "HRV Twenty20": "Super Smash",
    "HRV Cup": "Super Smash",
    "Women's T20 Challenge Match": "Women's T20 Challenge",
}

# Organizing jurisdictions, distinct from the venue's host country.
DOMESTIC_JURISDICTIONS = {
    "Afghanistan": ("Afghanistan Premier League",),
    "Australia": ("Big Bash League", "Women's Big Bash League", "Sheffield Shield", "One-Day Cup (Australia)", "Women's National Cricket League"),
    "Bangladesh": ("Bangladesh Premier League", "Dhaka Premier Division Cricket League"),
    "England and Wales": (
        "County Championship", "County Championship Division One", "County Championship Division Two",
        "Bob Willis Trophy", "The Hundred", "T20 Blast", "Vitality Blast", "One-Day Cup",
        "Rachael Heyhoe Flint Trophy", "Charlotte Edwards Cup", "Women's Cricket Super League",
        "ECB Women's One-Day Cup", "Women's T20 Blast",
    ),
    "India": ("Indian Premier League", "Women's Premier League", "Women's T20 Challenge", "Syed Mushtaq Ali Trophy", "Ranji Trophy", "Vijay Hazare Trophy"),
    "Ireland": ("Cricket Ireland Inter-Provincial Limited Over Cup", "Cricket Ireland Inter-Provincial Twenty20 Trophy"),
    "Nepal": ("Everest Premier League", "Nepal Premier League"),
    "New Zealand": ("Plunket Shield", "Super Smash", "Ford Trophy", "Hallyburton Johnstone Shield"),
    "Pakistan": ("Pakistan Super League", "Quaid-e-Azam Trophy", "Quaid-e-Azam Trophy Silver League", "Quaid-e-Azam Trophy Gold"),
    "South Africa": ("SA20", "Mzansi Super League", "CSA T20 Challenge", "CSA Pro20", "South Africa Domestic T20/Pro20"),
    "Sri Lanka": ("Lanka Premier League", "Major Clubs Limited Over Tournament", "Major Clubs T20 Tournament", "Major League Tournament"),
    "United Arab Emirates": ("Abu Dhabi T10", "International League T20"),
    "United States of America": ("Major League Cricket", "US Masters T10"),
    "West Indies": ("Caribbean Premier League", "Women's Caribbean Premier League", "Super 50", "T20 Blaze"),
    "Zimbabwe": ("Zim Afro T10",),
    "Europe": ("European T20 Premier League", "European Cricket League"),
    "Global": ("FairBreak Invitational Tournament",),
}
JURISDICTIONS = {event: area for area, events in DOMESTIC_JURISDICTIONS.items() for event in events}


def normalized(value):
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(re.findall(r"[^\W_]+", text, re.UNICODE))


def competition_key(match):
    # Cricsheet uses a name per source event, including historical sponsor
    # names. Keep the published name in the row and only group explicit aliases.
    name = match.get("league") or match.get("tournament")
    if not name:
        return ""
    canonical = ALIASES.get(name, name)
    key = "|".join(normalized(v) for v in (canonical, match["competition_level"], match["team_category"]))
    return "comp-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def result_from_text(detail, winner=""):
    text = detail.casefold()
    labels = (
        ("abandon", "abandoned"), ("cancel", "cancelled"), ("postpon", "postponed"),
        ("no result", "no_result"), ("draw", "draw"), ("tie", "tie"),
    )
    if winner:
        return "win"
    return next((result for token, result in labels if token in text), "")


def margins(detail):
    found = re.search(r"\bby ((?:an innings and )?\d+ (?:runs?|wickets?)|an innings)\b", detail, re.I)
    return found[1] if found else ""


def method(detail):
    found = re.search(r"\b(?:DLS|D/L|VJD|VJD method|Super Over|Bowl-out)\b", detail, re.I)
    return found[0] if found else ""


def innings_from_balls(match_id, number, innings, source_url):
    penalty = innings.get("penalty_runs", {})
    runs = penalty.get("pre", 0) + penalty.get("post", 0)
    wickets = legal_balls = 0
    for over in innings.get("overs", []):
        for ball in over["deliveries"]:
            runs += ball["runs"]["total"]
            extras = ball.get("extras", {})
            legal_balls += not (extras.get("wides") or extras.get("noballs"))
            wickets += sum(w["kind"] not in {"retired hurt", "retired not out", "obstructing the field (non-dismissal)"}
                           for w in ball.get("wickets", []))
    return {
        "match_id": match_id, "innings_number": number, "batting_team": innings["team"],
        "runs": runs, "wickets": wickets, "legal_balls": legal_balls,
        "is_super_over": bool(innings.get("super_over")), "declared": bool(innings.get("declared")),
        "forfeited": bool(innings.get("forfeited")), "source_url": source_url,
        "confidence": "Medium", "confidence_reason": "Calculated from Cricsheet deliveries and innings penalties",
    }


def cricsheet_match(source_id, document, retrieved_at, source_url=CRICSHEET):
    info = document["info"]
    dates = info["dates"]
    team_a, team_b = info["teams"]
    outcome = info.get("outcome", {})
    source_type = info["match_type"]
    event = info.get("event", {})
    event_name = event.get("name", "")
    canonical_event = ALIASES.get(event_name, event_name)
    category = info.get("gender", "")
    age = re.search(r"\b(?:U|Under[- ]?)(\d{2})\b", " ".join([event_name, team_a, team_b]), re.I)
    level = info.get("team_type", "")
    match_format = FORMATS.get(source_type, source_type)
    if source_type in {"T20", "IT20"}:
        scheduled_balls = info.get("overs", 0) * info.get("balls_per_over", 6)
        if scheduled_balls == 60:
            match_format = "T10"
        elif scheduled_balls == 100 or canonical_event == "The Hundred":
            match_format = "100-ball"
        elif scheduled_balls == 300:
            match_format = "One-day"
        elif source_type == "T20" and level == "international":
            match_format = "T20I"
        elif source_type == "IT20":
            match_format = "T20"
    winner = outcome.get("winner") or outcome.get("eliminator") or outcome.get("bowl_out") or ""
    margin = " and ".join(f"{amount} {unit.rstrip('s') if amount == 1 else unit}" if amount else unit
                          for unit, amount in outcome.get("by", {}).items())
    result = result_from_text(outcome.get("result", ""), winner)
    toss = info.get("toss", {})
    match_id = f"cricket-{source_id}"
    innings = [innings_from_balls(match_id, number, inning, source_url)
               for number, inning in enumerate(document.get("innings", []), 1)]
    recorded_method = outcome.get("method", "")
    if outcome.get("eliminator"):
        recorded_method = " / ".join(filter(None, (recorded_method, "Super Over")))
    elif outcome.get("bowl_out"):
        recorded_method = " / ".join(filter(None, (recorded_method, "Bowl-out")))
    row = {
        "match_id": match_id, "source_match_id": source_id, "source": "Cricsheet",
        "league": canonical_event if level == "club" else "", "tournament": event_name,
        "season": str(info.get("season", "")), "stage": str(event.get("stage") or event.get("match_number") or ""),
        "format": match_format, "match_classification": source_type, "competition_level": level,
        "team_category": category, "age_group": f"U{age[1]}" if age else "",
        "country_or_region": JURISDICTIONS.get(canonical_event, "Global" if level == "international" else ""),
        "team_a": team_a, "team_b": team_b, "start_date_local": dates[0], "end_date_local": dates[-1],
        "venue": info.get("venue", ""), "city": info.get("city", ""),
        "host_country": info.get("country", ""),
        "match_status": result if result in {"abandoned", "cancelled", "postponed"} else "completed" if result else "unknown",
        "result": result, "result_as_published": outcome.get("result", ""), "winner": winner,
        "result_margin": margin, "result_method": recorded_method,
        "toss_winner": toss.get("winner", ""), "toss_decision": toss.get("decision", ""),
        "batting_first": innings[0]["batting_team"] if innings else "",
        "source_url": source_url, "retrieved_at_utc": retrieved_at,
        "confidence": "Medium" if result else "Low",
        "confidence_reason": "Cricsheet archive record" if result else "Cricsheet record without a definitive result",
    }
    row["competition_id"] = competition_key(row)
    return row, innings


def read_cricsheet(path, retrieved_at, source_url=CRICSHEET):
    with ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            source_id = Path(name).stem
            if name.endswith(".json") and source_id.isdecimal():
                yield cricsheet_match(source_id, json.loads(archive.read(name)), retrieved_at, source_url)


def index_by(items, key):
    grouped = defaultdict(list)
    for row in items:
        grouped[key(row)].append(row)
    return grouped
