"""Team strength ratings from match results (Elo with a margin-of-victory multiplier).

The ball-by-ball simulator knows the players but not how often a side actually wins.
These ratings add that, and the two are blended for the win chance. Settings were
chosen on matches from one to four years back and checked on the most recent year.
Pure local computation.
"""
import json
import math
from functools import lru_cache

from .cricket_sim import FAMILIES, OVERS, load, team_key

K = {"short": 32.0, "long": 20.0}
START, NEW_TEAM_BOOST = 1500.0, 8.0
# National sides outside the ICC full members mostly play each other, which inflates their
# ratings against full members. Starting them 300 points lower fixed that in testing.
FULL_MEMBERS = {"india", "australia", "england", "south africa", "new zealand", "pakistan", "sri lanka", "west indies",
                "bangladesh", "afghanistan", "ireland", "zimbabwe"}
ASSOCIATE_START = START - 300.0
DEFAULT_BLEND = {"short": (0.5, 0.85), "long": (0.3, 0.6)}    # (simulator weight, rating weight) on the log-odds scale


def _multiplier(match, winner):
    """Bigger wins move ratings more: 0.7 for the narrowest, up to 1.6."""
    if match["adjusted"] or len(match["innings"]) < 2:
        return 1.0
    first, second = match["innings"][:2]
    if team_key(first["team"]) == winner:
        margin = (first["runs"] - second["runs"]) / max(first["runs"], 1)
    else:
        full = int(OVERS[match["fmt"]]) * 6
        margin = 0.6 * (full - second["balls"]) / full + 0.25 * (10 - second["wickets"]) / 10
    return 0.7 + 1.5 * min(max(margin, 0.0), 0.6)


def walk(matches, family, female, before_day=None, ratings=None, played=None):
    """Yield (match, rating of teams[0], rating of teams[1], games played by the less
    experienced side) before each match, in date order, then update the two tables."""
    ratings, played = {} if ratings is None else ratings, {} if played is None else played
    for match in sorted(matches, key=lambda m: m["day"]):
        if match["fmt"] not in FAMILIES[family] or (match["gender"] == "female") != female:
            continue
        if before_day is not None and match["day"] >= before_day:
            break
        a, b = (team_key(t) for t in match["teams"])
        for key in (a, b):
            if key not in ratings:
                ratings[key] = ASSOCIATE_START if match["intl"] and key not in FULL_MEMBERS else START
        ra, rb = ratings[a], ratings[b]
        yield match, ra, rb, min(played.get(a, 0), played.get(b, 0))
        winner = team_key(match["winner"]) if match["winner"] else None
        if winner not in (a, b):
            continue
        expected = 1 / (1 + 10 ** ((rb - ra) / 400))
        step = K[family] * _multiplier(match, winner) * ((1.0 if winner == a else 0.0) - expected)
        ratings[a] = ra + step * (1 + NEW_TEAM_BOOST / (played.get(a, 0) + 4))
        ratings[b] = rb - step * (1 + NEW_TEAM_BOOST / (played.get(b, 0) + 4))
        played[a], played[b] = played.get(a, 0) + 1, played.get(b, 0) + 1


@lru_cache(maxsize=8)
def table(root, family, female, before_day):
    """-> ({team key: rating}, {team key: results counted}) from matches before a day."""
    ratings, played = {}, {}
    for _ in walk(load(root).matches, family, female, before_day, ratings, played):
        pass
    return ratings, played


def log_odds(rating_a, rating_b):
    return (rating_a - rating_b) / 400 * math.log(10)


def blend_weights(root, family):
    """Weights fitted by tools/backtest_cricket_sim.py on held-out matches, else defaults."""
    name = "oneday" if family == "long" else "t20"
    try:
        saved = json.loads((root / f"artifacts/cricket-sim-backtest-{name}.json").read_text(encoding="utf-8"))["report"]["blend"]["weights"]
        return min(max(float(saved["simulator"]), 0.15), 1.0), min(max(float(saved["rating"]), 0.3), 1.2)
    except (OSError, ValueError, KeyError, TypeError):
        return DEFAULT_BLEND[family]


def blend(simulated, rating_edge, weights, share=1.0):
    """Win chance from the simulator's win chance and the rating edge (log-odds).
    share: how much of the pre-match blend still applies (1 before the start, 0 at the end)."""
    p = min(max(simulated, 0.002), 0.998)
    raw = math.log(p / (1 - p))
    mixed = weights[0] * raw + weights[1] * rating_edge
    return 1 / (1 + math.exp(-(share * mixed + (1 - share) * raw)))
