"""Parsers for published fixtures and scorecards used in the cricket export."""

import calendar
import html
import json
import re
from datetime import datetime, timedelta, timezone

from matchlab.cricket_archive import JURISDICTIONS, competition_key, margins, method, result_from_text


COUNTRIES_URL = "https://unstats.un.org/unsd/methodology/m49/"
ICC_MEMBERS = "https://www.icc-cricket.com/about/members"
CRICSHEET_COVERAGE = "https://cricsheet.org/coverage/"
ESPN_URL = "https://site.web.api.espn.com/apis/personalized/v2/scoreboard/header?sport=cricket&lang=en"
ABU_DHABI_URL = "https://www.abudhabit10.com/t10x/matches"
ABU_DHABI_FEEDS = "https://dz8zbd8amw7pd.cloudfront.net/Abu_Dhabi/feeds"
CREX_EPL = "https://crex.com/series/everest-premier-league-2021-OA/matches"
EPL_REFERENCE = "https://cricombo.com/league/everest-premier-league"
CREX_CALENDAR = "https://crex.com/fixtures/league/series"
CREX_T10 = {
    "2019": "https://crex.com/series/abu-dhabi-t10-league-2019-HI/matches",
    "2020/21": "https://crex.com/series/K9/abu-dhabi-t10-league-2021/matches",
    "2021/22": "https://crex.com/series/abu-dhabi-t10-2021-SE/matches",
    "2022": "https://crex.com/series/abu-dhabi-t10-league-2022-17R/matches",
    "2023": "https://crex.com/series/abu-dhabi-t10-league-2023-1I8/matches",
    "2024": "https://crex.com/series/abu-dhabi-t10-league-2024-1M7/matches",
    "2025": "https://crex.com/series/abu-dhabi-t10-league-2025-1QT/matches",
}
MONTHS = "|".join(calendar.month_name[1:])
CREX_HOSTS = {
    "O": "India", "P": "South Africa", "Q": "Australia", "R": "New Zealand", "U": "Pakistan",
    "W": "Bangladesh", "X": "Zimbabwe", "11": "United Arab Emirates", "19": "Nepal", "16": "India",
}
CREX_FORMATS = {
    "ODI": "ODI", "One Day": "One-day", "List A": "One-day", "T20": "T20", "T20I": "T20I",
    "Test": "Test", "Multi Day": "Multi-day", "First Class": "Multi-day", "First Class Only": "Multi-day",
    "Youth ODI": "One-day", "Youth T20": "T20",
}


def html_text(value):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value)).split())


def table_rows(markup):
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", markup, re.S):
        yield [html_text(cell) for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row, re.S)]


def country_register(markup):
    table = re.search(r'<table class="table table-striped"[^>]*>(.*?)</table>', markup, re.S)
    countries = {row[2]: row[0] for row in table_rows(table[1])
                 if len(row) == 3 and re.fullmatch(r"[A-Z]{3}", row[2])} if table else {}
    if len(countries) < 200:
        raise ValueError("UN M49 country table missing or incomplete")
    return countries


def cricsheet_coverage(markup):
    match = re.search(r'By Competition</h\d>.*?<table[^>]*>(.*?)</table>', markup, re.S)
    if not match:
        raise ValueError("Cricsheet competition coverage table missing")
    for row in table_rows(match[1]):
        if len(row) < 2:
            continue
        counts = re.fullmatch(r"([\d,]+) of ([\d,]+)", row[1])
        if counts:
            yield row[0], *(int(v.replace(",", "")) for v in counts.groups())


def utc_stamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def legal_balls(overs):
    found = re.fullmatch(r"(\d+)(?:\.([0-5]))?", str(overs))
    return int(found[1]) * 6 + int(found[2] or 0) if found else ""


def score_line(match_id, number, team, score, overs, source_url, confidence):
    found = re.fullmatch(r"(\d+)(?:/(\d+))?", score)
    if not found:
        raise ValueError(f"Unrecognized score for {match_id}: {score!r}")
    return {
        "match_id": match_id, "innings_number": number, "batting_team": team, "runs": int(found[1]),
        "wickets": int(found[2]) if found[2] else "", "legal_balls": legal_balls(overs),
        "score_as_published": f"{score} ({overs})" if overs else score, "source_url": source_url,
        "confidence": confidence, "confidence_reason": "Published innings score",
    }


def published_match(match_id, source_id, source, url, retrieved_at, league, tournament,
                    season, match_format, teams, day, start, venue, detail, winner, status,
                    country="", category="", classification="", level="club", confidence="Medium"):
    result = result_from_text(detail, winner) if status in {"completed", "unknown"} else ""
    if result in {"abandoned", "postponed", "cancelled"}:
        status = result
    row = {
        "match_id": match_id, "source_match_id": source_id, "source": source, "source_url": url,
        "retrieved_at_utc": retrieved_at, "league": league, "tournament": tournament, "season": season,
        "team_a": teams[0], "team_b": teams[1], "start_date_local": day, "start_time_utc": start,
        "end_date_local": day if status == "completed" and match_format not in {"Test", "Multi-day"} else "",
        "format": match_format, "competition_level": level, "team_category": category,
        "match_classification": classification, "venue": venue, "country_or_region": country,
        "match_status": status, "result": result, "result_as_published": detail,
        "winner": winner if result == "win" else "", "result_margin": margins(detail) if result == "win" else "",
        "result_method": method(detail) if result else "", "confidence": confidence,
        "confidence_reason": f"Published by {source}",
    }
    age = re.search(r"\b(?:U|Under[- ]?)(\d{2})\b", tournament, re.I)
    row["age_group"] = f"U{age[1]}" if age else ""
    row["competition_id"] = competition_key(row)
    return row


def abu_dhabi_matches(rows, season, retrieved_at):
    for raw in rows:
        source_id = raw["MatchID"]
        match_id = f"abu-dhabi-t10-{source_id}"
        teams = raw["TeamAName"], raw["TeamBName"]
        match_day = datetime.strptime(raw["Local_Date"], "%d %b %Y").date().isoformat()
        start = datetime.strptime(f'{raw["Local_Date"]} {raw["Local_Time"]}', "%d %b %Y %H:%M:%S")
        start = utc_stamp(start.replace(tzinfo=timezone(timedelta(hours=4))))
        detail = raw.get("Result") or raw.get("MatchState") or ""
        status = {"Yet To Start": "scheduled", "Live": "live", "Completed": "completed"}.get(raw["Status"], "unknown")
        winner = next((name for name in teams if detail.casefold().startswith(f"{name} won".casefold())), "")
        row = published_match(match_id, source_id, "Abu Dhabi T10 official match centre", ABU_DHABI_URL,
                              retrieved_at, "Abu Dhabi T10", raw["CompName"], season, "T10", teams,
                              match_day, start, raw.get("Venue", ""), detail, winner, status,
                              country="United Arab Emirates", category={"Men": "male", "Women": "female"}.get(raw.get("Gender"), ""), confidence="High")
        row.update(stage=raw.get("MatchNumber", ""), host_country="United Arab Emirates")
        toss = re.fullmatch(r"(.+?) won the toss and chose to (bat|field|bowl)", raw.get("Toss", ""), re.I)
        if toss:
            prefixes = {raw["TeamANameprefix"]: teams[0], raw["TeamBNameprefix"]: teams[1]}
            row.update(toss_winner=prefixes.get(toss[1], ""), toss_decision="bat" if toss[2].lower() == "bat" else "field")
        flags = [label for key, label in (("DWL", "DLS"), ("SO", "Super Over")) if raw.get(key) == "1"]
        if flags:
            row["result_method"] = " / ".join(flags)
        innings = []
        for suffix in ("1st", "2nd", "3rd", "4th"):
            number, runs, team = (raw.get(key + suffix) for key in ("InningsNo", "Runs", "BattingClubName"))
            if not (number and str(runs or "").isdigit() and team):
                continue
            wickets = raw.get("Wickets" + suffix, "")
            score = f"{runs}/{wickets}" if str(wickets).isdigit() else str(runs)
            inning = score_line(match_id, int(number), team, score, raw.get("Overs" + suffix, ""), ABU_DHABI_URL, "High")
            inning["is_super_over"] = int(number) > 2
            innings.append(inning)
        if innings:
            row["batting_first"] = innings[0]["batting_team"]
        yield row, innings


def crex_state(markup):
    script = re.search(r'<script id="app-root-state" type="application/json">(.*?)</script>', markup, re.S)
    if not script:
        raise ValueError("CREX fixture data missing")
    entities = {"q": '"', "a": "&", "s": "'", "l": "<", "g": ">"}
    return json.loads(re.sub(r"&([qaslg]);", lambda match: entities[match[1]], script[1]))


def crex_series_links(markup):
    for path in sorted(set(re.findall(r'href="(/series/[a-z0-9-]+-[A-Z0-9]+)"', markup))):
        yield f"https://crex.com{path}/matches"


def crex_series_title(markup):
    heading = re.search(r"<h1\b[^>]*>(.*?)</h1>", markup, re.S)
    return html_text(heading[1]).removesuffix(" Matches") if heading else ""


def epl_scorecard_references(markup):
    cards = re.findall(r'<a class="pv-h2h-match hist-link" href="([^"]+)">(.*?)</a>', markup, re.S)
    if not cards:
        raise ValueError("Everest Premier League reference scores missing")
    for path, card in cards:
        sides = re.findall(
            r'<span class="pv-h2h-team([^"]*)">\s*<img[^>]*alt="([^"]+)".*?</span>\s*'
            r'<span class="pv-h2h-score[^"]*">(.*?)</span>', card, re.S)
        if len(sides) != 2:
            continue
        source_id = path.rsplit("-", 1)[1]
        match_id = f"cricombo-{source_id}"
        day = datetime.strptime(path.split("/")[-1][:10], "%d-%m-%Y").date().isoformat()
        names = [html.unescape(side[1]) for side in sides]
        winner = next((name for name, side in zip(names, sides) if "pv-h2h-win" in side[0]), "")
        url = f"https://cricombo.com{path}"
        match = {
            "match_id": match_id, "start_date_local": day, "team_a": names[0], "team_b": names[1],
            "source": "Cricombo", "source_url": url, "league": "Everest Premier League", "season": "2021",
            "format": "T20", "team_category": "male", "result": "win" if winner else "", "winner": winner,
        }
        innings = [score_line(match_id, "", name, score, "", url, "Medium")
                   for name, (_, _, score) in zip(names, sides) if re.fullmatch(r"\d+(?:/\d+)?", score)]
        yield match, innings


def crex_matches(markup, url, league, season, match_format, country, retrieved_at, category="", level=""):
    state = crex_state(markup)
    games = state["https://stats.crickapi.com/series/getMatchesForSeriesID"]
    if not games:
        return
    overview = state.get("https://stats.crickapi.com/series/getSeriesOverview", {}).get("i1", {}).get("i", {})
    maps = [state.get(f"https://oc.crickapi.com/mapping/getHomeMapData{suffix}", {})
            for suffix in ("seriesmain", "seriesmatches")]
    team_names = {team["f_key"]: team["n"] for data in maps for team in data.get("t", [])}
    venues = {venue["f_key"]: venue["n"] for data in maps for venue in data.get("v", [])}
    series = next((item for data in reversed(maps) for item in data.get("s", []) if item["f_key"] == games[0]["sf"]), {})
    tournament = series.get("n") or crex_series_title(markup)
    title = re.fullmatch(r"(.*?)[ ]+(\d{4}(?:[-/]\d{2,4})?)", tournament)
    level = level or ("international" if overview.get("it") or series.get("tour")
                      or any(marker in tournament.casefold() for marker in ("asia cup", "t20i", "nations trophy"))
                      else "club")
    league = league or (title[1] if title else tournament)
    league = {
        "Womens Big Bash League": "Women's Big Bash League",
        "The Ford Trophy": "Ford Trophy",
        "Quaid e Azam Trophy Gold": "Quaid-e-Azam Trophy Gold",
        "Quaid e Azam Trophy Silver": "Quaid-e-Azam Trophy Silver League",
        "Abu Dhabi T10 League": "Abu Dhabi T10",
    }.get(league, league)
    country = country or JURISDICTIONS.get(league, CREX_HOSTS.get(overview.get("host"), ""))
    host_country = CREX_HOSTS.get(overview.get("host"), country if level == "club" else "")
    if league == "Afghanistan Premier League" and season == "2018":
        host_country = "United Arab Emirates"
    season = season or (title[2].replace("-", "/") if title else "")
    if level == "international":
        league = ""
    for game in games:
        source_id = str(game["id"])
        match_id = f"crex-{source_id}"
        teams = [team_names.get(game.get(key), "") for key in ("t1f", "t2f")]
        detail = game.get("a", "")
        if not detail or detail.startswith(("$", "^")):
            detail = game.get("resultExtraComment") or game.get("result") or ""
        winner = team_names.get(game.get("w"), "")
        status = "completed" if game["status"] == 2 else "live" if game["status"] == 1 else "scheduled"
        published_format = game.get("fo") or {
            1: overview.get("odi_subformat"), 2: overview.get("t20_subformat"), 3: overview.get("test_subformat"),
        }.get(game["ft"]) or ""
        fmt = match_format or CREX_FORMATS.get(published_format) or {1: "One-day", 2: "T20", 3: "Multi-day", 4: "T10"}.get(game["ft"], "")
        game_category = category or {0: "female", 1: "male"}.get(game.get("g"), "")
        row = published_match(match_id, source_id, "CREX", url, retrieved_at, league, tournament, season, fmt,
                              teams, datetime.strptime(game["date"], "%m/%d/%Y").date().isoformat(),
                              utc_stamp(datetime.fromtimestamp(game["t"] / 1000, timezone.utc)),
                              venues.get(game.get("vf"), ""), detail, winner, status,
                              country=country or ("Global" if level == "international" else ""), category=game_category,
                              classification=published_format, level=level)
        row.update(stage=game.get("mn", ""), host_country=host_country,
                   batting_first=team_names.get(game.get("bf"), ""),
                   score_a_as_published=" & ".join(filter(None, (game.get("s1"), game.get("s3")))),
                   score_b_as_published=" & ".join(filter(None, (game.get("s2"), game.get("s4")))))
        if not all(teams):
            row.update(confidence="Low", confidence_reason="Published fixture with undecided team slot")
        # The feed stores one score per team. An innings ordinal is known only
        # when the batting-first team is explicitly published.
        innings = []
        for index, team in enumerate(teams, 1):
            score = game.get(f"s{index}", "")
            if score and team and fmt not in {"Test", "Multi-day"} and re.fullmatch(r"\d+(?:/\d+)?", score):
                first = row["batting_first"]
                number = (1 if team == first else 2) if first else ""
                innings.append(score_line(match_id, number, team, score, game.get(f"o{index}", ""), url, "Medium"))
        yield row, innings


def espn_fixtures(payload, retrieved_at):
    for sport in payload["sports"]:
        for series in sport.get("leagues", []):
            for event in series.get("events", []):
                teams = event.get("competitors", [])
                if len(teams) != 2 or not all(team.get("displayName") for team in teams):
                    continue
                notes = {note["type"]: note["text"] for note in event.get("notes", [])
                         if note["type"] in {"season", "matchdays", "toss"}}
                classification = event.get("class", {})
                card = classification.get("generalClassCard", "")
                class_name = classification.get("name") or card
                category = "female" if "women" in (card + class_name + series["name"]).casefold() else "male"
                name = series["name"].strip()
                season = notes.get("season", str(event.get("season", "")))
                league = re.sub(r" \d{4}(?:/\d{2,4})?$", "", name)
                international = classification.get("internationalClassId") not in {None, "", "0"}
                international = international or "tour of" in name.casefold()
                match_format = next((fmt for token, fmt in (
                    ("t10", "T10"), ("the hundred", "100-ball")) if token in name.casefold()), "")
                if not match_format:
                    match_format = {
                        "4": "Test" if international and card == "Test" else "Multi-day",
                        "5": "ODI" if international and "international" in class_name.casefold() else "One-day",
                        "6": "T20I" if international else "T20",
                        "17": "T20I" if international else "T20",
                    }.get(classification.get("generalClassId"), "")
                kind = event.get("fullStatus", {}).get("type", {})
                state = kind.get("state") or event.get("status")
                status = {"pre": "scheduled", "in": "live", "post": "completed"}.get(state, "unknown")
                detail = event.get("summary") or kind.get("detail", "")
                if status == "completed":
                    detail = event.get("fullStatus", {}).get("longSummary") or detail
                winner = next((team["displayName"] for team in teams if team.get("winner")), "") if status == "completed" else ""
                dates = re.search(rf"\b(\d{{1,2}})(?:,\d{{1,2}})* ({MONTHS}) (\d{{4}})", notes.get("matchdays", ""))
                day = datetime.strptime(" ".join(dates.groups()), "%d %B %Y").date().isoformat() if dates else ""
                source_id = event["id"]
                url = next((link["href"] for link in event.get("links", []) if "boxscore" in link.get("rel", [])), ESPN_URL)
                row = published_match(f"cricket-{source_id}", source_id, "ESPN cricket scoreboard", url, retrieved_at,
                                      "" if international else league, name, season, match_format,
                                      [team["displayName"] for team in teams], day,
                                      event.get("date", "") if event.get("timeValid") else "",
                                      event.get("location", ""), detail, winner, status,
                                      JURISDICTIONS.get(league, "Global" if international else ""), category,
                                      class_name, "international" if international else "club")
                row.update(stage=event.get("description", "").split(",", 1)[0],
                           score_a_as_published=teams[0].get("score", ""), score_b_as_published=teams[1].get("score", ""))
                toss = re.match(r"(.+?)\s*,?\s+elected to (bat|field|bowl)\b", notes.get("toss", ""), re.I)
                if toss:
                    row.update(toss_winner=toss[1].strip(), toss_decision="bat" if toss[2].lower() == "bat" else "field")
                yield row, []
