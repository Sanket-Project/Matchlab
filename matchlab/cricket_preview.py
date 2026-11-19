"""Build a sourced cricket preview from the saved fixture and local archive."""
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from functools import lru_cache
from zipfile import BadZipFile, ZipFile

from .cricket_archive import CRICKET_TEAMS
from .cricket_format_forecast import forecast
from .cricket_projections import WINDOW, project
from .live import name_key


FIXTURE_FIELDS = ("id", "team", "opponent", "tournament", "start", "venue", "status",
                  "state", "team_score", "opponent_score", "detail")
FORMATS = {"test": "Test", "t10": "T10", "odi": "ODI", "t20": "T20", "t20i": "T20I",
           "it20": "T20I", "first class": "Multi-day", "fc": "Multi-day", "multi day": "Multi-day",
           "list a": "One-day", "one day": "One-day", "100 ball": "100-ball"}
SCOREBOARD = "https://www.espncricinfo.com/live-cricket-score"
TEAM_ALIASES = {name_key(old): name_key(new) for old, new in CRICKET_TEAMS.items()}


def _snapshot(root):
    path = root / "data/real/cricket_global"
    name = json.loads((path / "latest.json").read_text(encoding="utf-8"))["snapshot"]
    if not isinstance(name, str) or not re.fullmatch(r"\d{8}T\d+Z", name):
        raise ValueError("Invalid cricket archive snapshot")
    return path / name


def _team(name, category):
    key = name_key(name)
    if category == "female":
        key = re.sub(r" (women|w)$", "", key)
    return TEAM_ALIASES.get(key, key)


@lru_cache(maxsize=2)
def _archive(path, format_name, category, league):
    with (path / "matches.csv").open(encoding="utf-8", newline="") as file:
        matches = [row for row in csv.DictReader(file)
                   if row["format"] == format_name and row["team_category"] == category
                   and (not league or name_key(row["league"]) == league)
                   and row["match_status"] == "completed"
                   and row["start_date_local"] and row["end_date_local"]]
    innings = defaultdict(list)
    ids = {row["match_id"] for row in matches}
    with (path / "innings.csv").open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            if row["match_id"] in ids and row["is_super_over"] != "True" and row["forfeited"] != "True":
                innings[row["match_id"]].append(row)

    results = []
    for row in matches:
        match_id = row["match_id"]
        teams = tuple(_team(row[key], category) for key in ("team_a", "team_b"))
        if not all(teams) or teams[0] == teams[1]:
            continue
        scores = {}
        scorecard = []
        for inning in sorted(innings[match_id], key=lambda x: int(x["innings_number"])):
            batting = _team(inning["batting_team"], category)
            if inning["runs"].isdigit() and batting in teams:
                scores.setdefault(batting, int(inning["runs"]))
                scorecard.append({"team": inning["batting_team"], "runs": int(inning["runs"]),
                                  "wickets": inning["wickets"] or None, "declared": inning["declared"] == "True",
                                  "legal_balls": int(inning["legal_balls"]) if inning.get("legal_balls", "").isdigit() else None})
        results.append({"id": match_id, "start": row["start_date_local"], "end": row["end_date_local"],
                        "teams": teams, "winner": _team(row["winner"], category), "result": row["result"],
                        "venue": row["venue"], "scores": scores, "data_source": row["source"],
                        "source_id": row["source_match_id"], "published": {
                            "date": row["start_date_local"], "teams": [row["team_a"], row["team_b"]],
                            "result": row["result"], "winner": row["winner"] or None,
                            "margin": row["result_margin"] or None, "venue": row["venue"] or None,
                            "innings": scorecard, "source_url": row["source_url"],
                        }})
    return sorted(results, key=lambda row: (row["end"], row["start"], row["id"]))


def _player_history(root, matches, teams, category):
    records = {row["source_id"]: row for row in matches if row["data_source"] == "Cricsheet"}
    if not records:
        return {}
    batters, pairs = Counter(), Counter()
    runs = Counter()
    used = 0
    try:
        with ZipFile(root / "data/raw/cricket/all_json.zip") as archive:
            for source_id, row in records.items():
                try:
                    document = json.loads(archive.read(f"{source_id}.json"))
                except KeyError:
                    continue
                used += 1
                head_to_head = set(row["teams"]) == set(teams)
                for inning in document["innings"]:
                    side = inning["team"]
                    if _team(side, category) not in teams or inning.get("super_over"):
                        continue
                    for over in inning.get("overs", []):
                        for delivery in over["deliveries"]:
                            batter, bowler = delivery["batter"], delivery["bowler"]
                            scored = delivery["runs"]["batter"]
                            batters[side, batter] += scored
                            if head_to_head and not delivery.get("extras", {}).get("wides"):
                                pair = (batter, bowler)
                                pairs[pair] += 1
                                runs[pair] += scored
    except (OSError, ValueError, KeyError, BadZipFile):
        return {}
    if not used:
        return {}
    return {
        "matches": used,
        "recent_batting": [{"team": side, "batter": player, "runs": runs_scored}
                           for (side, player), runs_scored in batters.most_common(6)],
        "direct_batter_bowler": [{"batter": batter, "bowler": bowler, "non_wide_deliveries": count,
                                  "batter_runs": runs[batter, bowler]}
                                 for (batter, bowler), count in pairs.most_common(6) if count >= 6],
        "source_url": "https://cricsheet.org/downloads/",
    }


def _recent(history, teams):
    return [[row for row in history if side in row["teams"]][-WINDOW:] for side in teams]


@lru_cache(maxsize=12)
def _projections(path, _archive_revision, snapshot, format_name, category, league, cutoff, teams, lineups):
    history = [row for row in _archive(snapshot, format_name, category, league) if row["end"] < cutoff]
    return project(path, history, _recent(history, teams), teams, lineups, cutoff, format_name,
                   lambda name: _team(name, category))


def build_context(root, match, updated_at, lineups=((), ())):
    fixture = {key: match.get(key) or "" for key in FIXTURE_FIELDS}
    fixture["scoreboard_updated_at"] = updated_at or ""
    fixture["source_url"] = match.get("source_url") or (SCOREBOARD if fixture["id"] else "")
    cutoff = match.get("local_date") or datetime.fromisoformat(fixture["start"].replace("Z", "+00:00")).date().isoformat()
    tournament = name_key(fixture["tournament"])
    abu_dhabi = "abu dhabi" in tournament and "t10" in tournament
    if abu_dhabi:
        format_name = "T10"
    elif re.search(r"\bthe hundred\b", tournament):
        format_name = "100-ball"
    elif re.search(r"\bt20is?\b|\bt20 internationals?\b", tournament):
        format_name = "T20I"
    else:
        format_name = FORMATS.get(name_key(fixture["detail"]))
    category = "female" if re.search(r"\bwomen(?:s| s)?\b|\bw$", name_key(" ".join(
        fixture[key] for key in ("tournament", "team", "opponent")))) else "male"
    teams = tuple(_team(fixture[key], category) for key in ("team", "opponent"))
    context = {"fixture": fixture, "format": format_name, "cutoff": cutoff,
               "recent_form": [], "head_to_head": [], "player_history": {},
               "forecast": {"reason": "A pre-match forecast is unavailable for this competition."}}
    if not format_name or not all(teams) or teams[0] == teams[1]:
        context["archive_note"] = "Comparable history is unavailable for this fixture."
        return context
    try:
        snapshot = _snapshot(root)
        league = "abu dhabi t10" if abu_dhabi else ""
        history = [row for row in _archive(snapshot, format_name, category, league) if row["end"] < cutoff]
        if format_name == "T20" and not all(_recent(history, teams)):
            international = [row for row in _archive(snapshot, "T20I", category, "") if row["end"] < cutoff]
            if all(_recent(international, teams)):
                format_name = context["format"] = "T20I"
                history = international
    except (OSError, ValueError, KeyError, TypeError):
        context["archive_note"] = "The global cricket archive could not be read."
        return context

    recent = _recent(history, teams)
    meetings = [row for row in history if set(row["teams"]) == set(teams)][-5:][::-1]
    players = {row["id"]: row for row in [*recent[0][-2:], *recent[1][-2:], *meetings[:2]]}
    context.update({
        "archive_snapshot": snapshot.name,
        "recent_form": [{"team": fixture[key], "matches": [row["published"] for row in reversed(matches)]}
                        for key, matches in zip(("team", "opponent"), recent)],
        "head_to_head": [row["published"] for row in meetings],
        "player_history": _player_history(root, players.values(), teams, category),
    })
    if format_name == "Test" or abu_dhabi:
        context["forecast"] = forecast(history, fixture, teams, cutoff, format_name)
    path = root / "data/raw/cricket/all_json.zip"
    try:
        context["projections"] = _projections(path, path.stat().st_mtime_ns, snapshot, format_name, category,
                                               league, cutoff, teams, lineups)
    except (OSError, ValueError, KeyError, TypeError, BadZipFile):
        context["projection_note"] = "Ball-by-ball records could not be loaded for these projections."
    return context
