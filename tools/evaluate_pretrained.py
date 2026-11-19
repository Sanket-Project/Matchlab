"""Chronological held-out evaluation using original downloaded weights, offline.

Freeze all TabICL labeled context before an 80% date boundary. Later test
queries may see previously completed test results as rolling features, never
their own/later results. No validation labels enter TabICL fit().
"""
import argparse
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path
from statistics import mean
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from matchlab.offline import enable_offline
enable_offline()
from matchlab.engine import Engine
from matchlab.pretrained import file_hash


def sample(records, n):
    if len(records) <= n:
        return records
    return [records[round(i * (len(records) - 1) / (n - 1))] for i in range(n)]


def mae(pred, true):
    return mean(abs(a - b) for a, b in zip(pred, true))


def query(m, reverse=False, **extra):
    venue = m.get("venue") or "neutral"
    if reverse and venue != "neutral":
        venue = "away" if venue == "home" else "home"
    return dict(team=m["opponent"] if reverse else m["team"], opponent=m["team"] if reverse else m["opponent"],
                cutoff=m.get("pre_match_date") or m["date"], window=5, venue=venue, **extra)


def evaluate(engine, sport, count):
    ds, meta = engine.datasets[sport], engine.metadata[sport]
    index = engine.pretrained.index(sport, ds)
    split = ds.matches[int(len(ds.matches) * .8)].get("pre_match_date") or ds.matches[int(len(ds.matches) * .8)]["date"]
    report = dict(split=split, real_matches=len(ds.matches), data_sha256=ds.file_hashes, context_limit=192, tasks={}, records={})
    heldout = [m for m in ds.matches if (m.get("pre_match_date") or m["date"]) >= split]
    eligible = []
    for m in heldout:
        q = query(m)
        f = index.features(q["team"], q["opponent"], q["cutoff"], 5, q["venue"])
        if min(f["team_matches"], f["opponent_matches"]) >= 2:
            eligible.append(m)
    selected = sample(eligible, count)
    report.update(heldout_pool=len(heldout), eligible_match_pool=len(eligible), selected_matches=len(selected))
    def predict(task, qs):
        if not qs:
            raise ValueError("No eligible held-out examples")
        return engine.pretrained.predict(sport, ds, task, engine.registries[sport].configs[task], qs, meta, context_cutoff=split)
    qs = [query(m) for m in selected]
    try:
        outputs = predict("winner", qs)
        labels = ["team", "draw", "opponent"] if meta["draw"] else ["team", "opponent"]
        truth = [m["outcome"] for m in selected]
        accuracy = mean(max(p["value"], key=p["value"].get) == y for p, y in zip(outputs, truth))
        loss = mean(-math.log(max(1e-10, p["value"].get(y, 0))) for p, y in zip(outputs, truth))
        brier = mean(sum((p["value"].get(k, 0) - int(y == k))**2 for k in labels) for p, y in zip(outputs, truth))
        context = index.examples("winner", split, 5, 192)
        context_counts = Counter(r["target"] for r in context)
        majority = context_counts.most_common(1)[0][0]
        report["tasks"]["winner"] = dict(n=len(outputs), accuracy=accuracy, log_loss=loss, multiclass_brier=brier,
                                           uniform_log_loss=math.log(len(labels)), context_majority_accuracy=mean(y == majority for y in truth),
                                           context_rows=outputs[0]["provenance"]["context_rows"])
        report["records"]["winner"] = [dict(match_id=m["match_id"], cutoff=q["cutoff"], actual=y, predicted=p["value"], context_end=p["provenance"]["context_end"]) for m, q, y, p in zip(selected, qs, truth, outputs)]
    except Exception as exc:
        report["tasks"]["winner"] = dict(unavailable=str(exc))
    side_qs = [query(m, reverse) for m in selected for reverse in (False, True)]
    side_truth = [m[k] for m in selected for k in ("team_score", "opponent_score")]
    try:
        outputs = predict("team_score", side_qs)
        baselines = [p["features"]["team_recent_avg"] for p in outputs]
        report["tasks"]["team_score"] = dict(n=len(outputs), mae=mae([p["value"] for p in outputs], side_truth), recent_mean_mae=mae(baselines, side_truth), unit=meta["unit"])
        report["records"]["team_score"] = [dict(query=q, actual=y, predicted=p["value"], context_end=p["provenance"]["context_end"]) for q, y, p in zip(side_qs, side_truth, outputs)]
    except Exception as exc:
        report["tasks"]["team_score"] = dict(unavailable=str(exc))
    for task, candidates in (("player_score", ds.players), ("player_threat", index.grouped_interactions)):
        records = []
        for p in candidates:
            m = ds.by_id[p["match_id"]]
            when = m.get("pre_match_date") or m["date"]
            if when < split:
                continue
            q = query(m, p["team"] != m["team"], player=p["player"], opponent_player=p.get("opponent_player"))
            f = index.features(q["team"], q["opponent"], when, 5, q["venue"], q["player"], q.get("opponent_player"))
            if min(f["team_matches"], f["opponent_matches"], f["player_appearances"]) < 2:
                continue
            if task == "player_threat" and (f["player_action_rate"] is None or f["opponent_action_conceded_rate"] is None):
                continue
            target = p["score"] if task == "player_score" else p["successes"] / p["opportunities"]
            records.append(dict(query=q, target=target, match_id=p["match_id"]))
        selected_players = sample(records, count)
        try:
            outputs = predict(task, [p["query"] for p in selected_players])
            actual = [p["target"] for p in selected_players]
            baseline = [p["features"]["player_recent_avg" if task == "player_score" else "player_action_rate"] for p in outputs]
            report["tasks"][task] = dict(n=len(outputs), mae=mae([p["value"] for p in outputs], actual), historical_baseline_mae=mae(baseline, actual), unit=meta["player_unit"] if task == "player_score" else "pair-match success fraction")
            report["records"][task] = [dict(**r, predicted=p["value"], context_end=p["provenance"]["context_end"]) for r, p in zip(selected_players, outputs)]
        except Exception as exc:
            report["tasks"][task] = dict(unavailable=str(exc))
        if task == "player_score":
            form_records = selected_players
    for name, records in (("chronos_team_form", [dict(query=q, target=y) for q, y in zip(side_qs, side_truth)]), ("chronos_player_form", form_records)):
        try:
            outputs = engine.pretrained.forecast(ds, [r["query"] for r in records], meta)
            valid = [(r, p) for r, p in zip(records, outputs) if p["value"] is not None]
            if not valid:
                raise ValueError("No selected series has 8 chronological pre-match observations")
            actual = [r["target"] for r, p in valid]
            predicted = [p["value"] for r, p in valid]
            report["tasks"][name] = dict(n=len(valid), mae=mae(predicted, actual), quantile_10_90_coverage=mean(p["q10"] <= r["target"] <= p["q90"] for r, p in valid), unit=meta["player_unit"] if "player" in name else meta["unit"])
            report["records"][name] = [dict(**r, predicted=p["value"], q10=p["q10"], q90=p["q90"], history_end=p["provenance"]["history_end"]) for r, p in valid]
        except Exception as exc:
            report["tasks"][name] = dict(unavailable=str(exc))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matches", type=int, default=32)
    parser.add_argument("--sports", nargs="*")
    args = parser.parse_args()
    engine = Engine(json.loads((ROOT / "config.pretrained.example.json").read_text()), ROOT)
    manifest = json.loads((ROOT / "models/manifest.json").read_text())
    before = {f["path"]: file_hash(ROOT / f["path"]) for f in manifest["files"]}
    result = dict(method=__doc__, offline=True, sample_size_per_sport=args.matches, sports={}, limitations=["Small deterministic samples, not a full-season accuracy estimate. No tuning or calibration on these samples.", "Upstream pretrained corpus overlap cannot be audited here; application-level contexts/features are chronological.", "Rolling features may use earlier completed held-out results; all labeled TabICL context stays frozen before split."])
    result["model_sha256"] = before
    if args.sports and (ROOT / "artifacts/evaluation.json").exists():
        previous = json.loads((ROOT / "artifacts/evaluation.json").read_text())
        result["sports"] = previous["sports"]
    for sport in engine.datasets:
        if args.sports and sport not in args.sports:
            continue
        print("Evaluating " + sport, flush=True)
        start = time.monotonic()
        result["sports"][sport] = evaluate(engine, sport, args.matches)
        result["sports"][sport]["seconds"] = round(time.monotonic() - start, 2)
        (ROOT / "artifacts/evaluation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result["sports"][sport]["tasks"]), flush=True)
    after = {f["path"]: file_hash(ROOT / f["path"]) for f in manifest["files"]}
    assert before == after
    result["original_weights_unchanged"] = True
    (ROOT / "artifacts/evaluation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
