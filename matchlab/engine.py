import copy
from collections import Counter
from datetime import date
from statistics import mean
from .data import Dataset, local_path
from .models import ModelRegistry
from .sports import SPORTS
from .contexts import FEATURE_DESCRIPTIONS
from .cricket import POST_TOSS, PRE_MATCH, reverse_xis, validate_post_toss
from .f1 import PRE_WEEKEND, POST_QUALIFYING, RaceEngine
from .pretrained import PretrainedModels
from .splits import build as build_breakdowns
from .ratings import RATING_DESCRIPTIONS
from .trained import TrainedModels, FORMATS as TRAINED_FORMATS, POST_TOSS_MODELS

TABICL_FORMATS = ("tabicl_classifier", "tabicl_regressor")
# Name of each outcome-model format in artifacts/model-comparison.json.
COMPARISON_NAMES = {"tabicl_classifier": "tabicl", "trained_logistic": "trained_logistic", "trained_elo": "elo_only", "trained_ensemble": "trained_ensemble"}

FEATURES = {
    "team_recent_avg": "Mean scored by the focal side in the form window",
    "team_recent_conceded": "Mean conceded by the focal side",
    "team_recent_win_rate": "Focal side wins / matches (draws excluded from wins)",
    "team_recent_draw_rate": "Focal side draws / matches",
    "team_matches": "Focal side matches in the form window",
    "opponent_recent_avg": "Opposing side mean score",
    "opponent_recent_conceded": "Opposing side mean conceded",
    "opponent_recent_win_rate": "Opposing side wins / matches",
    "opponent_recent_draw_rate": "Opposing side draws / matches",
    "opponent_matches": "Opposing side matches in the form window",
    "h2h_avg": "Focal side mean against the selected opponent, last N meetings",
    "h2h_win_rate": "Focal side wins / last N meetings",
    "h2h_matches": "Meetings in the last N head-to-head window",
    "is_home": "1 for focal side at home, 0 otherwise (neutral and away)",
    "is_neutral": "1 at neutral venue, 0 otherwise",
    "player_recent_avg": "Selected player's mean in last N appearances for focal side",
    "player_opponent_avg": "Selected player's mean in last N appearances vs opposing side",
    "player_appearances": "Selected player's appearances in the form window",
    "opponent_player_recent_avg": "Opposing player's mean in last N appearances for opposing side",
    "interaction_rate": "Selected player's successes / opportunities vs selected opposing player",
    "interaction_opportunities": "Opportunities in last N distinct meetings of this player pair",
    "interaction_successes": "Successes in last N distinct meetings of this player pair",
    "interaction_avg_score": "Total player-pair score / meetings in interaction window",
}
FEATURES.update(FEATURE_DESCRIPTIONS)
FEATURES.update(RATING_DESCRIPTIONS)


def default_config():
    return {"sports": {key: {"data_dir": f"data/demo/{key}", "demo": True,
                              "reference_mode": True, "models": {}} for key, sport in SPORTS.items() if sport["kind"] == "match"}}


def summary(rows):
    n = len(rows)
    return {"matches": n, "avg": mean(r["score"] for r in rows) if n else None,
            "conceded": mean(r["conceded"] for r in rows) if n else None,
            "wins": sum(r["result"] == "W" for r in rows),
            "draws": sum(r["result"] == "D" for r in rows),
            "losses": sum(r["result"] == "L" for r in rows),
            "win_rate": sum(r["result"] == "W" for r in rows) / n if n else None,
            "draw_rate": sum(r["result"] == "D" for r in rows) / n if n else None}


class Engine:
    def __init__(self, config, root):
        if not isinstance(config, dict) or not isinstance(config.get("sports"), dict) or not config["sports"]:
            raise ValueError("Configuration requires a nonempty sports object")
        if not set(config["sports"]).issubset(SPORTS):
            raise ValueError("Supported sports: " + ", ".join(SPORTS))
        self.root, self.config = root, copy.deepcopy(config)
        self.datasets, self.registries = {}, {}
        self.race_engine = None
        self.metadata = {}
        self.pretrained = PretrainedModels(self.config.get("pretrained", {}), root)
        self.trained = TrainedModels()
        # Measured held-out results (tools/evaluate_models.py), shown beside predictions.
        self.comparison = {}
        try:
            import json
            self.comparison = json.loads((root / "artifacts/model-comparison.json").read_text(encoding="utf-8")).get("sports", {})
        except (OSError, ValueError, AttributeError):
            pass
        for key, spec in self.config["sports"].items():
            if not isinstance(spec, dict):
                raise ValueError("Each sport configuration must be an object")
            for flag in ("demo", "reference_mode"):
                if flag in spec and not isinstance(spec[flag], bool):
                    raise ValueError(f"{flag} must be true or false")
            if SPORTS[key]["kind"] == "race":
                if spec.get("demo") or spec.get("reference_mode"):
                    raise ValueError("Formula 1 requires a real race dataset")
                self.race_engine = RaceEngine(local_path(spec.get("data_dir"), root))
                continue
            scoring = spec.get("scoring", {})
            if not isinstance(scoring, dict) or set(scoring) - {"draw", "max_score", "strict_scores", "format"}:
                raise ValueError("scoring accepts draw, max_score, strict_scores and format")
            if "draw" in scoring and not isinstance(scoring["draw"], bool):
                raise ValueError("scoring.draw must be a boolean")
            if key in ("tennis", "badminton", "baseball") and scoring.get("draw", False):
                raise ValueError(f"{key} cannot use draw outcomes")
            self.metadata[key] = {**SPORTS[key], **scoring}
            # Cricket accepts recorded draws and derives the outcome space from history.
            validation = {**self.metadata[key], "draw": True} if key == "cricket" else self.metadata[key]
            ds = self.datasets[key] = Dataset(local_path(spec.get("data_dir"), root), validation)
            if key == "cricket":
                self.metadata[key]["draw"] = any(m["outcome"] == "draw" for m in ds.matches)
            known_demo = ds.folder.is_relative_to((root / "data/demo").resolve())
            ds.synthetic = bool(spec.get("demo", False) or known_demo or ds.provenance.get("synthetic", False))
            self.config["sports"][key]["demo"] = ds.synthetic
            self.registries[key] = ModelRegistry(spec.get("models", {}), root)

    def catalog(self):
        result = []
        for key, ds in self.datasets.items():
            counts = Counter(t for m in ds.matches for t in (m["team"], m["opponent"]))
            cricket = self.trained.cricket_index(key, ds)
            result.append({"id": key, **self.metadata[key], "teams": ds.teams,
                           "recommended_teams": [t for t, _ in counts.most_common(2)],
                           "players": {k: sorted(v) for k, v in ds.rosters.items()},
                           "rows": len(ds.matches), "player_rows": len(ds.players),
                           "interaction_rows": len(ds.interactions), "latest": ds.matches[-1]["date"],
                           "earliest": ds.matches[0]["date"],
                           "available_matches": [{"match_id": m["match_id"], "date": m["date"],
                                                  "team": m["team"], "opponent": m["opponent"],
                                                  "venue": cricket.match_venues[m["match_id"]] if cricket else m.get("venue", "neutral")}
                                                 for m in ds.matches],
                           "demo": self.config["sports"][key].get("demo", False),
                           "reference_mode": self.config["sports"][key].get("reference_mode", False),
                           "data_provenance": ds.provenance, "data_sha256": ds.file_hashes,
                           "models": [self.registries[key].inspect(t) for t in ("winner", "team_score", "player_score", "player_threat")] + ([self.pretrained.chronos_status()] if self.config.get("pretrained") else [])})
        if self.race_engine is not None:
            result.append(self.race_engine.catalog())
        return result

    def race(self, query):
        if self.race_engine is None:
            raise ValueError("Formula 1 is unavailable in this data workspace")
        try:
            if isinstance(query["season"], bool) or isinstance(query["round"], bool):
                raise ValueError()
            return self.race_engine.by_round[int(str(query["season"])), int(str(query["round"]))]
        except (KeyError, TypeError, ValueError):
            raise ValueError("Select a Grand Prix by season and round") from None

    def forecast_race(self, query, published=None):
        race = self.race(query)
        stage = query.get("stage", PRE_WEEKEND)
        grid, source, field = query.get("grid"), None, None
        if stage == POST_QUALIFYING and published and not race["completed"]:
            field = published["field"]
            if grid is None or grid == published["grid"]:
                grid, source = published["grid"], published["source"]
        result = self.race_engine.predict(race, stage, grid, grid_source=source, published_field=field)
        report = self.comparison.get("f1", {})
        validation = report.get("stages", {}).get(stage)
        if validation:
            result["track_record"] = {k: validation[k] for k in ("n", "correct", "accuracy", "log_loss", "baselines")}
        return result

    def cricket_xis(self, query):
        ds = self.datasets.get("cricket")
        if ds is None or ds.synthetic:
            raise ValueError("Starting XIs require real cricket data")
        team, opponent = query.get("team"), query.get("opponent")
        if team == opponent or team not in ds.teams or opponent not in ds.teams:
            raise ValueError("Choose two different cricket teams")
        cutoff = date.fromisoformat(str(query.get("cutoff"))).isoformat()
        cricket = self.trained.cricket_index("cricket", ds)
        return {"team_xi": cricket.last_xi(team, cutoff), "opponent_xi": cricket.last_xi(opponent, cutoff)}

    def _run_pretrained(self, sport, task, requests, *, stage=PRE_MATCH):
        try:
            if stage == POST_TOSS:
                return self.trained.predict(sport, self.datasets[sport], task, {"format": POST_TOSS_MODELS[task]},
                                            requests, self.metadata[sport], stage=POST_TOSS)
            spec = self.registries[sport].configs[task]
            runner = self.trained if spec.get("format") in TRAINED_FORMATS else self.pretrained
            return runner.predict(sport, self.datasets[sport], task, spec, requests, self.metadata[sport])
        except Exception as exc:
            return [{"value": None, "source": "unavailable", "error": f"{type(exc).__name__}: {exc}"} for _ in requests]

    def _prediction(self, sport, task, features, reference, request=None):
        registry = self.registries[sport]
        if task in registry.configs:
            try:
                if registry.configs[task].get("format") in TABICL_FORMATS or registry.configs[task].get("format") in TRAINED_FORMATS:
                    return self._run_pretrained(sport, task, [request])[0]
                unknown = set(registry.configs[task].get("features", [])) - set(FEATURES)
                if unknown:
                    raise ValueError("Unknown features: " + ", ".join(sorted(unknown)))
                return registry.predict(task, features)
            except Exception as exc:
                return {"value": None, "source": "unavailable", "error": f"{type(exc).__name__}: {exc}"}
        if self.config["sports"][sport].get("reference_mode", False) and reference is not None:
            return {"value": reference, "source": "reference", "model": "Historical arithmetic; no trained model"}
        return {"value": None, "source": "unavailable", "error": "No model configured for this prediction"}

    def analyze(self, query):
        sport = query.get("sport", next(iter(self.datasets), None))
        if sport not in self.datasets:
            raise ValueError("Select a configured sport")
        ds, meta = self.datasets[sport], self.metadata[sport]
        team, opponent = query.get("team"), query.get("opponent")
        if team not in ds.teams or opponent not in ds.teams or team == opponent:
            raise ValueError("Choose two different sides from this sport")
        stage = query.get("stage", PRE_MATCH)
        if stage not in (PRE_MATCH, POST_TOSS):
            raise ValueError("Prediction stage must be pre_match or post_toss")
        announced = None
        if stage == POST_TOSS:
            if sport != "cricket" or ds.synthetic:
                raise ValueError("Post-toss forecasts require real cricket data")
            announced = validate_post_toss(query, team, opponent)
        try:
            window = int(query.get("window", 5))
            cutoff = date.fromisoformat(str(query.get("cutoff", date.today().isoformat()))).isoformat()
        except (TypeError, ValueError):
            raise ValueError("Use a valid prediction date and a whole-number form window") from None
        if not 1 <= window <= 30:
            raise ValueError("Form window must be between 1 and 30 matches")
        venue = query.get("venue", "neutral")
        if venue not in ("home", "away", "neutral"):
            raise ValueError("Venue must be home, away, or neutral")
        supplied_venue = venue
        ground, season = None, None
        if sport == "cricket":
            meta = {**meta, "draw": any(m["outcome"] == "draw" and m["date"] < cutoff for m in ds.matches)}
            cricket = self.trained.cricket_index(sport, ds)
            if cricket is not None:
                ground, season = query.get("ground"), query.get("season")
                if any(v is not None and (not isinstance(v, str) or not v.strip()) for v in (ground, season)):
                    raise ValueError("Cricket ground and season must be nonempty strings when supplied")
                ground, season = cricket.fixture(team, opponent, cutoff, ground, season)
                venue = cricket.venue(team, opponent, cutoff, ground, season, supplied_venue)
        histories = [ds.history(t, cutoff)[-window:] for t in (team, opponent)]
        if any(not h for h in histories):
            raise ValueError("Both sides need completed matches before the prediction date")
        summaries = [summary(h) for h in histories]
        h2h = ds.history(team, cutoff, opponent)[-window:]
        pair = summary(h2h)
        players = {}
        for side in (team, opponent):
            players[side] = sorted({p["player"] for p in ds.players if p["team"] == side and p["date"] < cutoff})
        def default_player(side):
            counts = Counter(p["player"] for p in ds.players if p["team"] == side and p["date"] < cutoff)
            return counts.most_common(1)[0][0] if counts else None
        player = query.get("player") or default_player(team)
        other_player = query.get("opponent_player") or default_player(opponent)
        if player and player not in players[team]:
            raise ValueError("Selected player has no appearances for this side before the prediction date")
        if other_player and other_player not in players[opponent]:
            raise ValueError("Opposing player has no appearances for this side before the prediction date")
        request = dict(sport=sport, team=team, opponent=opponent, cutoff=cutoff, window=window, venue=supplied_venue,
                       player=player, opponent_player=other_player, ground=ground, season=season)
        if sport == "badminton":
            fixtures = [m for m in ds.matches if (m.get("pre_match_date") or m["date"]) == cutoff
                        and {m["team"], m["opponent"]} == {team, opponent}]
            fixture = fixtures[0] if len(fixtures) == 1 else {}
            request.update(level=fixture.get("level"), round=fixture.get("round"))
        appearances = [p for p in ds.players if p["player"] == player and p["team"] == team and p["date"] < cutoff]
        versus = [p for p in appearances if p["opponent"] == opponent][-window:]
        appearances = appearances[-window:]
        other_appearances = [p for p in ds.players if p["player"] == other_player and p["team"] == opponent and p["date"] < cutoff][-window:]
        interactions = [r for r in ds.interactions if r["date"] < cutoff and r["player"] == player and r["opponent_player"] == other_player]
        meeting_ids = list(dict.fromkeys(r["match_id"] for r in interactions))[-window:]
        interactions = [r for r in interactions if r["match_id"] in meeting_ids]
        opportunities = sum(r["opportunities"] for r in interactions)
        successes = sum(r["successes"] for r in interactions)
        player_avg = mean(p["score"] for p in appearances) if appearances else None
        vs_avg = mean(p["score"] for p in versus) if versus else None

        def side_features(index):
            a, b = summaries[index], summaries[1-index]
            side_pair = summary(ds.history((team, opponent)[index], cutoff, (opponent, team)[index])[-window:])
            return {"team_recent_avg": a["avg"], "team_recent_conceded": a["conceded"],
                    "team_recent_win_rate": a["win_rate"], "team_recent_draw_rate": a["draw_rate"], "team_matches": a["matches"],
                    "opponent_recent_avg": b["avg"], "opponent_recent_conceded": b["conceded"],
                    "opponent_recent_win_rate": b["win_rate"], "opponent_recent_draw_rate": b["draw_rate"], "opponent_matches": b["matches"],
                    "h2h_avg": side_pair["avg"], "h2h_win_rate": side_pair["win_rate"], "h2h_matches": side_pair["matches"],
                    "is_home": int(venue == ("home" if index == 0 else "away")), "is_neutral": int(venue == "neutral"),
                    "player_recent_avg": player_avg if index == 0 else None,
                    "player_opponent_avg": vs_avg if index == 0 else None,
                    "player_appearances": len(appearances) if index == 0 else 0,
                    "opponent_player_recent_avg": mean(p["score"] for p in other_appearances) if other_appearances and index == 0 else None,
                    "interaction_rate": successes / opportunities if opportunities and index == 0 else None,
                    "interaction_opportunities": opportunities if index == 0 else 0,
                    "interaction_successes": successes if index == 0 else 0,
                    "interaction_avg_score": sum(r["score"] for r in interactions) / len(meeting_ids) if meeting_ids and index == 0 else None}

        feature_sets = [side_features(0), side_features(1)]
        a, b = summaries
        shares = {"team": a["wins"] + b["losses"] + 1, "opponent": b["wins"] + a["losses"] + 1}
        if meta["draw"]:
            shares["draw"] = a["draws"] + b["draws"] + 1
        total = sum(shares.values())
        if announced is not None:
            winner = self._run_pretrained(sport, "winner", [{**request, **announced}], stage=POST_TOSS)[0]
        else:
            winner = self._prediction(sport, "winner", feature_sets[0], {k: v/total for k, v in shares.items()}, request)
        if winner["value"] is not None and not meta["draw"] and winner["value"].get("draw", 0) > 0:
            winner = {"value": None, "source": "unavailable", "error": "This sport does not support a draw output"}
        if announced is not None or self.registries[sport].configs.get("team_score", {}).get("format") in ("tabicl_regressor", "trained_ridge"):
            reverse = {**request, "team": opponent, "opponent": team, "player": other_player, "opponent_player": player,
                       "venue": "away" if supplied_venue == "home" else "home" if supplied_venue == "away" else "neutral"}
            score_requests = [request, reverse]
            if announced is not None:
                score_requests = [{**request, **announced}, {**reverse, **reverse_xis(announced)}]
            scores = self._run_pretrained(sport, "team_score", score_requests, stage=stage)
        else:
            scores = []
            for i in range(2):
                f = feature_sets[i]
                reference = .55*f["team_recent_avg"] + .3*f["opponent_recent_conceded"] + .15*(f["h2h_avg"] if f["h2h_avg"] is not None else f["team_recent_avg"])
                scores.append(self._prediction(sport, "team_score", f, reference))
        player_estimate = .75*player_avg + .25*(vs_avg if vs_avg is not None else player_avg) if player_avg is not None else None
        player_prediction = self._prediction(sport, "player_score", feature_sets[0], player_estimate, request) if player else {"value": None, "source": "unavailable", "error": "No player data: add real players.csv appearances to enable individual scoring"}
        threat = self._prediction(sport, "player_threat", feature_sets[0], successes/opportunities if opportunities else None, request) if player and other_player else {"value": None, "source": "unavailable", "error": "No player matchup data: add real player appearances and directional interactions"}
        scoring_form = None
        if self.config.get("pretrained"):
            try:
                form_requests = [{**request, "player": None}, {**request, "team": opponent, "player": None}]
                if player:
                    form_requests.append(request)
                forms = self.pretrained.forecast(ds, form_requests, meta)
                scoring_form = {"teams": forms[:2], "player": forms[2] if player else {"value": None, "source": "unavailable", "error": "No real player scoring history"}}
            except Exception as exc:
                unavailable = {"value": None, "source": "unavailable", "error": f"{type(exc).__name__}: {exc}"}
                scoring_form = {"teams": [unavailable, unavailable], "player": unavailable}
        warnings = []
        if self.config["sports"][sport].get("demo", False):
            warnings.append("Synthetic demonstration data. These are not real fixtures or validated forecasts.")
        if any(s["matches"] < window for s in summaries):
            warnings.append("One or both sides have fewer matches than the requested form window.")
        if not h2h:
            warnings.append("No head-to-head meetings before this date; head-to-head features remain missing.")
        if not opportunities:
            warnings.append("No direct interactions for this player pair before this date; no historical threat rate is available.")
        formats = {self.registries[sport].configs.get(t, {}).get("format") for t in ("winner", "team_score", "player_score", "player_threat")}
        if formats & set(TABICL_FORMATS):
            warnings.append("TabICL probabilities and regression outputs are uncalibrated sports forecasts. Frozen general pretrained weights use only completed pre-cutoff labeled examples; no sports accuracy is implied by publisher benchmarks.")
        if stage == POST_TOSS:
            warnings.append("Post-toss winner and team scores use the supplied toss and starting XIs. Player form uses completed pre-cutoff results.")
        elif formats & set(TRAINED_FORMATS):
            warnings.append("Trained outcome and score models use Elo and completed pre-cutoff results.")
            if sport == "cricket":
                warnings.append("Cricket squad strength uses the previous starting XIs as a proxy.")
        if self.config.get("pretrained"):
            warnings.append("Chronos forecasts scoring form by appearance order, without opponent adjustment. Historical form may be stale; check source coverage.")
        if threat.get("target"):
            warnings.append(threat["target"])
        warnings.extend(ds.provenance.get("limitations", []))
        # Measured record of the model that produced this outcome, if it has been evaluated.
        measured = self.comparison.get(sport, {})
        name = COMPARISON_NAMES.get(self.registries[sport].configs.get("winner", {}).get("format"))
        if stage == POST_TOSS:
            measured = measured.get("stages", {}).get(POST_TOSS, {})
            name = POST_TOSS_MODELS["winner"]
        record = measured.get("winner", {}).get(name) if name and not ds.synthetic else None
        if sport == "cricket" and name in ("trained_logistic", "elo_only") and measured.get("stage") != stage:
            record = None
        if winner["value"] is not None and record and "accuracy" in record:
            winner = {**winner, "track_record": {**record, "heldout_from": measured.get("split"), "data_through": measured.get("latest")}}
        trained_inputs = next((p["features"] for p in (winner, scores[0])
                               if sport == "cricket" and p.get("provenance", {}).get("stage") == stage), None)
        ratings = trained_inputs or self.trained.index(sport, ds)[1].features(team, opponent, cutoff, supplied_venue)
        strength = {"team": {"rating": ratings["team_elo"], "matches": ratings["team_rated_matches"]},
                    "opponent": {"rating": ratings["opponent_elo"], "matches": ratings["opponent_rated_matches"]},
                    "expected": ratings["elo_expected"], "home_advantage_applied": (venue if trained_inputs else supplied_venue) != "neutral",
                    "note": "Elo strength rating from results before the prediction date; 1500 is a side with no history."}
        all_p = [winner, *scores, player_prediction, threat]
        if any(p["source"] == "reference" for p in all_p):
            warnings.append("Reference estimates use historical arithmetic, not ML. Percentages are not calibrated probabilities; no accuracy claim is made.")
        insights = None
        if sport == "cricket":
            horizons = [10, 20]
            if "ODI" in str(meta.get("format", "")):
                horizons = [10, 20, 30, 40, 50]
            elif "Test" in str(meta.get("format", "")):
                horizons = [10, 20, 30, 40, 50]
            insights = {
                "format": meta.get("format", "Cricket"),
                "pitch_report": {"value": None, "source": "unavailable",
                                 "error": "Pitch, weather, and ground-condition fields are not present in the local dataset."},
                "player_report": {"player": player, "score": player_prediction, "threat": threat,
                                  "basis": "Selected-player history and direct interaction records before the cutoff."},
                "innings_forecasts": [{"overs": overs, "teams": [None, None], "source": "unavailable",
                                      "error": "No over-by-over innings data or horizon model is configured; final-score forecasts are shown above."}
                                     for overs in horizons],
            }
        return {"sport": sport, "meta": meta, "team": team, "opponent": opponent,
                **({"stage": stage} if sport == "cricket" else {}),
                "cutoff": cutoff, "window": window, "venue": venue, "demo": self.config["sports"][sport].get("demo", False),
                "summaries": summaries, "history": histories, "h2h": h2h, "h2h_summary": pair,
                "winner": winner, "scores": scores, "player_score": player_prediction, "threat": threat,
                "scoring_form": scoring_form, "strength": strength,
                "insights": insights,
                "player": player, "opponent_player": other_player, "players": players,
                "player_history": appearances, "player_vs_opponent": versus,
                "interaction": {"opportunities": opportunities, "successes": successes, "meetings": len(meeting_ids),
                                "rate": successes/opportunities if opportunities else None, "rows": interactions},
                "breakdowns": build_breakdowns(ds, team, opponent, player, other_player, cutoff),
                "features": feature_sets, "warnings": warnings,
                "provenance": {"data_dir": str(ds.folder), "data_sources": ds.provenance, "data_sha256": ds.file_hashes,
                               "latest_eligible": max(h[-1]["date"] for h in histories),
                               "cutoff_rule": "Only matches dated strictly before the prediction date are used"}}
