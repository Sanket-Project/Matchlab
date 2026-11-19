import copy
import csv
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from matchlab.contexts import HistoryIndex
from matchlab.cricket import POST_TOSS_FEATURES, CricketHistory, validate_post_toss
from matchlab.data import read_csv
from matchlab.engine import Engine
from matchlab.ratings import RatingIndex
from matchlab.sports import SPORTS
from matchlab.trained import TrainedModels
from tools import import_public_data


def match(mid, day, season, ground="Oval", batting_first="A", outcome="team"):
    return dict(match_id=mid, date=day, pre_match_date=day, season=season, ground=ground,
                team="A", opponent="B", team_score=160, opponent_score=150, outcome=outcome,
                venue="neutral", batting_first=batting_first, toss_winner="A", toss_decision="bat")


def dataset(matches, players=(), interactions=()):
    return SimpleNamespace(matches=matches, players=list(players), interactions=list(interactions), synthetic=False)


class CricketStageOneTests(unittest.TestCase):
    def test_season_boundary_pulls_ratings_back_before_same_day_results(self):
        ds = dataset([match("a", "2023-04-01", "2023"), match("b", "2024-04-01", "2024")])
        index = CricketHistory(ds, HistoryIndex(ds))
        ratings = RatingIndex(ds, k=40, cricket=index, season_pullback=.5)
        self.assertEqual(ratings.rating("A", "2024-03-31"), (1520, 1))
        self.assertEqual(ratings.rating("A", "2024-04-01"), (1510, 1))
        self.assertEqual(ratings.rating("B", "2024-04-01"), (1490, 1))
        self.assertEqual(ratings.rating("A", "2024-04-02")[1], 2)
        self.assertEqual(ratings.features("A", "B", "2024-03-28", season="2024")["team_elo"], 1510)

    def test_home_ground_ignores_current_season_and_unavailable_results(self):
        old = match("a", "2023-04-01", "2023")
        new = [match(str(i), f"2024-04-0{i}", "2024", "Park") for i in range(1, 5)]
        new += [match("later", "2024-04-05", "2023", "Park")]
        ds = dataset([old, *new])
        index = CricketHistory(ds, HistoryIndex(ds))
        self.assertEqual(index.home_ground("A", "2024-04-05", "2024"), "Oval")
        self.assertIsNone(index.home_ground("A", "2023-04-01", "2023"))
        # Both teams had the same most frequent ground in this fixture.
        self.assertEqual(index.venue("A", "B", "2024-04-05", "Oval", "2024"), "neutral")
        old["opponent"] = "C"
        index = CricketHistory(ds, HistoryIndex(ds))
        self.assertEqual(index.venue("A", "B", "2024-04-05", "Oval", "2024"), "home")
        self.assertEqual(index.venue("B", "A", "2024-04-05", "Oval", "2024"), "away")

    def test_ground_character_uses_recorded_order_and_minimum_completed_matches(self):
        matches = [match(str(i), f"2024-04-0{i}", "2024", batting_first="A" if i <= 3 else "B")
                   for i in range(1, 7)]
        ds = dataset(matches)
        index = CricketHistory(ds, HistoryIndex(ds))
        self.assertEqual(index.ground_features("Oval", "2024-04-05"), (None, None))
        self.assertEqual(index.ground_features("Oval", "2024-04-06"), (156, .6))
        self.assertEqual(index.ground_features("Other", "2024-04-06"), (None, None))

    def test_stage_one_uses_only_the_last_completed_xi_and_prior_player_form(self):
        old, upcoming = match("a", "2024-04-01", "2024"), match("b", "2024-04-02", "2024")
        players = [dict(match_id=m["match_id"], date=m["date"], player=f"{side}{i}",
                        team=side, score=i if i < 11 else 1000, starter="1" if i < 11 else "0")
                   for m in (old, upcoming) for side in ("A", "B") for i in range(12)]
        interactions = [dict(match_id="a", date=old["date"], player="A0", opponent_player="B0",
                             opportunities=10, successes=2, score=8),
                        dict(match_id="a", date=old["date"], player="B0", opponent_player="A0",
                             opportunities=20, successes=1, score=4),
                        dict(match_id="b", date=upcoming["date"], player="A0", opponent_player="B0",
                             opportunities=2, successes=2, score=8)]
        ds = dataset([old, upcoming], players, interactions)
        features = TrainedModels().features("cricket", ds, "A", "B", upcoming["date"], 5)
        self.assertEqual(features["team_squad_runs"], 5)
        self.assertEqual(features["team_squad_batting_boundary_rate"], .2)
        self.assertEqual(features["team_squad_bowling_boundary_rate"], .05)
        changed = copy.deepcopy(ds)
        changed.matches[-1].update(toss_winner="B", toss_decision="field", batting_first="B", team_score=900)
        changed.interactions[-1].update(successes=0, score=0)
        for p in changed.players:
            if p["match_id"] == "b":
                p.update(score=999, starter="0")
        self.assertEqual(features, TrainedModels().features("cricket", changed, "A", "B", upcoming["date"], 5))
        for p in changed.players:
            p.pop("starter")
        unknown = TrainedModels().features("cricket", changed, "A", "B", upcoming["date"], 5)
        self.assertIsNone(unknown["team_squad_runs"])

    def test_parameter_selection_and_prediction_ignore_future_outcomes(self):
        matches = [match(f"{year}-{i}", f"{year}-04-{i:02}", str(year), outcome="team" if i % 5 else "opponent")
                   for year in range(2020, 2025) for i in range(1, 11)]
        ds = dataset(matches)
        cutoff = "2024-04-03"
        q = dict(team="A", opponent="B", cutoff=cutoff, window=5, venue="neutral")
        changed = copy.deepcopy(ds)
        for m in changed.matches:
            if m["date"] >= cutoff:
                m.update(outcome="draw", team_score=777, opponent_score=777, batting_first="B")
        args = ("winner", {"format": "trained_logistic"}, [q], SPORTS["cricket"])
        first = TrainedModels().predict("cricket", ds, *args)[0]
        second = TrainedModels().predict("cricket", changed, *args)[0]
        self.assertEqual(first, second)
        self.assertEqual(set(first["value"]), {"team", "opponent"})
        self.assertEqual(first["provenance"]["elo_selection"]["folds"], 3)
        self.assertIn("team_squad_runs", first["provenance"]["unavailable_features"])

    def test_engine_uses_observed_outcome_classes_at_the_prediction_cutoff(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            matches = [match("a", "2024-04-01", "2024"), match("b", "2024-04-04", "2024", outcome="draw")]
            with (folder / "matches.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(matches[0]))
                writer.writeheader()
                writer.writerows(matches)
            engine = Engine({"sports": {"cricket": {"data_dir": directory, "reference_mode": True,
                                                    "scoring": {"draw": False}}}}, folder)
            q = dict(sport="cricket", team="A", opponent="B", cutoff="2024-04-04")
            self.assertNotIn("draw", engine.analyze(q)["winner"]["value"])
            self.assertIn("draw", engine.analyze({**q, "cutoff": "2024-04-05"})["winner"]["value"])

    def test_imports_innings_order_and_recovers_starting_players_from_replacements(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "cricket").mkdir()
            names = {side: [f"{side}{i}" for i in range(11 if side == "B" else 12)] for side in ("A", "B")}
            delivery = dict(batter="B0", bowler="A11", runs=dict(total=4, batter=4),
                            replacements={"match": [dict(team="A", **{"in": "A11", "out": "A0"})]})
            row = dict(info=dict(dates=["2024-04-01"], teams=["A", "B"], overs=20, season="2024",
                                 outcome={"winner": "B"}, players=names),
                       innings=[dict(team="B", overs=[dict(deliveries=[delivery])]), dict(team="A", overs=[])])
            with zipfile.ZipFile(folder / "cricket/ipl_json.zip", "w") as archive:
                archive.writestr("123.json", json.dumps(row))
            with patch.multiple(import_public_data, RAW=folder, OUT=folder / "out"):
                import_public_data.cricket()
            matches = read_csv(folder / "out/cricket/matches.csv", {"batting_first"})
            players = {p["player"]: p for p in read_csv(folder / "out/cricket/players.csv", {"player", "starter"})}
            self.assertEqual(matches[0]["batting_first"], "B")
            self.assertEqual(players["A0"]["starter"], "1")
            self.assertEqual(players["A11"]["starter"], "0")


class CricketStageTwoTests(unittest.TestCase):
    @staticmethod
    def starting_players(matches):
        return [dict(match_id=m["match_id"], date=m["date"], team=side, player=f"{side}{i}", score=i, starter="1")
                for m in matches for side in ("A", "B") for i in range(11)]

    @staticmethod
    def announced():
        return dict(toss_winner="A", toss_decision="bat",
                    team_xi=[f"A{i}" for i in range(11)], opponent_xi=[f"B{i}" for i in range(11)])

    def test_requires_complete_and_distinct_announced_xis_and_a_valid_toss(self):
        valid = self.announced()
        self.assertEqual(validate_post_toss(valid, "A", "B"), valid)
        for changed, message in ((dict(toss_winner="C"), "toss winner"), (dict(toss_decision="bowl"), "bat or field"),
                                 (dict(team_xi=valid["team_xi"][:-1]), "11"), (dict(team_xi=["A0"] * 11), "distinct"),
                                 (dict(opponent_xi=[*valid["opponent_xi"][:-1], "A0"]), "both XIs"),
                                 (dict(team_xi=[*valid["team_xi"][:-1], " "]), "11")):
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, message):
                validate_post_toss({**valid, **changed}, "A", "B")

    def test_announced_players_replace_the_last_xi_and_use_only_prior_form(self):
        matches = [match(str(i), f"2024-04-0{i}", "2024", batting_first="A" if i <= 3 else "B")
                   for i in range(1, 7)]
        players = self.starting_players(matches)
        previous, upcoming = matches[-2:]
        for m in (previous, upcoming):
            players.append(dict(match_id=m["match_id"], date=m["date"], team="A", player="A11", score=110, starter="0"))
        interactions = [dict(match_id=m["match_id"], date=m["date"], player="A11", opponent_player="B0",
                             opportunities=10, successes=4, score=16) for m in (previous, upcoming)]
        ds = dataset(matches, players, interactions)
        announced = {**self.announced(), "team_xi": [f"A{i}" for i in range(1, 12)]}
        args = ("cricket", ds, "A", "B", upcoming["date"], 5)
        models = TrainedModels()
        pre = models.features(*args)
        post = models.features(*args, post_toss=announced)
        self.assertTrue(set(POST_TOSS_FEATURES).isdisjoint(pre))
        self.assertEqual(pre["team_squad_runs"], 5)
        self.assertAlmostEqual(post["team_squad_runs"], 15)
        self.assertEqual(post["team_squad_batting_boundary_rate"], .4)
        self.assertEqual(post["toss_won"], 1)
        self.assertEqual(post["toss_decision_bat"], 1)
        self.assertEqual(post["toss_decision_ground_win_rate"], .6)
        field = models.features(*args, post_toss={**announced, "toss_winner": "B", "toss_decision": "field"})
        self.assertEqual([field[k] for k in POST_TOSS_FEATURES], [0, 0, 0])
        self.assertIsNone(models.features(*args, ground="Unknown", post_toss=announced)["toss_decision_ground_win_rate"])
        changed = copy.deepcopy(ds)
        changed.matches[-1].update(team_score=1000, outcome="draw", toss_winner="B", toss_decision="field")
        changed.interactions[-1].update(successes=10, score=40)
        for p in changed.players:
            if p["match_id"] == upcoming["match_id"]:
                p.update(starter="0", score=999)
        self.assertEqual(post, TrainedModels().features("cricket", changed, *args[2:], post_toss=announced))

    def test_training_uses_only_complete_post_toss_pairs_with_reversed_xis(self):
        matches = [match(str(i), f"2024-04-0{i}", "2024") for i in range(1, 7)]
        matches[3]["toss_decision"] = ""
        players = [p for p in self.starting_players(matches) if (p["match_id"], p["player"]) != ("5", "A0")]
        for p in players:
            if p["team"] == "B":
                p["score"] += 20
        ds = dataset(matches, players)
        models = TrainedModels()
        args = ("cricket", ds, "winner", "2024-04-06", 5)
        pre = models.examples(*args)
        self.assertEqual([r["match_id"] for r in pre], ["3", "3", "4", "4", "5", "5"])
        post = models.examples(*args, stage="post_toss")
        self.assertEqual([r["match_id"] for r in post], ["3", "3"])
        for row, runs, won in zip(post, (5, 25), (1, 0)):
            self.assertEqual(row["features"]["team_squad_runs"], runs)
            self.assertEqual(row["features"]["toss_won"], won)

    def test_engine_routes_explicit_stage_without_crossing_fit_caches(self):
        matches = [match(f"{year}-{i}", f"{year}-04-{i:02}", str(year), outcome="team" if i % 5 else "opponent")
                   for year in range(2020, 2025) for i in range(1, 11)]
        players = self.starting_players(matches)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for filename, rows in (("matches.csv", matches), ("players.csv", players)):
                with (folder / filename).open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
            engine = Engine({"sports": {"cricket": {"data_dir": directory, "models": {
                "winner": {"format": "trained_logistic"}, "team_score": {"format": "trained_ridge"}}}}}, folder)
            q = dict(sport="cricket", team="A", opponent="B", cutoff="2024-04-03")
            announced = self.announced()
            announced["team_xi"] = [f"Debutant {i}" for i in range(11)]
            pre = engine.analyze(q)
            self.assertEqual(pre, engine.analyze({**q, **announced}))
            with self.assertRaisesRegex(ValueError, "toss winner"):
                engine.analyze({**q, "stage": "post_toss"})
            post = engine.analyze({**q, **announced, "stage": "post_toss"})
            self.assertEqual((pre["stage"], post["stage"]), ("pre_match", "post_toss"))
            self.assertEqual(set(post["winner"]["value"]), {"team", "opponent"})
            self.assertAlmostEqual(sum(post["winner"]["value"].values()), 1)
            self.assertNotEqual(pre["winner"]["sha256"], post["winner"]["sha256"])
            self.assertIn("team_squad_runs", post["winner"]["provenance"]["imputed_features"])
            self.assertEqual([p["features"]["toss_won"] for p in post["scores"]], [1, 0])
            self.assertEqual([p["provenance"]["stage"] for p in post["scores"]], ["post_toss"] * 2)
            self.assertEqual(pre, engine.analyze(q))

    def test_evaluation_compares_the_same_holdout_when_post_toss_inputs_are_missing(self):
        from tools.evaluate_models import evaluate

        matches = [match(f"{year}-{i}", f"{year}-04-{i:02}", str(year), outcome="team" if i % 5 else "opponent")
                   for year in range(2020, 2025) for i in range(1, 11)]
        matches[-1]["toss_winner"] = ""
        ds = dataset(matches, self.starting_players(matches))
        engine = SimpleNamespace(datasets={"cricket": ds}, metadata={"cricket": SPORTS["cricket"]},
                                 pretrained=SimpleNamespace(index=lambda sport, data: HistoryIndex(data)))
        report = evaluate(engine, {}, "cricket", 400)
        pre, post = (report["stages"][stage] for stage in ("pre_match", "post_toss"))
        self.assertEqual(report["evaluated_matches"], 10)
        self.assertEqual(post["excluded_missing_inputs"], 1)
        self.assertEqual(pre["evaluated_matches"], post["evaluated_matches"])
        self.assertEqual(pre["winner"]["class_frequency"], post["winner"]["class_frequency"])
        self.assertEqual(post["winner"]["trained_logistic"]["n"], 9)
        self.assertEqual(post["team_score"]["trained_ridge"]["n"], 18)
        self.assertEqual(post["split"], "2024-04-01")


if __name__ == "__main__":
    unittest.main()
