"""Learn from the track record: correct the pre-match win chance for over- or under-confidence.

Graded forecasts give pairs of (the favourite's win chance, did the favourite win). One number
is fitted to them, a confidence factor k: the corrected chance is the model's chance with its
log-odds multiplied by k. k below 1 pulls chances toward 50% (the model was too sure of itself),
k above 1 pushes them away (it was too cautious). 50% always stays 50%, so the pick never flips.

Small samples are mostly luck, so nothing is applied until MIN_GRADED forecasts are graded for
the sport, and the fit is held toward "no change" by a prior that fades as results accumulate.
"""
import math

MIN_GRADED = 30          # graded pre-match forecasts per sport before any correction is applied
PRIOR = 2.0              # pull toward no change; larger means more results are needed to move k
LOW, HIGH = 0.5, 1.5     # the factor is never allowed outside this range
STEPS = 200


def _logit(p):
    p = min(0.999, max(0.001, float(p)))
    return math.log(p / (1 - p))


def adjust(p, factor):
    """Win chance p with its log-odds scaled by factor."""
    return 1 / (1 + math.exp(-factor * _logit(p)))


def fit(pairs):
    """pairs: (favourite's model win chance, favourite won) for graded forecasts of one sport."""
    pairs = [(_logit(max(p, 1 - p)), bool(won)) for p, won in pairs]
    n = len(pairs)
    info = {"graded": n, "needed": MIN_GRADED, "active": False, "factor": 1.0}
    if n < MIN_GRADED:
        return info

    def loss(log_k):
        k, total = math.exp(log_k), PRIOR * log_k * log_k / 2
        for x, won in pairs:
            z = k * x if won else -k * x
            total += math.log1p(math.exp(-z))
        return total
    lo, hi = math.log(LOW), math.log(HIGH)
    best = min((lo + (hi - lo) * i / STEPS for i in range(STEPS + 1)), key=loss)
    factor = round(math.exp(best), 2)
    info.update(factor=factor, active=factor != 1.0,
                favourite_expected=round(sum(1 / (1 + math.exp(-x)) for x, _ in pairs) / n, 3),
                favourite_won=round(sum(won for _, won in pairs) / n, 3))
    return info


def apply(forecast, info):
    """Attach the calibration report and, once it is active, correct the pre-match win chances.
    The model's own number is kept as "win_model" so later fits always learn from raw output."""
    if not forecast.get("supported"):
        return forecast
    forecast["calibration"] = info
    if info.get("active") and len(forecast.get("teams") or []) == 2:
        first, second = forecast["teams"]
        first["win_model"], second["win_model"] = first["win"], second["win"]
        first["win"] = round(adjust(first["win"], info["factor"]), 3)
        second["win"] = round(1 - first["win"], 3)
    return forecast
