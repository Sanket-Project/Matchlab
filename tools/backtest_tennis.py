"""Held-out check of the tennis ratings: every match is predicted from earlier matches only.

python tools/backtest_tennis.py            -> artifacts/tennis-backtest.json
Scored on main-draw tour-level matches in the last 365 days of the archive, against the
simple baseline "the better-ranked player wins".
"""
import json
import math
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from matchlab import tennis_forecast as tf  # noqa: E402


def run(tour, surface_weight=None):
    if surface_weight is not None:
        tf.SURFACE_WEIGHT = surface_weight
    rows = tf.read_rows(ROOT, tour)
    end = rows[-1]["day"]
    table, scored = tf.Ratings(tour), []
    for row in rows:
        level = row.get("tourney_level") or ""
        tour_level = row["main"] and level not in ("C", "S", "15", "25", "35", "40", "50", "60", "75", "80", "100", "D")
        if row["day"] > end - 365 and tour_level and "W/O" not in row["score"].upper() and row["score"].strip():
            winner, loser = table.players.get(row["winner_id"]), table.players.get(row["loser_id"])
            if winner and loser and min(winner.played, loser.played) >= 10:
                p = table.expected(winner, loser, row["surface"] or "Hard")
                ranks = [tf._number(row.get(k)) for k in ("winner_rank", "loser_rank")]
                scored.append((p, None if not all(ranks) or ranks[0] == ranks[1] else ranks[0] < ranks[1]))
        table.add(row)
    ranked = [r for _, r in scored if r is not None]
    return {"matches": len(scored), "window": [str(date.fromordinal(end - 365)), str(date.fromordinal(end))],
            "accuracy": sum(p > 0.5 for p, _ in scored) / len(scored),
            "log_loss": -sum(math.log(min(max(p, 0.01), 0.99)) for p, _ in scored) / len(scored), "coin_flip_log_loss": 0.6931,
            "better_ranked_wins": sum(ranked) / len(ranked), "surface_weight": tf.SURFACE_WEIGHT}


if __name__ == "__main__":
    if "--grid" in sys.argv:
        for weight in (0.0, 0.3, 0.5, 0.7, 1.0):
            print(weight, {tour: {k: round(v, 4) for k, v in run(tour, weight).items() if k in ("accuracy", "log_loss", "matches")} for tour in ("atp", "wta")})
        sys.exit()
    report = {tour: run(tour) for tour in ("atp", "wta")}
    (ROOT / "artifacts/tennis-backtest.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
