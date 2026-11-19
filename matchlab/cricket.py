"""Causal IPL fixture context and pre-match and post-toss features."""
from bisect import bisect_left
from collections import Counter, defaultdict
from itertools import accumulate
from statistics import mean

MIN_GROUND_MATCHES = 5
GROUND_FEATURES = ["ground_first_innings_mean", "ground_batting_first_win_rate"]
SQUAD_FEATURES = ["runs", "batting_boundary_rate", "bowling_boundary_rate"]
CRICKET_FEATURES = GROUND_FEATURES + [f"{side}_squad_{name}" for side in ("team", "opponent") for name in SQUAD_FEATURES]
PRE_MATCH, POST_TOSS = "pre_match", "post_toss"
POST_TOSS_FEATURES = ["toss_won", "toss_decision_bat", "toss_decision_ground_win_rate"]


def match_start(match):
    return match.get("pre_match_date") or match["date"]


def validate_post_toss(inputs, team, opponent):
    winner, decision = inputs.get("toss_winner"), inputs.get("toss_decision")
    if winner not in (team, opponent):
        raise ValueError("Select one of the two sides as the toss winner")
    if decision not in ("bat", "field"):
        raise ValueError("Toss decision must be bat or field")
    result = dict(toss_winner=winner, toss_decision=decision)
    for key, side in (("team_xi", team), ("opponent_xi", opponent)):
        names = inputs.get(key)
        if (not isinstance(names, list) or len(names) != 11
                or any(not isinstance(name, str) or not name.strip() for name in names)):
            raise ValueError(f"Enter 11 player names for {side}'s starting XI")
        result[key] = [name.strip() for name in names]
        if len({name.casefold() for name in result[key]}) != 11:
            raise ValueError(f"{side}'s starting XI must contain 11 distinct players")
    if {name.casefold() for name in result["team_xi"]} & {name.casefold() for name in result["opponent_xi"]}:
        raise ValueError("A player cannot appear in both XIs")
    return result


def reverse_xis(inputs):
    return {**inputs, "team_xi": inputs["opponent_xi"], "opponent_xi": inputs["team_xi"]}


class CricketHistory:
    def __init__(self, ds, history):
        self.history = history
        self.season_starts = {}
        self.fixtures = defaultdict(list)
        self.venues = defaultdict(list)
        grounds = defaultdict(list)
        for m in sorted(ds.matches, key=lambda m: (match_start(m), m["match_id"])):
            start, season = match_start(m), m.get("season")
            if season:
                self.season_starts.setdefault(season, start)
            ground = m.get("ground")
            self.fixtures[(start, frozenset((m["team"], m["opponent"])))].append((ground, season))
            if not ground:
                continue
            for side in (m["team"], m["opponent"]):
                if season:
                    self.venues[side].append((m["date"], season, ground))
            batting_first = m.get("batting_first")
            if batting_first in (m["team"], m["opponent"]):
                side = "team" if batting_first == m["team"] else "opponent"
                grounds[ground].append((m["date"], m[f"{side}_score"], int(m["outcome"] == side)))
        self.grounds = {}
        for ground, rows in grounds.items():
            dates, scores, wins = zip(*sorted(rows))
            self.grounds[ground] = (dates, list(accumulate(scores, initial=0)), list(accumulate(wins, initial=0)))
        self.match_venues = {
            m["match_id"]: self.venue(m["team"], m["opponent"], match_start(m), m.get("ground"),
                                      m.get("season"), m.get("venue") or "neutral")
            for m in ds.matches
        }

        appearances = defaultdict(list)
        self.players = defaultdict(list)
        for p in ds.players:
            appearances[(p["match_id"], p["team"])].append(p)
            self.players[p["player"]].append(p)
        self.xis = {}
        for key, rows in appearances.items():
            if all(p.get("starter") in ("0", "1") for p in rows):
                starters = [p["player"] for p in rows if p["starter"] == "1"]
            else:
                starters = [p["player"] for p in rows] if all("starter" not in p for p in rows) else []
            if len(starters) == 11:
                self.xis[key] = starters
        # Sum all opposing batters/bowlers into one record per player appearance.
        self.batting, self.bowling = (self.action_totals(mapping) for mapping in (history.actions, history.defending))
        self.dates = {}
        for mapping in (self.players, self.batting, self.bowling):
            for rows in mapping.values():
                rows.sort(key=lambda r: (r["date"], r["match_id"]))
                self.dates[id(rows)] = [r["date"] for r in rows]

    @staticmethod
    def action_totals(mapping):
        totals = {}
        for player, rows in mapping.items():
            matches = {}
            for r in rows:
                mid = r["match_id"]
                total = matches.setdefault(mid, dict(match_id=mid, date=r["date"], opportunities=0, successes=0))
                total["opportunities"] += r["opportunities"]
                total["successes"] += r["successes"]
            totals[player] = list(matches.values())
        return totals

    def fixture(self, team, opponent, cutoff, ground=None, season=None):
        matches = self.fixtures.get((cutoff, frozenset((team, opponent))), [])
        if len(matches) == 1:
            fixture_ground, fixture_season = matches[0]
            ground = ground or fixture_ground
            season = season or fixture_season
        return ground, season

    def home_ground(self, side, cutoff, season):
        year = season if season and len(season) == 4 and season.isdigit() else cutoff[:4]
        start = self.season_starts.get(season, f"{year}-01-01")
        counts = Counter(ground for day, played_season, ground in self.venues.get(side, ())
                         if day < cutoff and played_season != season and self.season_starts[played_season] < start)
        leaders = counts.most_common(2)
        if leaders and (len(leaders) == 1 or leaders[0][1] > leaders[1][1]):
            return leaders[0][0]
        return None

    def venue(self, team, opponent, cutoff, ground, season, fallback="neutral"):
        if not ground:
            return fallback
        home, away = (self.home_ground(side, cutoff, season) == ground for side in (team, opponent))
        if home == away:
            return "neutral"
        return "home" if home else "away"

    def ground_features(self, ground, cutoff):
        dates, scores, wins = self.grounds.get(ground, ((), (), ()))
        n = bisect_left(dates, cutoff)
        return (scores[n] / n, wins[n] / n) if n >= MIN_GROUND_MATCHES else (None, None)

    def recent(self, mapping, player, cutoff, window):
        rows = mapping.get(player)
        if rows is None:
            return []
        n = bisect_left(self.dates[id(rows)], cutoff)
        return rows[max(0, n - window):n]

    def last_xi(self, side, cutoff):
        last = self.history.before(self.history.sides, side, cutoff, 2)
        if not last or (len(last) == 2 and last[-1]["date"] == last[-2]["date"]):
            return ()
        return self.xis.get((last[-1]["match_id"], side), ())

    def recorded_post_toss(self, match):
        """Return the toss and starting XIs for this exact historical fixture."""
        mid, team, opponent = match["match_id"], match["team"], match["opponent"]
        fields = dict(toss_winner=match.get("toss_winner"), toss_decision=match.get("toss_decision"),
                      team_xi=self.xis.get((mid, team)), opponent_xi=self.xis.get((mid, opponent)))
        try:
            return validate_post_toss(fields, team, opponent)
        except ValueError:
            return None

    def squad_features(self, players, cutoff, window):
        runs = [mean(r["score"] for r in rows) for player in players
                if (rows := self.recent(self.players, player, cutoff, window))]

        def boundary_rate(mapping):
            rows = [r for player in players for r in self.recent(mapping, player, cutoff, window)]
            opportunities = sum(r["opportunities"] for r in rows)
            return sum(r["successes"] for r in rows) / opportunities if opportunities else None

        return mean(runs) if runs else None, boundary_rate(self.batting), boundary_rate(self.bowling)

    def features(self, team, opponent, cutoff, window, ground, post_toss=None):
        runs, batting_first_win_rate = self.ground_features(ground, cutoff)
        if post_toss is None:
            team_xi, opponent_xi = self.last_xi(team, cutoff), self.last_xi(opponent, cutoff)
        else:
            team_xi, opponent_xi = post_toss["team_xi"], post_toss["opponent_xi"]
        values = (runs, batting_first_win_rate, *self.squad_features(team_xi, cutoff, window),
                  *self.squad_features(opponent_xi, cutoff, window))
        row = dict(zip(CRICKET_FEATURES, values))
        if post_toss is not None:
            bats = int(post_toss["toss_decision"] == "bat")
            row.update(toss_won=int(post_toss["toss_winner"] == team), toss_decision_bat=bats,
                       toss_decision_ground_win_rate=bats * batting_first_win_rate if batting_first_win_rate is not None else None)
        return row
