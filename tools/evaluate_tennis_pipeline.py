"""Multi-model tennis prediction pipeline combining Surface Elo, Point Simulation, and Context.

Minimalist implementation adhering to Ponytail's principles (zero unnecessary dependencies).
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from matchlab import tennis_forecast as tf
from matchlab.data import Dataset
from matchlab.sports import SPORTS
from matchlab.trained import TrainedModels


def evaluate_backtest():
    """Run held-out expanding window validation across ATP and WTA archives."""
    results = {}
    for tour in ("atp", "wta"):
        rows = tf.read_rows(ROOT, tour)
        end = rows[-1]["day"]
        table = tf.Ratings(tour)
        scored = []
        for row in rows:
            level = row.get("tourney_level") or ""
            tour_level = row["main"] and level not in ("C", "S", "15", "25", "35", "40", "50", "60", "75", "80", "100", "D")
            # Only score matches in the held-out final 365 days of historical data
            if row["day"] > end - 365 and tour_level and "W/O" not in row["score"].upper() and row["score"].strip():
                winner = table.players.get(row["winner_id"])
                loser = table.players.get(row["loser_id"])
                if winner and loser and min(winner.played, loser.played) >= 10:
                    surface = row.get("surface") or "Hard"
                    # Layer 1 & 2: Surface Elo + Point Level Serving/Return Dynamics
                    p = table.expected(winner, loser, surface)
                    p = min(max(p, 0.01), 0.99)
                    ranks = [tf._number(row.get(k)) for k in ("winner_rank", "loser_rank")]
                    better_rank = None if not all(ranks) or ranks[0] == ranks[1] else ranks[0] < ranks[1]
                    scored.append((p, better_rank))
            table.add(row)

        n = len(scored)
        correct = sum(p > 0.5 for p, _ in scored)
        log_loss = -sum(math.log(p) for p, _ in scored) / n
        brier = sum((1.0 - p) ** 2 for p, _ in scored) / n
        ranked = [r for _, r in scored if r is not None]
        rank_acc = sum(ranked) / len(ranked) if ranked else 0.0

        results[tour.upper()] = {
            "matches": n,
            "accuracy": round(correct / n, 4),
            "log_loss": round(log_loss, 4),
            "brier_score": round(brier, 4),
            "baseline_ranked_accuracy": round(rank_acc, 4),
            "coin_flip_log_loss": 0.6931,
            "beats_ranking_baseline": (correct / n) > rank_acc,
            "beats_coin_flip": log_loss < 0.6931,
        }
    return results


def analyze_today_matches():
    """Run the multi-model pipeline on today's scheduled matches."""
    today_file = ROOT / "data/today_matches.json"
    if not today_file.exists():
        return []
    data = json.loads(today_file.read_text(encoding="utf-8"))
    matches = data.get("sports", {}).get("tennis", [])
    predictions = []
    for m in matches:
        forecast = tf.build(ROOT, m, None)
        if not forecast.get("supported"):
            continue
        t0, t1 = forecast["teams"]
        set_scores = forecast.get("set_scores", [])
        top_set = max(set_scores, key=lambda s: s["chance"]) if set_scores else None
        predictions.append({
            "match_id": m["id"],
            "tournament": m.get("tournament", "Tennis"),
            "player_a": t0["name"],
            "player_b": t1["name"],
            "surface": forecast.get("surface", {}).get("name", "Hard"),
            "win_probability_a": round(t0["win"], 3),
            "win_probability_b": round(t1["win"], 3),
            "rating_a": t0.get("rating", {}).get("blended"),
            "rating_b": t1.get("rating", {}).get("blended"),
            "hold_rate_a": round(t0.get("hold", 0.0), 3),
            "hold_rate_b": round(t1.get("hold", 0.0), 3),
            "top_predicted_score": f"{top_set['winner']} in {top_set['score']} ({top_set['chance']:.1%})" if top_set else "N/A",
            "h2h": f"{forecast.get('h2h', {}).get('wins', [0, 0])[0]}-{forecast.get('h2h', {}).get('wins', [0, 0])[1]}",
        })
    return predictions


if __name__ == "__main__":
    print("--- 1. Running Chronological Backtest (Past 365 Days) ---")
    backtest = evaluate_backtest()
    print(json.dumps(backtest, indent=2))

    print("\n--- 2. Predictions for Today's Scheduled Matches ---")
    today_preds = analyze_today_matches()
    for p in today_preds:
        print(f"[{p['tournament']}] {p['player_a']} ({p['win_probability_a']:.1%}) vs {p['player_b']} ({p['win_probability_b']:.1%}) | Surface: {p['surface']} | Favorite: {p['top_predicted_score']}")
