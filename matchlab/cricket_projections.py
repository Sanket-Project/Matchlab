"""Causal player and cumulative team forecasts from Cricsheet deliveries."""
from bisect import bisect_left
from collections import Counter, defaultdict
from functools import lru_cache
from json import JSONDecoder, loads
from math import sqrt
from statistics import mean
from zipfile import ZipFile

from .cricket_archive import CRICSHEET
from .live import name_key

WINDOW = 15
MIN_MATCHES = 3
BOWLER_WICKETS = {"bowled", "caught", "caught and bowled", "lbw", "stumped", "hit wicket"}
OVER_LIMITS = {"T10": 10, "T20": 20, "T20I": 20, "ODI": 50, "One-day": 50, "Test": 90, "Multi-day": 90}


def _info(archive, filename):
    # Cricsheet puts the lineup and registry before the much larger innings array.
    with archive.open(filename) as file:
        raw = file.read(8192)
        while raw:
            header = raw.decode("utf-8", errors="ignore")
            start = header.find('"info"')
            if start != -1:
                try:
                    return JSONDecoder().raw_decode(header, header.index("{", start))[0]
                except ValueError:
                    pass
            chunk = file.read(8192)
            if not chunk:
                break
            raw += chunk
    raise ValueError("Cricsheet match metadata is missing")


def _scorecard(document, checkpoints, side_key):
    info = document["info"]
    identities = info["registry"]["people"]
    runs, wickets = Counter(), Counter()
    batted, bowled = set(), set()
    innings = {}
    outcome = info.get("outcome", {})
    adjusted = outcome.get("method") or outcome.get("result") == "no result"
    played = False
    for inning in document.get("innings", []):
        if inning.get("super_over") or inning.get("forfeited"):
            continue
        side = side_key(inning["team"])
        penalty = inning.get("penalty_runs", {})
        total, balls, timeline = penalty.get("pre", 0), 0, []
        for over in inning.get("overs", []):
            for ball in over["deliveries"]:
                played = True
                batter, bowler = (identities.get(ball[key]) for key in ("batter", "bowler"))
                runs[batter] += ball["runs"]["batter"]
                batted.update((batter, identities.get(ball.get("non_striker"))))
                bowled.add(bowler)
                wickets[bowler] += sum(w["kind"] in BOWLER_WICKETS for w in ball.get("wickets", []))
                total += ball["runs"]["total"]
                extras = ball.get("extras", {})
                if extras.get("wides") or extras.get("noballs"):
                    continue
                balls += 1
                if len(timeline) < len(checkpoints) and balls == checkpoints[len(timeline)]:
                    timeline.append(total)
        if balls and not adjusted and side not in innings:
            total += penalty.get("post", 0)
            if timeline and balls == checkpoints[len(timeline) - 1]:
                timeline[-1] = total
            innings[side] = timeline + [total] * (len(checkpoints) - len(timeline))
    return innings, runs, wickets, batted, bowled, played


def _neighbors(examples, features, scales):
    """Distance-weighted k-nearest-neighbor regression with shared weights across outputs."""
    if not examples:
        return None
    neighbors = []
    for historical, target in examples:
        distance = sum(((a - b) / scale) ** 2 for a, b, scale in zip(historical, features, scales))
        neighbors.append((distance, target))
    k = min(len(neighbors), max(5, round(sqrt(len(neighbors)))))
    closest = sorted(neighbors, key=lambda item: item[0])[:k]
    weights = [1 / (1 + distance) for distance, _ in closest]
    return [sum(weight * value for weight, value in zip(weights, column)) / sum(weights)
            for column in zip(*(target for _, target in closest))]


def _player_features(matches):
    return tuple(mean(row[key] for row in matches) for key in ("runs", "wickets", "batted", "bowled"))


def _player_estimates(rosters, appearances, format_name):
    training = []
    for matches in appearances.values():
        for index, row in enumerate(matches):
            past = [match for match in matches[:index] if match["end"] < row["date"]][-WINDOW:]
            if len(past) >= 2:
                training.append((_player_features(past), (row["runs"], row["wickets"])))
    long_form = format_name in ("Test", "Multi-day")
    results = []
    for roster in rosters:
        players = []
        for player_id, name in roster["players"]:
            matches = appearances.get(player_id, [])
            estimate = None
            if len(matches) >= MIN_MATCHES:
                estimate = _neighbors(training, _player_features(matches),
                                      (50 if long_form else 25, 2 if long_form else 1, 0.4, 0.4))
            players.append({
                "name": name, "runs": round(estimate[0], 1) if estimate else None,
                "wickets": round(estimate[1], 2) if estimate else None,
                "matches": [{k: v for k, v in row.items() if k != "end"} for row in reversed(matches)],
            })
        results.append({"source": roster["source"], "squad_date": roster["squad_date"], "players": players})
    return results


def _team_estimates(history, recent, teams, trajectories, cutoff, long_form):
    indexed = defaultdict(list)
    for row in history:
        for side in row["teams"]:
            indexed[side].append(row)

    @lru_cache(maxsize=None)
    def form(side, before, batting):
        rows = indexed[side]
        index = bisect_left(rows, before, key=lambda row: row["end"])
        values = [score for row in rows[max(0, index - WINDOW):index]
                  for name, score in row["scores"].items() if (name == side) == batting]
        return mean(values) if values else None

    results = []
    for index, side in enumerate(teams):
        opponent = teams[1 - index]
        features = (form(side, cutoff, True), form(opponent, cutoff, False))
        examples, used = [], set()
        batting_matches = sum((row["id"], side) in trajectories for row in recent[index])
        for rows, known, batting in ((recent[index], side, True), (recent[1 - index], opponent, False)):
            for row in rows:
                rival = next(t for t in row["teams"] if t != known)
                batter, bowler = (known, rival) if batting else (rival, known)
                key = (row["id"], batter)
                target = trajectories.get(key)
                if target is None or key in used:
                    continue
                used.add(key)
                past = (form(batter, row["start"], True), form(bowler, row["start"], False))
                if None not in past:
                    examples.append((past, target))
        estimate = None
        if batting_matches >= MIN_MATCHES and len(examples) >= MIN_MATCHES and None not in features:
            scale = 90 if long_form else 35
            estimate = _neighbors(examples, features, (scale, scale))
        latest = next((row["end"] for row in reversed(recent[index]) if (row["id"], side) in trajectories), None)
        results.append({"matches": batting_matches, "training_innings": len(examples), "as_of": latest,
                        "runs": [round(value) for value in estimate] if estimate is not None else None})
    return results


def _roster(read_info, rows, filenames, side, side_key, lineup, history, cutoff):
    if not lineup:
        for row in reversed(rows):
            filename = filenames.get(row["id"])
            if filename is None:
                continue
            info = read_info(filename)
            names = next((names for team, names in info["players"].items() if side_key(team) == side), [])
            if names:
                return {"players": [(info["registry"]["people"][name], name) for name in names],
                        "source": "Last archived playing squad", "squad_date": row["end"]}
        return {"players": [], "source": "Playing squad unavailable", "squad_date": None}
    wanted = {name_key(name) for name in lineup}
    resolved = {}
    for row in reversed(history):
        filename = filenames.get(row["id"])
        if filename is None or side not in row["teams"]:
            continue
        info = read_info(filename)
        for team, names in info["players"].items():
            if side_key(team) != side:
                continue
            for name in names:
                key = name_key(name)
                if key in wanted:
                    resolved[key] = info["registry"]["people"][name]
                    wanted.remove(key)
        if not wanted:
            break
    return {"players": [(resolved.get(name_key(name)), name) for name in lineup],
            "source": "Entered starting XI", "squad_date": cutoff}


def project(zip_path, history, recent, teams, lineups, cutoff, format_name, side_key):
    hundred = format_name == "100-ball"
    labels = list(range(25, 101, 25) if hundred else range(5, OVER_LIMITS[format_name] + 1, 5))
    checkpoints = labels if hundred else [6 * over for over in labels]
    appearances = defaultdict(list)
    trajectories = {}
    with ZipFile(zip_path) as archive:
        read_info = lru_cache(maxsize=128)(lambda filename: _info(archive, filename))
        members = set(archive.namelist())
        filenames = {row["id"]: filename for row in history if row["data_source"] == "Cricsheet"
                     if (filename := f'{row["source_id"]}.json') in members}
        rosters = [_roster(read_info, rows, filenames, side, side_key, lineup, history, cutoff)
                   for side, rows, lineup in zip(teams, recent, lineups)]
        targets = {pid for roster in rosters for pid, _ in roster["players"] if pid is not None}
        team_matches = {row["id"] for rows in recent for row in rows} & filenames.keys()
        for row in reversed(history):
            mid = row["id"]
            if not targets and not team_matches:
                break
            if mid not in filenames:
                continue
            players = []
            if targets:
                info = read_info(filenames[mid])
                registry = info["registry"]["people"]
                for team, names in info["players"].items():
                    for name in names:
                        pid = registry.get(name)
                        if pid in targets:
                            players.append((pid, team))
            if not players and mid not in team_matches:
                continue
            card = _scorecard(loads(archive.read(filenames[mid])), checkpoints, side_key)
            innings, runs, wickets, batted, bowled, played = card
            if mid in team_matches:
                team_matches.remove(mid)
                trajectories.update({(mid, side): values for side, values in innings.items()})
            if played:
                for pid, team in players:
                    if pid not in targets:
                        continue
                    opponent = next(name for name in row["published"]["teams"] if side_key(name) != side_key(team))
                    appearances[pid].append({"date": row["start"], "end": row["end"], "team": team,
                                             "opponent": opponent, "runs": runs[pid], "wickets": wickets[pid],
                                             "batted": pid in batted, "bowled": pid in bowled})
                    if len(appearances[pid]) == WINDOW:
                        targets.remove(pid)
    for matches in appearances.values():
        matches.reverse()
    batting = _team_estimates(history, recent, teams, trajectories, cutoff, format_name in ("Test", "Multi-day"))
    players = _player_estimates(rosters, appearances, format_name)
    return {
        "model": "Distance-weighted nearest-neighbor regression",
        "window": WINDOW, "minimum_matches": MIN_MATCHES,
        "source_url": CRICSHEET, "checkpoint_unit": "Balls" if hundred else "Overs", "checkpoints": labels,
        "sides": [{**team, **squad} for team, squad in zip(batting, players)],
    }
