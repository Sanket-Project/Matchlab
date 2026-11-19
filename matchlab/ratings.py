"""Causal Elo strength ratings and published rankings.

A rating asked for at a cutoff uses only results that were available strictly
before that cutoff. Each match's rating change is computed from what was known
before that match started, and takes effect on the date its result became
available (later than the start date for tennis tournaments). Cricket can
also apply a season reset and a training-selected update rate.
"""
import math
from bisect import bisect_left
from collections import defaultdict

BASE, K, HOME_ADVANTAGE, SCALE = 1500.0, 20.0, 60.0, 400.0
RATING_FEATURES = ["team_elo", "opponent_elo", "elo_diff", "elo_expected", "team_rated_matches", "opponent_rated_matches",
                   "team_rank_points_log", "opponent_rank_points_log", "rank_points_log_diff"]
RATING_DESCRIPTIONS = {
    "team_elo": "Focal side Elo strength rating from results available before the date (1500 = new side)",
    "opponent_elo": "Opposing side Elo strength rating",
    "elo_diff": "Focal minus opposing Elo rating, plus 60 at home / minus 60 away",
    "elo_expected": "Elo expected score for the focal side (0 to 1)",
    "team_rated_matches": "Results behind the focal side's rating",
    "opponent_rated_matches": "Results behind the opposing side's rating",
    "team_rank_points_log": "Log of focal side's most recent published ranking points (tennis only)",
    "opponent_rank_points_log": "Log of opposing side's most recent published ranking points (tennis only)",
    "rank_points_log_diff": "Difference of the two log ranking points",
}


def expected(diff):
    return 1.0 / (1.0 + 10 ** (-diff / SCALE))


class RatingIndex:
    def __init__(self, ds, *, k=K, cricket=None, season_pullback=0.0, matches=None):
        self.season_pullback = season_pullback
        self.season_starts = {}
        changes = defaultdict(list)   # side -> [(day, is_result, delta)]
        self.ranks = defaultdict(list)  # side -> [(published_date, points)]
        current = defaultdict(lambda: BASE)
        pending = []
        ordered = sorted(ds.matches if matches is None else matches,
                         key=lambda m: (m.get("pre_match_date") or m["date"], m["date"], m["match_id"]))
        for m in ordered:
            start = m.get("pre_match_date") or m["date"]
            still = []
            for available, side, delta in pending:
                if available < start:
                    current[side] += delta
                else:
                    still.append((available, side, delta))
            pending = still
            a, b = m["team"], m["opponent"]
            venue = m.get("venue") or "neutral"
            if cricket is not None:
                season = m.get("season")
                if season and season not in self.season_starts:
                    self.season_starts[season] = start
                    for side, rating in current.items():
                        pullback = (BASE - rating) * season_pullback
                        current[side] += pullback
                        changes[side].append((start, False, pullback))
                venue = cricket.match_venues[m["match_id"]]
            edge = HOME_ADVANTAGE if venue == "home" else -HOME_ADVANTAGE if venue == "away" else 0.0
            score = 1.0 if m["outcome"] == "team" else 0.0 if m["outcome"] == "opponent" else 0.5
            delta = k * (score - expected(current[a] - current[b] + edge))
            for side, change in ((a, delta), (b, -delta)):
                pending.append((m["date"], side, change))
                changes[side].append((m["date"], True, change))
            for side, column in ((a, "team_rank_points"), (b, "opponent_rank_points")):
                try:
                    points = float(m.get(column) or "")
                except ValueError:
                    continue
                if points > 0:
                    self.ranks[side].append((start, points))
        self.dates, self.totals, self.counts = {}, {}, {}
        for side, rows in changes.items():
            rows.sort()
            self.dates[side] = [(d, is_result) for d, is_result, _ in rows]
            running, totals, counts = BASE, [BASE], [0]
            for _, is_result, change in rows:
                running += change
                totals.append(running)
                counts.append(counts[-1] + is_result)
            self.totals[side], self.counts[side] = totals, counts
        self.rank_dates = {}
        for side, rows in self.ranks.items():
            rows.sort()
            self.rank_dates[side] = [d for d, _ in rows]

    def rating(self, side, cutoff):
        """(rating, results counted) from results available strictly before cutoff."""
        dates = self.dates.get(side)
        if not dates:
            return BASE, 0
        n = bisect_left(dates, (cutoff, True))
        return self.totals[side][n], self.counts[side][n]

    def rank_points(self, side, cutoff):
        """Most recent ranking points published strictly before cutoff, or None."""
        dates = self.rank_dates.get(side)
        if not dates:
            return None
        n = bisect_left(dates, cutoff)
        return self.ranks[side][n - 1][1] if n else None

    def features(self, team, opponent, cutoff, venue="neutral", *, season=None):
        (ra, na), (rb, nb) = self.rating(team, cutoff), self.rating(opponent, cutoff)
        if season and cutoff < self.season_starts.get(season, "9999-12-31"):
            # A known upcoming season can be forecast before its opening day.
            ra += (BASE - ra) * self.season_pullback
            rb += (BASE - rb) * self.season_pullback
        edge = HOME_ADVANTAGE if venue == "home" else -HOME_ADVANTAGE if venue == "away" else 0.0
        diff = ra - rb + edge
        pa, pb = self.rank_points(team, cutoff), self.rank_points(opponent, cutoff)
        la, lb = (math.log(p) if p else None for p in (pa, pb))
        return {"team_elo": ra, "opponent_elo": rb, "elo_diff": diff, "elo_expected": expected(diff),
                "team_rated_matches": na, "opponent_rated_matches": nb,
                "team_rank_points_log": la, "opponent_rank_points_log": lb,
                "rank_points_log_diff": la - lb if la is not None and lb is not None else None}
