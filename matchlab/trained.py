"""Small models trained locally on this project's own match history.

Unlike the frozen pretrained adapters, these are fitted here:
- trained_elo: match outcome from the Elo rating gap alone (one input);
- trained_logistic: match outcome from rolling form, Elo and tennis ranking points;
- trained_ridge: each side's score from the same wider inputs. A model answering a query dated D is fitted only on matches
whose results were available strictly before D, each described by what was
known before that match started. Fits and cricket Elo parameter selections are
cached in memory.
"""
import hashlib
import json
import math
import re
from collections import OrderedDict

from .contexts import HistoryIndex, SIDE_FEATURES
from .cricket import (CRICKET_FEATURES, MIN_GROUND_MATCHES, POST_TOSS, POST_TOSS_FEATURES, PRE_MATCH,
                      CricketHistory, match_start, reverse_xis, validate_post_toss)
from .ratings import RatingIndex, RATING_FEATURES

FORMATS = {"trained_logistic": "winner", "trained_elo": "winner", "trained_ensemble": "winner", "trained_ridge": "team_score"}
POST_TOSS_MODELS = {"winner": "trained_logistic", "team_score": "trained_ridge"}
MODEL_NAMES = {"trained_logistic": "Trained logistic regression (Elo + form)", "trained_ridge": "Trained ridge regression (Elo + form)",
               "trained_elo": "Elo strength rating model"}
ENSEMBLE_WEIGHTS = {
    "football": {"trained_elo": 0.5, "trained_logistic": 0.5},
    "tennis": {"trained_elo": 0.5, "trained_logistic": 0.5},
    "badminton": {"trained_elo": 0.3, "trained_logistic": 0.7},
    "baseball": {"trained_elo": 0.7, "trained_logistic": 0.3},
    "rugby": {"trained_elo": 0.7, "trained_logistic": 0.3},
}
MODEL_NAMES["trained_ensemble"] = "Weighted Elo + logistic ensemble"
FEATURES = SIDE_FEATURES + RATING_FEATURES
ELO_ONLY = ["elo_diff"]
MIN_ROWS, MAX_MATCHES = 60, 4000
CRICKET_K = (20.0, 10.0, 40.0)
CRICKET_PULLBACK = (.5, .25, .75)
BADMINTON_FEATURES = ["tournament_tier", "round_depth"]
BADMINTON_ROUNDS = {"final": 0, "semi final": 1, "quarter final": 2, "round of 16": 3,
                    "round of 32": 4, "round of 64": 5, "qualification quarter final": 6,
                    "qualification round of 16": 7, "qualification round of 32": 8}


def inspect_trained(task, spec):
    fmt = spec.get("format")
    if FORMATS.get(fmt) != task:
        raise ValueError("trained_logistic, trained_elo and trained_ensemble serve the winner task; trained_ridge serves team_score")
    return dict(task=task, state="available", format=fmt, path=None,
                message=f"{MODEL_NAMES[fmt]}; fitted locally on results before the prediction date; nothing downloaded or saved")


def flip(venue):
    return "away" if venue == "home" else "home" if venue == "away" else "neutral"


class TrainedModels:
    def __init__(self):
        self.indexes, self.ratings, self.fitted = {}, {}, OrderedDict()
        self.cricket_indexes, self.cricket_ratings = {}, OrderedDict()

    def index(self, sport, ds):
        key = (sport, id(ds))
        if key not in self.indexes:
            self.indexes[key] = HistoryIndex(ds)
            self.ratings[key] = RatingIndex(ds)
        return self.indexes[key], self.ratings[key]

    def cricket_index(self, sport, ds):
        if sport != "cricket" or ds.synthetic:
            return None
        key = id(ds)
        if key not in self.cricket_indexes:
            self.cricket_indexes[key] = CricketHistory(ds, self.index(sport, ds)[0])
        return self.cricket_indexes[key]

    def cricket_elo(self, ds, cutoff):
        """Select Elo parameters by expanding date folds within the fit period."""
        key = (id(ds), cutoff)
        if key in self.cricket_ratings:
            self.cricket_ratings.move_to_end(key)
            return self.cricket_ratings[key]

        cricket = self.cricket_index("cricket", ds)
        training = [m for m in ds.matches if m["date"] < cutoff]
        dates = sorted({match_start(m) for m in training})
        if len(dates) < 6:
            raise ValueError("Insufficient cricket history for three Elo validation folds")
        boundaries = [dates[len(dates) * part // 6] for part in (3, 4, 5)] + [cutoff]
        folds = []
        for start, end in zip(boundaries, boundaries[1:]):
            train = [i for i, m in enumerate(training) if m["date"] < start]
            valid = [i for i, m in enumerate(training) if start <= match_start(m) < end and m["date"] < end]
            if not train or not valid:
                raise ValueError("Insufficient completed cricket results for an Elo validation fold")
            folds.append((train, valid))

        import numpy as np

        labels = np.array([m["outcome"] for m in training])
        reverse = np.array(["opponent" if y == "team" else "team" if y == "opponent" else "draw" for y in labels])
        best = (math.inf, None, None)
        for k in CRICKET_K:
            for pullback in CRICKET_PULLBACK:
                ratings = RatingIndex(ds, k=k, cricket=cricket, season_pullback=pullback, matches=training)
                gaps = np.array([ratings.features(m["team"], m["opponent"], match_start(m),
                                                  cricket.match_venues[m["match_id"]])["elo_diff"] for m in training])
                losses = []
                for train, valid in folds:
                    model = self.build("trained_elo").fit(np.r_[gaps[train], -gaps[train]].reshape(-1, 1),
                                                          np.r_[labels[train], reverse[train]])
                    probabilities = model.predict_proba(gaps[valid].reshape(-1, 1))
                    columns = {label: i for i, label in enumerate(model.classes_)}
                    losses.extend(-math.log(max(1e-10, p[columns[y]] if y in columns else 0.0))
                                  for p, y in zip(probabilities, labels[valid]))
                loss = sum(losses) / len(losses)
                if loss < best[0]:
                    best = (loss, k, pullback)

        loss, k, pullback = best
        ratings = RatingIndex(ds, k=k, cricket=cricket, season_pullback=pullback)
        selection = dict(k=k, season_pullback=pullback, folds=len(folds), validation_from=boundaries[0],
                         validation_log_loss=loss, cutoff=cutoff)
        self.cricket_ratings[key] = ratings, selection
        while len(self.cricket_ratings) > 12:
            self.cricket_ratings.popitem(last=False)
        return ratings, selection

    def features(self, sport, ds, team, opponent, cutoff, window, venue="neutral", *,
                 ground=None, season=None, ratings=None, post_toss=None, level=None, round_name=None):
        index, default_ratings = self.index(sport, ds)
        cricket = self.cricket_index(sport, ds)
        if cricket is not None:
            ground, season = cricket.fixture(team, opponent, cutoff, ground, season)
            venue = cricket.venue(team, opponent, cutoff, ground, season, venue)
        f = index.features(team, opponent, cutoff, window, venue)
        row = {k: f[k] for k in SIDE_FEATURES}
        row.update((ratings or default_ratings).features(team, opponent, cutoff, venue, season=season))
        if cricket is not None:
            row.update(cricket.features(team, opponent, cutoff, window, ground, post_toss))
        if sport == "badminton":
            tier = re.search(r"\bSuper (100|300|500|750|1000)\b", level or "")
            row.update(tournament_tier=int(tier[1]) if tier else None,
                       round_depth=BADMINTON_ROUNDS.get((round_name or "").casefold()))
        return row

    def examples(self, sport, ds, task, cutoff, window, *, ratings=None, stage=PRE_MATCH):
        """Both orientations of every match available before the cutoff."""
        cricket = None
        if stage == POST_TOSS:
            cricket = self.cricket_index(sport, ds)
            if cricket is None:
                raise ValueError("Post-toss forecasts require real cricket data")
        rows = []
        for m in [m for m in ds.matches if m["date"] < cutoff][-MAX_MATCHES:]:
            when = m.get("pre_match_date") or m["date"]
            venue = m.get("venue") or "neutral"
            announced = cricket.recorded_post_toss(m) if cricket is not None else None
            if cricket is not None and announced is None:
                continue
            pair = []
            for reverse in (False, True):
                a, b = (m["opponent"], m["team"]) if reverse else (m["team"], m["opponent"])
                inputs = reverse_xis(announced) if reverse and announced is not None else announced
                f = self.features(sport, ds, a, b, when, window, flip(venue) if reverse else venue,
                                  ground=m.get("ground"), season=m.get("season"), ratings=ratings, post_toss=inputs,
                                  level=m.get("level"), round_name=m.get("round"))
                if min(f["team_matches"], f["opponent_matches"]) < 2:
                    break
                if task == "winner":
                    label = m["outcome"]
                    if reverse and label != "draw":
                        label = "opponent" if label == "team" else "team"
                else:
                    label = m["opponent_score"] if reverse else m["team_score"]
                pair.append(dict(features=f, target=label, date=m["date"], match_id=m["match_id"]))
            if len(pair) == 2:
                rows.extend(pair)
        return rows

    @staticmethod
    def matrix(rows, names):
        import numpy as np
        return np.asarray([[np.nan if r.get(k) is None else r[k] for k in names] for r in rows], dtype=float)

    @staticmethod
    def build(kind):
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression, Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        final = Ridge(alpha=10.0) if kind == "trained_ridge" else LogisticRegression(C=1.0, max_iter=2000)
        # keep_empty_features: a column with no values at all (e.g. ranking
        # points outside tennis) stays in place as a constant instead of shifting others.
        return make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler(), final)

    def fit(self, sport, ds, kind, cutoff, window, meta, *, stage=PRE_MATCH):
        """Fit on results available before cutoff. kind: trained_logistic, trained_ridge or trained_elo."""
        if stage not in (PRE_MATCH, POST_TOSS):
            raise ValueError("Prediction stage must be pre_match or post_toss")
        if stage == POST_TOSS and (sport != "cricket" or kind not in POST_TOSS_MODELS.values()):
            raise ValueError("Post-toss forecasts require trained cricket winner or score models")
        key = (sport, id(ds), kind, cutoff, window, stage)
        if key in self.fitted:
            self.fitted.move_to_end(key)
            return self.fitted[key]
        task = "team_score" if kind == "trained_ridge" else "winner"
        cricket = self.cricket_index(sport, ds)
        ratings, selection = self.cricket_elo(ds, cutoff) if cricket is not None else (None, None)
        rows = self.examples(sport, ds, task, cutoff, window, ratings=ratings, stage=stage)
        if len(rows) < MIN_ROWS:
            history = "post-toss training history" if stage == POST_TOSS else "training history"
            raise ValueError(f"Insufficient {history}: {len(rows)} eligible rows before {cutoff}; need at least {MIN_ROWS}. Choose a later date or add real results.")
        names = ELO_ONLY if kind == "trained_elo" else FEATURES
        unavailable_features = []
        if sport == "badminton" and kind != "trained_elo":
            names = names + [name for name in BADMINTON_FEATURES if any(r["features"][name] is not None for r in rows)]
        if cricket is not None and kind != "trained_elo":
            candidates = names + CRICKET_FEATURES
            if stage == POST_TOSS:
                candidates += POST_TOSS_FEATURES
            names = [name for name in candidates if any(r["features"][name] is not None for r in rows)]
            unavailable_features = [name for name in candidates if name not in names]
        targets = [r["target"] for r in rows]
        if task == "winner":
            required = {"team", "opponent", "draw"} if meta["draw"] and "draw" in targets else {"team", "opponent"}
            if not required <= set(targets):
                raise ValueError("Training history does not contain every outcome class")
        model = self.build(kind).fit(self.matrix([r["features"] for r in rows], names), targets)
        if stage == POST_TOSS:
            identity = (stage, names, [(r["match_id"], r["target"], [r["features"][k] for k in names]) for r in rows])
        else:
            identity = [(r["match_id"], r["target"]) for r in rows]
        fitted = dict(model=model, names=names, kind=kind, rows=len(rows), matches=len(rows) // 2,
                      start=rows[0]["date"], end=rows[-1]["date"],
                      ratings=ratings, elo_selection=selection, unavailable_features=unavailable_features,
                      sha256=hashlib.sha256(json.dumps(identity).encode()).hexdigest())
        self.fitted[key] = fitted
        while len(self.fitted) > 24:
            self.fitted.popitem(last=False)
        return fitted

    def predict(self, sport, ds, task, spec, requests, meta, context_cutoff=None, *, stage=PRE_MATCH):
        kind = spec.get("format")
        inspect_trained(task, spec)
        if ds.synthetic:
            raise ValueError("Trained models are disabled for synthetic demonstration datasets")
        if kind == "trained_ensemble":
            if task != "winner":
                raise ValueError("The trained ensemble serves the winner task only")
            weights = ENSEMBLE_WEIGHTS.get(sport)
            if not weights:
                raise ValueError(f"No validated ensemble weights are configured for {sport}")
            components = {
                name: self.predict(sport, ds, task, {"format": name}, requests, meta,
                                    context_cutoff=context_cutoff, stage=stage)
                for name in weights
            }
            out = []
            for index, q in enumerate(requests):
                values = {}
                for name, weight in weights.items():
                    for label, probability in components[name][index]["value"].items():
                        values[label] = values.get(label, 0.0) + weight * probability
                total = sum(values.values())
                if not math.isfinite(total) or total <= 0:
                    raise ValueError("Trained ensemble returned invalid outcome probabilities")
                values = {label: probability / total for label, probability in values.items()}
                out.append(dict(
                    value=values,
                    raw_value=values,
                    adjustment="Probability blend; component weights are sport-specific and validated chronologically",
                    source="model",
                    model=MODEL_NAMES[kind],
                    sha256=hashlib.sha256(json.dumps({
                        "weights": weights,
                        "components": [components[name][index]["sha256"] for name in weights],
                    }, sort_keys=True).encode()).hexdigest(),
                    target="Expected match outcome probability",
                    features=components["trained_logistic"][index].get("features"),
                    provenance={
                        "method": "Weighted probability ensemble of locally fitted Elo and logistic models",
                        "weights": weights,
                        "components": {
                            name: components[name][index]["provenance"]
                            for name in weights
                        },
                        "feature_cutoff": q["cutoff"],
                    },
                ))
            return out
        cutoff, window = context_cutoff or requests[0]["cutoff"], requests[0]["window"]
        if any((q["cutoff"] != cutoff if context_cutoff is None else q["cutoff"] < cutoff) or q["window"] != window for q in requests):
            raise ValueError("Batch queries must share a window and cannot precede their training cutoff")
        announced = [validate_post_toss(q, q["team"], q["opponent"]) for q in requests] if stage == POST_TOSS else [None] * len(requests)
        fitted = self.fit(sport, ds, kind, cutoff, window, meta, stage=stage)
        inputs = [self.features(sport, ds, q["team"], q["opponent"], q["cutoff"], window, q.get("venue", "neutral"),
                                ground=q.get("ground"), season=q.get("season"), ratings=fitted["ratings"],
                                post_toss=toss, level=q.get("level"), round_name=q.get("round")) for q, toss in zip(requests, announced)]
        for f in inputs:
            if min(f["team_matches"], f["opponent_matches"]) < 2:
                raise ValueError("Insufficient history: each side needs at least 2 completed matches before the cutoff. Choose a later date or add real results.")
        model, X = fitted["model"], self.matrix(inputs, fitted["names"])
        provenance = dict(context_rows=fitted["rows"], context_matches=fitted["matches"], context_start=fitted["start"], context_end=fitted["end"],
                          context_sha256=fitted["sha256"], context_cutoff=cutoff, feature_names=fitted["names"],
                          missing_values="Median of the training rows; ratings start at 1500 for a new side",
                          method="Fitted locally on results available before the cutoff; standardised inputs", runtime="scikit-learn", device="cpu")
        if fitted["elo_selection"] is not None:
            provenance.update(stage=stage, elo_selection=fitted["elo_selection"],
                              minimum_ground_matches=MIN_GROUND_MATCHES, unavailable_features=fitted["unavailable_features"])
        if stage == POST_TOSS:
            provenance["post_toss_inputs"] = "Supplied toss and starting XIs for the selected fixture; player form uses completed pre-cutoff results"
        model_name = f"{MODEL_NAMES[kind]} (post-toss)" if stage == POST_TOSS else MODEL_NAMES[kind]

        def query_provenance(q, f):
            result = {**provenance, "feature_cutoff": q["cutoff"]}
            if fitted["elo_selection"] is not None:
                result["imputed_features"] = [name for name in fitted["names"] if f[name] is None]
            return result

        out = []
        if task == "winner":
            classes = [str(c) for c in model.classes_]
            for q, f, row in zip(requests, inputs, model.predict_proba(X)):
                value = {c: float(p) for c, p in zip(classes, row)}
                for label in ("team", "opponent"):
                    value.setdefault(label, 0.0)
                if any(not math.isfinite(v) for v in value.values()) or abs(sum(value.values()) - 1) > 1e-6:
                    raise ValueError("Trained model returned invalid outcome probabilities")
                out.append(dict(value=value, raw_value=value, adjustment="None", source="model", model=model_name, sha256=fitted["sha256"],
                                target="Expected match outcome probability", features=f, provenance=query_provenance(q, f)))
        else:
            ceiling = meta.get("max_score")
            for q, f, raw in zip(requests, inputs, model.predict(X)):
                raw = float(raw)
                if not math.isfinite(raw):
                    raise ValueError("Trained model returned a non-finite score")
                value = max(0.0, min(float(ceiling), raw) if ceiling is not None else raw)
                out.append(dict(value=value, raw_value=raw, source="model", model=model_name, sha256=fitted["sha256"],
                                adjustment="Clipped to nonnegative score" if ceiling is None else f"Clipped to [0, {ceiling}] legal target range",
                                target=f"Expected focal-side {meta['unit']} vs selected opponent", features=f,
                                provenance=query_provenance(q, f)))
        return out
