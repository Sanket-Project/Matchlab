"""Recompute every Track Record number from the raw prediction log, independently of matchlab.tracker, and compare.

This is deliberately written from the rules, not from the tracker's code:
- a forecast counts only if its saved copy says it was saved before the start (and its grade agrees);
- a rate's n is the number of counted, graded forecasts that carry that kind of grade;
- the AI rate and the model rate are compared on the same forecasts;
- calibration bins group the favourite's shown chance into 50-60, 60-70, 70-80, 80-90 and 90-100 %.

Run: python tools/verify_track_record.py [path/to/predictions.json]
Exit code 0 when every number matches, 1 otherwise. Also lists entries worth a human look (coin-flip picks, flags
that disagree, results without a pick).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def recompute(data):
    out = {}
    for sport in ("cricket", "tennis", "f1"):
        rows = [(mid, e) for mid, e in data.items() if "pre" in e and e["pre"].get("sport", "cricket") == sport]
        counted = [(mid, e) for mid, e in rows if e["pre"].get("saved_before_start") and (not e.get("result") or e["result"].get("saved_before_start"))]
        graded = [e["result"] for _, e in counted if e.get("result")]
        winner = [r["winner_pick"]["correct"] for r in graded if "winner_pick" in r]
        ai = [r for r in graded if "ai_pick" in r and "winner_pick" in r]
        firsts = [r["first_innings"] for r in graded if "first_innings" in r]
        picks = [p for r in graded for p in r.get("picks", [])]
        bins = []
        pairs = [(max(t["win"] for t in e["pre"]["teams"]), e["result"]["winner_pick"]["correct"]) for _, e in counted
                 if e.get("result") and "winner_pick" in e["result"] and len(e["pre"]["teams"]) == 2]
        for low, high in ((0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0001)):
            inside = [(p, w) for p, w in pairs if low <= p < high]
            bins.append((len(inside), sum(1 for _, w in inside if w)))
        out[sport] = {
            "saved": len(rows), "counted": len(counted), "graded": len(graded), "waiting": len(counted) - len(graded),
            "after_start": len(rows) - len(counted),
            "winner": (sum(winner), len(winner)),
            "ai_winner": (sum(r["ai_pick"]["correct"] for r in ai), len(ai)),
            "model_on_ai_sample": (sum(r["winner_pick"]["correct"] for r in ai), len(ai)),
            "first_innings_n": len(firsts),
            "first_innings_mae": round(sum(abs(f["actual"] - f["predicted"]) for f in firsts) / len(firsts), 1) if firsts else None,
            "first_innings_in_range": sum(1 for f in firsts if f["actual"] >= f["low"] and f["actual"] <= f["high"]),
            "top_batter": (sum(p["correct"] for p in picks if p["kind"] == "top_batter"), sum(1 for p in picks if p["kind"] == "top_batter")),
            "top_bowler": (sum(p["correct"] for p in picks if p["kind"] == "top_bowler"), sum(1 for p in picks if p["kind"] == "top_bowler")),
            "set_score": (sum(r["set_score"]["correct"] for r in graded if "set_score" in r), sum(1 for r in graded if "set_score" in r)),
            "bins": bins,
        }
    return out


def from_tracker(record):
    out = {}
    for sport, group in record["sports"].items():
        s = group["summary"]
        pair = lambda key: (s[key]["correct"], s[key]["n"])  # noqa: E731
        out[sport] = {
            "saved": s["saved"], "counted": s["graded"] + s["waiting"], "graded": s["graded"], "waiting": s["waiting"], "after_start": s["after_start"],
            "winner": pair("winner"), "ai_winner": pair("ai_winner"), "model_on_ai_sample": pair("model_on_ai_sample"),
            "first_innings_n": s["first_innings"]["n"], "first_innings_mae": s["first_innings"]["mean_error"],
            "first_innings_in_range": s["first_innings"]["in_range"],
            "top_batter": pair("top_batter"), "top_bowler": pair("top_bowler"), "set_score": pair("set_score"),
            "bins": [(b["n"], b["won"]) for b in group["bins"]],
        }
    return out


def notes(data):
    found = []
    for mid, e in data.items():
        pre, result = e.get("pre"), e.get("result")
        if not pre:
            continue
        wins = [t["win"] for t in pre["teams"]]
        if len(wins) == 2 and abs(wins[0] - wins[1]) < 0.005 and result and "winner_pick" in result:
            found.append(f"{mid}: coin-flip forecast ({wins[0]:.3f} v {wins[1]:.3f}) graded as a pick ({'correct' if result['winner_pick']['correct'] else 'missed'})")
        if result and bool(pre.get("saved_before_start")) != bool(result.get("saved_before_start")):
            found.append(f"{mid}: saved copy says before start = {pre.get('saved_before_start')}, grade says {result.get('saved_before_start')}")
        if result and "winner_pick" not in result:
            found.append(f"{mid}: graded without a winner pick ({result.get('status')})")
    return found


def main():
    from matchlab import tracker
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / tracker.FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    tracker._SUMMARY.clear()
    import os
    os.environ["MATCHLAB_TRACKER_FILE"] = str(path.resolve().relative_to(ROOT)) if path.resolve().is_relative_to(ROOT) else str(path)
    mine, theirs = recompute(data), from_tracker(tracker.track_record(ROOT))
    bad = 0
    print(f"{'sport':8} {'number':22} {'recomputed':>16} {'dashboard':>16}")
    for sport in mine:
        for key, value in mine[sport].items():
            same = value == theirs[sport][key]
            bad += not same
            print(f"{sport:8} {key:22} {str(value):>16} {str(theirs[sport][key]):>16} {'' if same else '  <-- MISMATCH'}")
    print("\nFor a human look:")
    for line in notes(data) or ["nothing"]:
        print("  " + line)
    print(f"\n{'All numbers match.' if not bad else f'{bad} numbers differ.'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
