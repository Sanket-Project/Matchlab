"""Format-specific pre-match estimates with chronological archive backtests."""
from collections import Counter
from math import log
from statistics import mean


def _fit(history, teams, outcomes, minimum):
    sides = [[row for row in history if team in row["teams"]][-12:] for team in teams]
    if min(map(len, sides)) < minimum:
        return None

    # Treat the two team labels symmetrically when the batting order is unknown.
    decisive = sum(row["winner"] is not None for row in history)
    counts = [decisive / 2 + 1, decisive / 2 + 1]
    if len(outcomes) == 3:
        counts.append(len(history) - decisive + 1)
    baseline = [count / sum(counts) for count in counts]
    comparable = {row["id"]: row for matches in sides for row in matches}
    results = Counter()
    for row in comparable.values():
        winner = row["winner"]
        if winner is None:
            results["draw"] += 1
        elif winner in teams:
            results[winner] += 1
        else:
            known_side = next(team for team in row["teams"] if team in teams)
            results[next(team for team in teams if team != known_side)] += 1
    keys = [*teams, "draw"] if len(outcomes) == 3 else list(teams)
    probabilities = [(results[key] + 12 * prior) / (len(comparable) + 12)
                     for key, prior in zip(keys, baseline)]

    scores = [runs for row in history for runs in row["scores"].values()]
    center = mean(scores) if scores else None
    estimates = []
    for i, team in enumerate(teams):
        made = [row["scores"][team] for row in sides[i] if team in row["scores"]]
        rival = teams[1 - i]
        conceded = [runs for row in sides[1 - i] for side, runs in row["scores"].items() if side != rival]
        if center is None or min(len(made), len(conceded)) < minimum:
            estimates.append(None)
        else:
            estimates.append(center + (sum(run - center for run in made + conceded)
                                       / (len(made) + len(conceded) + 8)))
    return {"probabilities": probabilities, "baseline": baseline, "scores": estimates,
            "baseline_score": center, "sample": [len(matches) for matches in sides]}


def _backtest(history, outcomes, minimum):
    if len(history) < 60:
        return {}
    split = history[len(history) * 4 // 5]["start"]
    losses, baseline_losses, errors, baseline_errors = [], [], [], []
    for row in history:
        if row["start"] < split:
            continue
        earlier = [previous for previous in history if previous["end"] < row["start"]]
        fit = _fit(earlier, row["teams"], outcomes, minimum)
        if not fit:
            continue
        winner = row["winner"]
        index = row["teams"].index(winner) if winner is not None else 2
        losses.append(-log(fit["probabilities"][index]))
        baseline_losses.append(-log(fit["baseline"][index]))
        for team, estimate in zip(row["teams"], fit["scores"]):
            if estimate is not None and team in row["scores"]:
                actual = row["scores"][team]
                errors.append(abs(actual - estimate))
                baseline_errors.append(abs(actual - fit["baseline_score"]))
    return {
        "matches": len(losses), "score_count": len(errors), "start": split,
        "log_loss": round(mean(losses), 4) if losses else None,
        "baseline_log_loss": round(mean(baseline_losses), 4) if losses else None,
        "run_mae": round(mean(errors), 1) if errors else None,
        "baseline_run_mae": round(mean(baseline_errors), 1) if errors else None,
    }


def forecast(rows, fixture, teams, cutoff, format_name):
    test = format_name == "Test"
    outcomes = ("win", "loss", "draw") if test else ("win", "loss")
    minimum = 4 if test else 3
    history = []
    for row in rows:
        if row["result"] != "win" and not (test and row["result"] == "draw"):
            continue
        if row["result"] == "win" and row["winner"] not in row["teams"]:
            continue
        history.append({**row, "winner": row["winner"] if row["result"] == "win" else None})
    history.sort(key=lambda row: row["start"])
    validation = _backtest(history, outcomes, minimum)
    fit = _fit(history, teams, outcomes, minimum) if len(history) >= 60 else None
    if not fit or validation.get("matches", 0) < 20:
        return {"reason": "Too few completed, comparable matches to estimate this fixture and backtest the method.",
                "validation": validation}

    return {
        "as_of": cutoff,
        "score_label": "First innings runs" if test else "Innings runs",
        "outcome_label": "Win or draw" if test else "Win, given a decisive result",
        "probabilities": [{"outcome": label, "probability": round(value, 4)}
                          for label, value in zip([fixture["team"], fixture["opponent"], "Draw"], fit["probabilities"])],
        "scores": [{"team": label, "runs": round(value)} for label, value in
                   zip([fixture["team"], fixture["opponent"]], fit["scores"]) if value is not None],
        "sample": fit["sample"], "validation": validation,
    }
