"""Point config.local.json at the best measured model per sport.

Reads artifacts/model-comparison.json (written by tools/evaluate_models.py) and
sets each sport's outcome and score model to the one with the lowest held-out
log loss / error. Player models are left unchanged. Run evaluate_models.py first.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORMATS = {"elo_only": "trained_elo", "trained_logistic": "trained_logistic", "trained_ridge": "trained_ridge"}

if __name__ == "__main__":
    comparison = json.loads((ROOT / "artifacts/model-comparison.json").read_text(encoding="utf-8"))["sports"]
    pretrained = json.loads((ROOT / "config.pretrained.example.json").read_text(encoding="utf-8"))
    path = ROOT / "config.local.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    for sport, spec in config["sports"].items():
        report = comparison.get(sport, {})
        for task, key in (("winner", "best_winner"), ("team_score", "best_team_score")):
            best = report.get(key)
            if not best:
                continue
            spec["models"][task] = {"format": FORMATS[best]} if best in FORMATS else pretrained["sports"][sport]["models"][task]
            print(f"{sport:10s} {task:10s} -> {spec['models'][task]['format']}")
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"Updated {path}")
