"""Descriptive associations for comparable cricket matches."""

import heapq
import math
from collections import defaultdict, deque
from functools import lru_cache
from statistics import mean

from matchlab.cricket_archive import index_by, normalized


TEAM_ALIASES = {
    "royal challengers bangalore": "royal challengers bengaluru",
    "delhi daredevils": "delhi capitals",
    "kings xi punjab": "punjab kings",
    "rising pune supergiants": "rising pune supergiant",
}


@lru_cache(maxsize=8192)
def team_identity(team):
    name = normalized(team)
    return TEAM_ALIASES.get(name, name)


def sides(match):
    return tuple(sorted(team_identity(match[key]) for key in ("team_a", "team_b")))


def decisive(match):
    return (match["result"] == "win" and match["winner"] in (match["team_a"], match["team_b"])
            and all(sides(match)))


def pre_match_form(matches):
    history = defaultdict(lambda: deque(maxlen=5))
    pending = []
    for index, match in enumerate(matches):
        day = match["start_date_local"]
        if not day:
            continue
        # Earlier starts can overlap multi-day matches. A match is eligible
        # for form once its result was available before this local date.
        while pending and pending[0][0] < day:
            _, _, prior = heapq.heappop(pending)
            winner = team_identity(prior["winner"])
            for team in sides(prior):
                history[team].append(team == winner)
        if decisive(match):
            a, b = sides(match)
            winner = team_identity(match["winner"])
            if len(history[a]) == len(history[b]) == 5:
                rate_a, rate_b = mean(history[a]), mean(history[b])
                if rate_a != rate_b:
                    yield match, int(winner == (a if rate_a > rate_b else b))
            if match.get("end_date_local"):
                heapq.heappush(pending, (match["end_date_local"], index, match))


def association(group_a, group_b=None, baseline=0):
    """Difference in means with a dyadic cluster-robust normal interval.

    The two teams in a match can reappear in other observations. Add
    covariance for observations sharing either team and subtract the
    duplicate contribution from observations sharing both teams.
    """
    if len(group_a) < 10 or (group_b is not None and len(group_b) < 10):
        return "", "", "", "Unknown", "Fewer than 10 eligible matches in a comparison group"
    team_sums, pair_sums = defaultdict(float), defaultdict(float)
    estimate = -baseline
    groups = [(group_a, 1)] if group_b is None else [(group_a, 1), (group_b, -1)]
    for group, sign in groups:
        average = mean(value for _, value in group)
        estimate += sign * average
        for match, value in group:
            pair = sides(match)
            residual = sign * (value - average) / len(group)
            for team in pair:
                team_sums[team] += residual
            pair_sums[pair] += residual
    variance = sum(value ** 2 for value in team_sums.values()) - sum(value ** 2 for value in pair_sums.values())
    if len(team_sums) < 10 or len(pair_sums) < 10 or variance <= 0:
        return estimate, "", "", "Low", "Too few team clusters or degenerate variance for an interval"
    se = math.sqrt(variance * len(team_sums) / (len(team_sums) - 1))
    return estimate, estimate - 1.96 * se, estimate + 1.96 * se, "Medium", "95% dyadic team-clustered interval"


def correlation_rows(matches, innings):
    first_innings = {i["match_id"]: i for i in innings if i["innings_number"] == 1 and i["legal_balls"]}
    cohorts = defaultdict(list)
    for match in matches:
        if not match["format"] or not match["team_category"] or not match["competition_level"]:
            continue
        label = (match["format"], match["team_category"], match.get("age_group", ""), match["competition_level"])
        cohorts[("", *label)].append(match)
        if match["competition_id"]:
            cohorts[(match["competition_id"], *label)].append(match)
    for (competition_id, match_format, category, age_group, level), cohort in sorted(cohorts.items()):
        cohort.sort(key=lambda row: (row["start_date_local"], row["match_id"]))
        first = cohort[0]
        name = (first["league"] or first["tournament"]) if competition_id else f"All {level} matches"
        days = [row["start_date_local"] for row in cohort if row["start_date_local"]]
        base = dict(competition_id=competition_id, competition_or_group=name, format=match_format,
                    team_category=category, age_group=age_group, competition_level=level,
                    date_range=f"{min(days)} to {max(days)}" if days else "")
        known = [m for m in cohort if m["confidence"] in {"High", "Medium"}]
        results = [m for m in known if decisive(m)]
        form = list(pre_match_form(known))
        toss = defaultdict(list)
        batting_order = []
        for match in results:
            toss_winner = match.get("toss_winner")
            decision = match.get("toss_decision")
            if toss_winner in (match["team_a"], match["team_b"]) and decision in {"bat", "field"}:
                toss[decision].append((match, int(toss_winner == match["winner"])))
            first_team = match.get("batting_first")
            if first_team in (match["team_a"], match["team_b"]):
                batting_order.append((match, int(first_team == match["winner"])))
        scoring = []
        for match in known:
            inning = first_innings.get(match["match_id"])
            if (inning and match["match_status"] == "completed" and match["venue"]
                    and all(sides(match)) and not match["result_method"]):
                scoring.append((match, 6 * inning["runs"] / inning["legal_balls"]))
        venues = index_by(scoring, lambda item: item[0]["venue"])
        comparisons = [
            ("Higher pre-match form", "Win rate above 50%", form, None, .5),
            ("Toss winner bats vs fields", "Toss winner win rate difference", toss["bat"], toss["field"], 0),
            ("Batting first", "Win rate above 50%", batting_order, None, .5),
        ]
        for venue, group in sorted(venues.items()):
            if len(group) >= 10:
                elsewhere = [item for item in scoring if item[0]["venue"] != venue]
                comparisons.append((venue, "First innings runs per six legal balls vs other venues", group, elsewhere, 0))
        if not any(len(group) >= 10 for group in venues.values()):
            comparisons.append(("Venue", "First innings runs per six legal balls vs other venues", [], [], 0))
        for factor, outcome, a, b, baseline in comparisons:
            estimate, lower, upper, confidence, reason = association(a, b, baseline)
            sample_size = len(a) + len(b or [])
            yield dict(base, factor=factor, outcome=outcome,
                       method="Difference in means with team-clustered 95% interval",
                       estimate=estimate, ci_lower=lower, ci_upper=upper,
                       confidence_interval=f"[{lower:.6f}, {upper:.6f}]" if lower != "" else "",
                       sample_size=sample_size, group_a_size=len(a), group_b_size=len(b) if b is not None else "",
                       excluded_count=len(cohort) - sample_size, confidence=confidence, confidence_reason=reason)
