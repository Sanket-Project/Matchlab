"""Create fictional CSV fixtures for UI tests. Does not train or create models."""
import csv
import random
import sys
from datetime import date, timedelta
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from matchlab.sports import SPORTS

PEOPLE = ["Aarav Mehta", "Leo Bennett", "Noah Clarke", "Rohan Iyer", "Ethan Brooks", "Arjun Rao"]
CLUBS = ["Northbridge", "Eastvale", "Westport", "Rivergate", "Kingsford", "Lakeside"]
SUFFIX = {"football": "FC", "cricket": "CC", "baseball": "Bears", "rugby": "RFC"}


def write(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def generate():
    for index, sport in enumerate(key for key, meta in SPORTS.items() if meta["kind"] == "match"):
        rng = random.Random(8300 + index)
        singles = sport in ("tennis", "badminton")
        sides = PEOPLE if singles else [f"{c} {SUFFIX[sport]}" for c in CLUBS]
        rosters = {side: [side] if singles else [PEOPLE[i], f"{['Sam', 'Dev', 'Oliver', 'Finn', 'Kian', 'Max'][i]} {['Wilson', 'Patel', 'Hayes', 'Reed', 'Sen', 'Hart'][i]}", f"{['Adam', 'Ishaan', 'Ryan', 'Nikhil', 'Oscar', 'James'][i]} {['Cole', 'Das', 'Stone', 'Shah', 'Lane', 'Roy'][i]}"] for i, side in enumerate(sides)}
        matches, players, interactions = [], [], []
        schedule = list(combinations(range(6), 2)) * 6
        for i, (a, b) in enumerate(schedule):
            if i % 2:
                a, b = b, a
            side, other = sides[a], sides[b]
            if sport == "football":
                scores = [rng.choices([0, 1, 2, 3, 4], [1, 4, 4+(5-x)/3, 2, 1])[0] for x in (a, b)]
            elif sport == "cricket":
                scores = [max(85, round(rng.gauss(162 + (3-x)*5, 24))) for x in (a, b)]
            elif singles:
                win_a = rng.random() < .5 + (b-a)*.045
                scores = [2, rng.randint(0, 1)] if win_a else [rng.randint(0, 1), 2]
            elif sport == "baseball":
                scores = [max(0, round(rng.gauss(4.8 + (3-x)*.3, 2.4))) for x in (a, b)]
                if scores[0] == scores[1]:
                    scores[rng.randint(0, 1)] += 1
            else:
                scores = [max(0, round(rng.gauss(23 + (3-x)*2, 10))) for x in (a, b)]
            match_id = f"{sport[:3]}-{i+1:03}"
            matches.append(dict(match_id=match_id, date=(date(2026, 8, 1)+timedelta(days=i)).isoformat(), team=side, opponent=other,
                                team_score=scores[0], opponent_score=scores[1], outcome="team" if scores[0] > scores[1] else "opponent" if scores[0] < scores[1] else "draw"))
            for j, team in enumerate((side, other)):
                remainder = scores[j]
                for p in rosters[team]:
                    if sport == "football":
                        score = rng.randint(0, remainder)
                        remainder -= score
                    elif sport == "cricket":
                        score = min(remainder, max(0, round(rng.gauss(32, 18))))
                        remainder -= score
                    elif sport == "tennis":
                        score = rng.randint(1, 15)
                    elif sport == "badminton":
                        score = rng.randint(30, 65) if scores[j] == 2 else rng.randint(18, 55)
                    elif sport == "baseball":
                        score = rng.choices([0, 1, 2, 3, 4], [3, 5, 3, 1, .2])[0]
                    else:
                        score = min(remainder, rng.choice([0, 3, 5, 7, 10, 12]))
                        remainder -= score
                    players.append(dict(match_id=match_id, player=p, team=team, score=score))
            for focal, opposing in ((side, other), (other, side)):
                for p in rosters[focal]:
                    for op in rosters[opposing]:
                        n = rng.randint(4, 15) if not singles else rng.randint(60, 140)
                        rate = {"football": .42, "cricket": .18, "tennis": .51, "badminton": .5, "baseball": .26, "rugby": .2}[sport]
                        successes = sum(rng.random() < rate for _ in range(n))
                        interactions.append(dict(match_id=match_id, player=p, opponent_player=op, opportunities=n,
                                                 successes=successes, score=successes*(4 if sport == "cricket" else 1)))
        folder = ROOT / "data" / "demo" / sport
        folder.mkdir(parents=True, exist_ok=True)
        write(folder / "matches.csv", ["match_id", "date", "team", "opponent", "team_score", "opponent_score", "outcome"], matches)
        write(folder / "players.csv", ["match_id", "player", "team", "score"], players)
        write(folder / "interactions.csv", ["match_id", "player", "opponent_player", "opportunities", "successes", "score"], interactions)
        print(f"{sport}: {len(matches)} synthetic matches")


if __name__ == "__main__":
    generate()
