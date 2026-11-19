"""Like-for-like held-out comparison of every outcome and score model, offline.

Same protocol as evaluate_pretrained.py, on a much larger sample: the date at
80% of each sport's matches is the boundary. Every model is frozen before the
boundary (TabICL context, trained-model fitting, class frequencies), and every
model is scored on the same later matches. Later matches may use earlier
completed held-out results in their rolling features and ratings, never their
own or later results. Cricket Elo parameters are selected by expanding date
folds before the boundary. The cricket stages are compared on the same matches
with recorded toss and starting XIs, with the full pre-match report preserved.
"""
import argparse
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from matchlab.offline import enable_offline
enable_offline()
import numpy as np
from matchlab.cricket import POST_TOSS, PRE_MATCH, reverse_xis
from matchlab.engine import Engine
from matchlab.f1 import POST_QUALIFYING, STAGES, RaceEngine, forecast_cutoff
from matchlab.trained import ENSEMBLE_WEIGHTS, FEATURES, POST_TOSS_MODELS, TrainedModels

OUTCOME_MODELS = ["uniform", "class_frequency", "elo_only", "trained_logistic", "trained_ensemble", "gradient_boosting", "tabicl"]
SHIPPABLE = {"winner": ["tabicl", "trained_logistic", "elo_only", "trained_ensemble"], "team_score": ["tabicl", "trained_ridge"]}


def sample(records, n):
    if len(records) <= n:
        return records
    if n == 1:
        return [records[len(records) // 2]]
    return [records[round(i * (len(records) - 1) / (n - 1))] for i in range(n)]


def query(m, reverse=False, *, announced=None):
    venue = m.get("venue") or "neutral"
    if reverse and venue != "neutral":
        venue = "away" if venue == "home" else "home"
    fields = dict(team=m["opponent"] if reverse else m["team"], opponent=m["team"] if reverse else m["opponent"],
                  cutoff=m.get("pre_match_date") or m["date"], window=5, venue=venue, ground=m.get("ground"),
                  season=m.get("season"), level=m.get("level"), round=m.get("round"))
    if announced is not None:
        fields.update(reverse_xis(announced) if reverse else announced)
    return fields


def outcome_metrics(probabilities, truth, labels, rng, reference=None):
    losses = np.array([-math.log(max(1e-10, p.get(y, 0.0))) for p, y in zip(probabilities, truth)])
    hits = np.array([max(labels, key=lambda k: p.get(k, 0.0)) == y for p, y in zip(probabilities, truth)], dtype=float)
    brier = float(np.mean([sum((p.get(k, 0.0) - (y == k)) ** 2 for k in labels) for p, y in zip(probabilities, truth)]))
    n = len(truth)
    result = dict(n=n, correct=int(hits.sum()), accuracy=float(hits.mean()), accuracy_95_margin=1.96 * math.sqrt(max(hits.mean() * (1 - hits.mean()), 1e-12) / n),
                  log_loss=float(losses.mean()), multiclass_brier=brier)
    if reference is not None:
        result.update(paired_gap(losses, reference, rng))
    return result, losses


def paired_gap(losses, reference, rng):
    gap = losses - reference
    n = len(gap)
    means = gap[rng.integers(0, n, size=(2000, n))].mean(axis=1)
    low, high = np.percentile(means, (2.5, 97.5))
    return dict(log_loss_vs_baseline=float(gap.mean()), log_loss_vs_baseline_95=[float(low), float(high)],
                beats_baseline=bool(high < 0))


def evaluate_f1(engine, limit):
    from scipy.stats import spearmanr

    races = engine.completed
    boundary = races[int(len(races) * .8)]["date"]
    heldout = [race for race in races if race["date"] >= boundary]
    cutoff = min(race["weekend_start"] for race in heldout)
    selected = sample(heldout, limit)
    grid_counts, grid_wins, grid_podiums = Counter(), Counter(), Counter()
    for race in races:
        if race["result_available"] >= cutoff:
            break
        for row in engine.entries[race["race_id"]]:
            slot = row["grid"]
            grid_counts[slot] += 1
            grid_wins[slot] += row["finish"] == 1
            grid_podiums[slot] += row["finish"] <= 3

    report = dict(kind="race", real_races=len(races), split=boundary, training_cutoff=cutoff.isoformat(),
                  latest=races[-1]["date"], stages={})
    for stage in STAGES:
        losses, hits, briers, errors, correlations = [], [], [], [], []
        baselines = {"uniform": [], "grid" if stage == POST_QUALIFYING else "championship_standings": []}
        predictions = []
        for race in selected:
            forecast = engine.predict(race, stage, training_cutoff=cutoff)
            field = forecast["drivers"]
            actual = np.array([row["actual"]["finish"] for row in field])
            winner = int(np.argmin(actual))
            win = np.array([row["win"] for row in field])
            podium = np.array([row["podium"] for row in field])
            expected = np.array([row["expected_position"] for row in field])
            losses.append(-math.log(max(1e-10, win[winner])))
            hits.append(winner == 0)
            briers.append(float(np.mean((podium - (actual <= 3)) ** 2)))
            errors.append(float(np.abs(expected - actual).mean()))
            correlations.append(float(spearmanr(expected, actual).statistic))

            n = len(field)
            baselines["uniform"].append((math.log(n), 1 / n, float(np.mean((3 / n - (actual <= 3)) ** 2))))
            if stage == POST_QUALIFYING:
                slots = [row["grid"] for row in field]
                # One uniform-prior pseudo-observation per slot guards against zero rates.
                weights = np.array([(grid_wins[s] + 1 / n) / (grid_counts[s] + 1) for s in slots])
                podium_base = np.array([(grid_podiums[s] + 3 / n) / (grid_counts[s] + 1) for s in slots])
                key = "grid"
            else:
                ranks = engine.standings(race, forecast_cutoff(race, stage), [row["driver_id"] for row in field])
                weights = np.exp(-(np.asarray(ranks) - 1) / 4)
                podium_base = None
                key = "championship_standings"
            weights /= weights.sum()
            top = np.flatnonzero(weights == weights.max())
            baselines[key].append((-math.log(weights[winner]), float(winner in top) / len(top),
                                   float(np.mean((podium_base - (actual <= 3)) ** 2)) if podium_base is not None else None))
            predictions.append(dict(season=race["season"], round=race["round"], name=race["name"], date=race["date"],
                                    top_pick=field[0]["driver"], winner=field[winner]["driver"], correct=hits[-1],
                                    winner_probability=float(win[winner])))
        rng = np.random.default_rng(7)
        comparisons = {}
        for name, rows in baselines.items():
            ref_loss, ref_hits, ref_brier = zip(*rows)
            comparisons[name] = dict(log_loss=float(np.mean(ref_loss)), accuracy=float(np.mean(ref_hits)),
                                     podium_brier=float(np.mean(ref_brier)) if ref_brier[0] is not None else None,
                                     **paired_gap(np.array(losses), ref_loss, rng))
        report["stages"][stage] = dict(n=len(selected), correct=sum(hits), accuracy=float(np.mean(hits)),
                                       log_loss=float(np.mean(losses)), podium_brier=float(np.mean(briers)),
                                       position_mae=float(np.mean(errors)), spearman=float(np.mean(correlations)),
                                       baselines=comparisons, predictions=predictions)
    return report


def record_outcome(report, name, producer, truth, labels, rng, reference=None):
    try:
        report["winner"][name], _ = outcome_metrics(producer(), truth, labels, rng, reference)
    except Exception as exc:
        report["winner"][name] = dict(unavailable=f"{type(exc).__name__}: {exc}")


def record_scores(report, name, producer, truth, unit):
    try:
        values = np.array(producer(), dtype=float)
        report["team_score"][name] = dict(n=len(values), mae=float(np.abs(values - truth).mean()), unit=unit)
    except Exception as exc:
        report["team_score"][name] = dict(unavailable=f"{type(exc).__name__}: {exc}")


def compare_cricket_stages(trained, ds, meta, selected, pre_report, frequency):
    cricket = trained.cricket_index("cricket", ds)
    pairs = [(m, inputs) for m in selected if (inputs := cricket.recorded_post_toss(m)) is not None] if cricket else []
    split, labels = pre_report["split"], pre_report.get("classes", [])
    common = dict(split=split, latest=pre_report["latest"], classes=labels)
    pre = {key: pre_report[key] for key in ("stage", "evaluated_matches", "training_rows", "winner", "team_score", "unavailable")
           if key in pre_report}
    pre.update(common)
    coverage = dict(excluded_missing_inputs=len(selected) - len(pairs),
                    input_source="Cricsheet toss and reconstructed starting XIs for each selected match")
    if len(pairs) < 2 or not labels:
        post = dict(**common, **coverage, stage=POST_TOSS, evaluated_matches=len(pairs), winner={}, team_score={},
                    unavailable="Too few held-out matches with recorded toss and starting XIs, or no eligible training outcomes")
        return {PRE_MATCH: pre, POST_TOSS: post}

    truth = [m["outcome"] for m, _ in pairs]
    side_truth = np.array([m[k] for m, _ in pairs for k in ("team_score", "opponent_score")], dtype=float)
    reference = np.array([-math.log(max(1e-10, frequency.get(y, 0.0))) for y in truth])
    history, _ = trained.index("cricket", ds)

    def matched(stage):
        report = dict(**common, stage=stage, evaluated_matches=len(pairs), winner={}, team_score={})
        rng = np.random.default_rng(7)
        contexts = [(m, inputs if stage == POST_TOSS else None) for m, inputs in pairs]
        qs = [query(m, announced=inputs) for m, inputs in contexts]
        side_qs = [query(m, reverse, announced=inputs) for m, inputs in contexts for reverse in (False, True)]

        def predict(task, requests):
            predictions = trained.predict("cricket", ds, task, {"format": POST_TOSS_MODELS[task]}, requests,
                                          meta, context_cutoff=split, stage=stage)
            report["training_rows"] = predictions[0]["provenance"]["context_rows"]
            return [p["value"] for p in predictions]

        uniform = {label: 1 / len(labels) for label in labels}
        record_outcome(report, "uniform", lambda: [uniform] * len(truth), truth, labels, rng)
        record_outcome(report, "class_frequency", lambda: [frequency] * len(truth), truth, labels, rng)
        record_outcome(report, "trained_logistic", lambda: predict("winner", qs), truth, labels, rng, reference)
        record_scores(report, "recent_5_mean", lambda: [history.features(q["team"], q["opponent"], q["cutoff"], 5,
                                                                       q["venue"])["team_recent_avg"] for q in side_qs],
                      side_truth, meta["unit"])
        record_scores(report, "trained_ridge", lambda: predict("team_score", side_qs), side_truth, meta["unit"])
        return report

    if coverage["excluded_missing_inputs"]:
        pre = matched(PRE_MATCH)
    return {PRE_MATCH: pre, POST_TOSS: {**matched(POST_TOSS), **coverage}}


def evaluate(engine, tabicl_specs, sport, limit):
    ds, meta = engine.datasets[sport], engine.metadata[sport]
    trained = TrainedModels()
    index = engine.pretrained.index(sport, ds)
    boundary = ds.matches[int(len(ds.matches) * .8)]
    split = boundary.get("pre_match_date") or boundary["date"]
    heldout = [m for m in ds.matches if (m.get("pre_match_date") or m["date"]) >= split]
    eligible = []
    for m in heldout:
        q = query(m)
        f = index.features(q["team"], q["opponent"], q["cutoff"], 5, q["venue"])
        if min(f["team_matches"], f["opponent_matches"]) >= 2:
            eligible.append(m)
    selected = sample(eligible, limit)
    report = dict(split=split, real_matches=len(ds.matches), heldout_pool=len(heldout), eligible_pool=len(eligible),
                  evaluated_matches=len(selected), earliest=ds.matches[0]["date"], latest=ds.matches[-1]["date"], winner={}, team_score={})
    if sport == "cricket":
        report["stage"] = PRE_MATCH
    if len(selected) < 2:
        report["unavailable"] = "Too few eligible held-out matches"
        if sport == "cricket":
            report["stages"] = compare_cricket_stages(trained, ds, meta, selected, report, {})
        return report
    rng = np.random.default_rng(7)
    truth = [m["outcome"] for m in selected]
    train_rows = trained.examples(sport, ds, "winner", split, 5)
    seen = Counter(r["target"] for r in train_rows)
    labels = [k for k in ("team", "draw", "opponent") if seen.get(k)]
    qs = [query(m) for m in selected]
    uniform = [{k: 1 / len(labels) for k in labels}] * len(selected)
    frequency = {k: seen[k] / sum(seen.values()) for k in labels}
    reference = np.array([-math.log(max(1e-10, frequency.get(y, 0.0))) for y in truth])
    report["training_rows"], report["classes"] = len(train_rows), labels

    def record(name, producer):
        record_outcome(report, name, producer, truth, labels, rng, None if name in ("uniform", "class_frequency") else reference)

    record("uniform", lambda: uniform)
    record("class_frequency", lambda: [frequency] * len(selected))
    record("elo_only", lambda: [p["value"] for p in trained.predict(sport, ds, "winner", {"format": "trained_elo"}, qs, meta, context_cutoff=split)])
    record("trained_logistic", lambda: [p["value"] for p in trained.predict(sport, ds, "winner", {"format": "trained_logistic"}, qs, meta, context_cutoff=split)])
    if sport in ENSEMBLE_WEIGHTS:
        record("trained_ensemble", lambda: [p["value"] for p in trained.predict(
            sport, ds, "winner", {"format": "trained_ensemble"}, qs, meta, context_cutoff=split)])
    if sport == "cricket" and "log_loss" in report["winner"]["elo_only"]:
        report["elo_selection"] = trained.cricket_elo(ds, split)[1]

    def boosted():
        from sklearn.ensemble import HistGradientBoostingClassifier
        model = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, random_state=0)
        names, rows, ratings, median = FEATURES, train_rows, None, None
        if sport == "cricket":
            fitted = trained.fit(sport, ds, "trained_logistic", split, 5, meta)
            names, ratings = fitted["names"], fitted["ratings"]
            rows = trained.examples(sport, ds, "winner", split, 5, ratings=ratings)
            median = fitted["model"].named_steps["simpleimputer"]
        if sport == "badminton":
            names = trained.fit(sport, ds, "trained_logistic", split, 5, meta)["names"]
        train = trained.matrix([r["features"] for r in rows], names)
        X = trained.matrix([trained.features(sport, ds, q["team"], q["opponent"], q["cutoff"], 5, q["venue"],
                                             ground=q["ground"], season=q["season"], ratings=ratings,
                                             level=q["level"], round_name=q["round"]) for q in qs], names)
        if median is not None:
            train, X = median.transform(train), median.transform(X)
        else:
            used = ~np.isnan(train).all(axis=0)  # ranking points exist for tennis only
            train, X = train[:, used], X[:, used]
        model.fit(train, [r["target"] for r in rows])
        return [dict(zip(map(str, model.classes_), map(float, row))) for row in model.predict_proba(X)]
    record("gradient_boosting", boosted)
    record("tabicl", lambda: [p["value"] for p in engine.pretrained.predict(sport, ds, "winner", tabicl_specs["winner"], qs, meta, context_cutoff=split)])

    side_qs = [query(m, reverse) for m in selected for reverse in (False, True)]
    side_truth = np.array([m[k] for m in selected for k in ("team_score", "opponent_score")], dtype=float)

    def score(name, producer):
        record_scores(report, name, producer, side_truth, meta["unit"])
    score("recent_5_mean", lambda: [index.features(q["team"], q["opponent"], q["cutoff"], 5, q["venue"])["team_recent_avg"] for q in side_qs])
    score("trained_ridge", lambda: [p["value"] for p in trained.predict(sport, ds, "team_score", {"format": "trained_ridge"}, side_qs, meta, context_cutoff=split)])
    score("tabicl", lambda: [p["value"] for p in engine.pretrained.predict(sport, ds, "team_score", tabicl_specs["team_score"], side_qs, meta, context_cutoff=split)])

    for task, metric in (("winner", "log_loss"), ("team_score", "mae")):
        available = {k: report[task][k][metric] for k in SHIPPABLE[task] if metric in report[task].get(k, {})}
        report[f"best_{task}"] = min(available, key=available.get) if available else None
    if sport == "cricket":
        report["stages"] = compare_cricket_stages(trained, ds, meta, selected, report, frequency)
    return report


def print_metrics(report):
    if "unavailable" in report:
        print(f"  unavailable: {report['unavailable']}")
    for name in OUTCOME_MODELS:
        r = report["winner"].get(name, {})
        if "log_loss" in r:
            verdict = "" if "beats_baseline" not in r else "  beats no-skill baseline" if r["beats_baseline"] else "  no better than no-skill baseline"
            print(f"  {name:18s} acc {100*r['accuracy']:5.1f}% ±{100*r['accuracy_95_margin']:4.1f}  log loss {r['log_loss']:.3f}{verdict}")
        elif r:
            print(f"  {name:18s} unavailable: {r['unavailable'][:90]}")
    for name, r in report["team_score"].items():
        print(f"  score {name:14s} " + (f"MAE {r['mae']:.3f} {r['unit']}" if "mae" in r else f"unavailable: {r['unavailable'][:80]}"))


def project_accuracy(sports):
    """Count one top pick per held-out event at its latest forecast stage."""
    try:
        badminton = sports["badminton"]
        picks = {
            "ipl_post_toss": sports["cricket"]["stages"][POST_TOSS]["winner"]["trained_logistic"],
            "badminton": badminton["winner"][badminton["best_winner"]],
            "f1_post_qualifying": sports["f1"]["stages"][POST_QUALIFYING],
        }
        events = sum(report["n"] for report in picks.values())
        correct = sum(report.get("correct", round(report["n"] * report["accuracy"])) for report in picks.values())
    except KeyError:
        return None
    return dict(events=events, correct=correct, accuracy=correct / events,
                stages={key: {k: record[k] for k in ("n", "accuracy")} for key, record in picks.items()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matches", type=int, default=400, help="Maximum held-out matches per sport, evenly spaced")
    parser.add_argument("--sports", nargs="*")
    args = parser.parse_args()
    if args.matches < 2:
        parser.error("--matches must be at least 2")
    # TabICL specifications come from the portable pretrained example so this
    # comparison does not depend on which model the dashboard currently uses.
    reference = json.loads((ROOT / "config.pretrained.example.json").read_text(encoding="utf-8"))
    engine = Engine(reference, ROOT)
    output = ROOT / "artifacts/model-comparison.json"
    result = dict(method=__doc__, max_matches_per_sport=args.matches, sports={})
    if args.sports and output.exists():
        result["sports"] = json.loads(output.read_text(encoding="utf-8")).get("sports", {})
    for sport in engine.datasets:
        if args.sports and sport not in args.sports:
            continue
        start = time.monotonic()
        report = evaluate(engine, reference["sports"][sport]["models"], sport, args.matches)
        report["seconds"] = round(time.monotonic() - start, 1)
        result["sports"][sport] = report
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\n{sport}: {report['evaluated_matches']} held-out matches from {report['split']} ({report['seconds']}s)")
        print_metrics(report)
        print(f"  best outcome model: {report.get('best_winner')}; best score model: {report.get('best_team_score')}")
        if sport == "cricket":
            pre, post = (report["stages"][stage] for stage in (PRE_MATCH, POST_TOSS))
            if pre["evaluated_matches"] != report["evaluated_matches"]:
                print(f"\ncricket paired pre-match: {pre['evaluated_matches']} held-out matches")
                print_metrics(pre)
            print(f"\ncricket post-toss: {post['evaluated_matches']} held-out matches from {post['split']}; "
                  f"{post['excluded_missing_inputs']} excluded for missing toss or XI")
            print_metrics(post)
    f1_folder = ROOT / "data/real/f1"
    if (not args.sports or "f1" in args.sports) and (f1_folder / "provenance.json").is_file():
        start = time.monotonic()
        report = evaluate_f1(RaceEngine(f1_folder), args.matches)
        report["seconds"] = round(time.monotonic() - start, 1)
        result["sports"]["f1"] = report
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        for stage, record in report["stages"].items():
            print(f"\nf1 {stage}: {record['correct']}/{record['n']} correct ({record['accuracy']:.1%}), "
                  f"log loss {record['log_loss']:.3f}, podium Brier {record['podium_brier']:.3f}, "
                  f"position MAE {record['position_mae']:.2f}, Spearman {record['spearman']:.3f}")
    if summary := project_accuracy(result["sports"]):
        result["project_winner_accuracy"] = summary
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\nProject winner accuracy: {summary['correct']}/{summary['events']} ({summary['accuracy']:.1%})")
