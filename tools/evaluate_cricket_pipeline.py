"""Multi-model cricket prediction pipeline combining Season-Aware Elo, TabICL/Logistic, and Monte Carlo Ball Simulator.

Minimalist implementation adhering to Ponytail's principles (zero unnecessary dependencies).
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from matchlab import cricket_forecast as cf, cricket_ratings as cr
from matchlab.cricket_sim import FAMILIES, Model, load, team_key
from matchlab.data import Dataset
from matchlab.sports import SPORTS
from matchlab.trained import TrainedModels


def evaluate_backtest_summary():
    """Load and format the held-out backtest results for the cricket ensemble."""
    t20_file = ROOT / "artifacts/cricket-sim-backtest-t20.json"
    ipl_file = ROOT / "artifacts/model-comparison.json"
    summary = {}
    if t20_file.exists():
        t20_data = json.loads(t20_file.read_text(encoding="utf-8"))["report"]
        summary["T20_Global_500_Matches"] = {
            "window": t20_data.get("window"),
            "matches": t20_data.get("matches"),
            "simulator_alone": {
                "accuracy": round(t20_data["blend"]["simulator_only"]["accuracy"], 4),
                "log_loss": round(t20_data["blend"]["simulator_only"]["log_loss"], 4),
            },
            "rating_alone": {
                "accuracy": round(t20_data["blend"]["rating_only"]["accuracy"], 4),
                "log_loss": round(t20_data["blend"]["rating_only"]["log_loss"], 4),
            },
            "multi_model_blend": {
                "accuracy": round(t20_data["blend"]["blend"]["accuracy"], 4),
                "log_loss": round(t20_data["blend"]["blend"]["log_loss"], 4),
                "weights": t20_data["blend"]["weights"],
            },
            "score_mae_runs": round(t20_data["first_innings_mae"]["simulator"], 2),
            "baseline_score_mae_runs": round(t20_data["first_innings_mae"]["venue_average"], 2),
        }

    if ipl_file.exists():
        ipl_data = json.loads(ipl_file.read_text(encoding="utf-8"))["sports"]["cricket"]
        pre = ipl_data["stages"]["pre_match"]
        post = ipl_data["stages"]["post_toss"]
        summary["IPL_Heldout_239_Matches"] = {
            "split_date": ipl_data["split"],
            "pre_toss": {
                "tabicl_accuracy": round(pre["winner"]["tabicl"]["accuracy"], 4),
                "tabicl_log_loss": round(pre["winner"]["tabicl"]["log_loss"], 4),
                "tabicl_brier": round(pre["winner"]["tabicl"]["multiclass_brier"], 4),
                "ridge_score_mae_runs": round(pre["team_score"]["trained_ridge"]["mae"], 2),
                "baseline_score_mae_runs": round(pre["team_score"]["recent_5_mean"]["mae"], 2),
            },
            "post_toss": {
                "logistic_accuracy": round(post["winner"]["trained_logistic"]["accuracy"], 4),
                "logistic_log_loss": round(post["winner"]["trained_logistic"]["log_loss"], 4),
                "logistic_brier": round(post["winner"]["trained_logistic"]["multiclass_brier"], 4),
                "ridge_score_mae_runs": round(post["team_score"]["trained_ridge"]["mae"], 2),
            },
        }
    return summary


def analyze_today_cricket_matches():
    """Run the 3-model ensemble on today's evening cricket matches."""
    today_file = ROOT / "data/today_matches.json"
    if not today_file.exists():
        return []
    data = json.loads(today_file.read_text(encoding="utf-8"))
    matches = data.get("sports", {}).get("cricket", [])
    predictions = []
    for m in matches:
        if m.get("state") not in ("pre", "in"):
            continue
        forecast = cf.build(ROOT, m, None)
        if not forecast.get("supported"):
            continue
        teams = forecast.get("teams", [])
        if len(teams) != 2:
            continue
        t0, t1 = teams
        inn0 = t0.get("first_innings", {})
        inn1 = t1.get("first_innings", {})
        predictions.append({
            "match_id": m["id"],
            "tournament": m.get("tournament", "Cricket"),
            "stage": forecast.get("stage", "pre_toss"),
            "team_a": t0["name"],
            "team_b": t1["name"],
            "win_probability_a": round(t0["win"], 3),
            "win_probability_b": round(t1["win"], 3),
            "sim_win_a": round(t0.get("win_parts", {}).get("simulation", 0.5), 3),
            "sim_win_b": round(t1.get("win_parts", {}).get("simulation", 0.5), 3),
            "rating_a": t0.get("win_parts", {}).get("team_rating", 1500),
            "rating_b": t1.get("win_parts", {}).get("team_rating", 1500),
            "expected_runs_a": f"{inn0.get('mean', 'N/A')} (range: {inn0.get('low', 'N/A')}–{inn0.get('high', 'N/A')})" if inn0 else "N/A",
            "expected_runs_b": f"{inn1.get('mean', 'N/A')} (range: {inn1.get('low', 'N/A')}–{inn1.get('high', 'N/A')})" if inn1 else "N/A",
            "reasons": t0.get("reasons", [])[:2],
        })
    return predictions


if __name__ == "__main__":
    print("--- 1. Cricket Multi-Model Ensemble Backtest ---")
    backtest = evaluate_backtest_summary()
    print(json.dumps(backtest, indent=2))

    print("\n--- 2. Predictions for Today's Scheduled Matches ---")
    today_preds = analyze_today_cricket_matches()
    for p in today_preds:
        print(f"[{p['tournament']}] ({p['stage'].upper()}) {p['team_a']} ({p['win_probability_a']:.1%}) vs {p['team_b']} ({p['win_probability_b']:.1%})")
        print(f"  -> Projected 1st Innings: {p['team_a']}: {p['expected_runs_a']} runs | {p['team_b']}: {p['expected_runs_b']} runs")
        if p['reasons']:
            print(f"  -> Matchup Note: {p['reasons'][0]}")
