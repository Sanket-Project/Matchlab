"""Strength ratings and locally trained models: causality and output validity."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from matchlab.data import Dataset
from matchlab.engine import Engine, default_config
from matchlab.ratings import BASE, RatingIndex
from matchlab.sports import SPORTS
from matchlab.trained import TrainedModels

REAL = (ROOT / "data/real/football/matches.csv").exists()


def mutate_future(ds, cutoff, field="date"):
    """Copy of a dataset with every result on/after the cutoff reversed."""
    clone = copy.copy(ds)
    clone.matches = [dict(m) for m in ds.matches]
    for m in clone.matches:
        if m[field] >= cutoff:
            m["team_score"], m["opponent_score"] = m["opponent_score"] + 5, m["team_score"]
            m["outcome"] = {"team": "opponent", "opponent": "team"}.get(m["outcome"], "team")
    clone.by_id = {m["match_id"]: m for m in clone.matches}
    return clone


@unittest.skipUnless(REAL, "One-time public data setup not installed")
class RatingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.football = Dataset(ROOT / "data/real/football", SPORTS["football"])
        cls.tennis = Dataset(ROOT / "data/real/tennis", SPORTS["tennis"])

    def test_ratings_ignore_results_on_or_after_the_cutoff(self):
        cutoff = "2023-03-01"
        before, after = RatingIndex(self.football), RatingIndex(mutate_future(self.football, cutoff))
        for side in self.football.teams:
            self.assertEqual(before.rating(side, cutoff), after.rating(side, cutoff))
        self.assertNotEqual(before.rating("Arsenal FC", "2024-06-01"), after.rating("Arsenal FC", "2024-06-01"))
        self.assertEqual(before.rating("Arsenal FC", "1990-01-01"), (BASE, 0))
        self.assertEqual(before.rating("Nobody FC", cutoff), (BASE, 0))

    def test_strong_sides_rate_higher_and_home_edge_is_symmetric(self):
        index = RatingIndex(self.football)
        city, _ = index.rating("Manchester City FC", "2024-06-01")
        self.assertGreater(city, 1600)
        self.assertLess(index.rating("Sheffield United FC", "2024-06-01")[0], 1500)
        home = index.features("Arsenal FC", "Chelsea FC", "2024-06-01", "home")
        away = index.features("Chelsea FC", "Arsenal FC", "2024-06-01", "away")
        self.assertAlmostEqual(home["elo_diff"], -away["elo_diff"])
        self.assertAlmostEqual(home["elo_expected"] + away["elo_expected"], 1.0)

    def test_tennis_results_count_only_once_available(self):
        index = RatingIndex(self.tennis)
        m = self.tennis.matches[len(self.tennis.matches) // 2]
        self.assertLess(m["pre_match_date"], m["date"])
        # The day the tournament starts, and any day up to availability, this result is unknown.
        clone = mutate_future(self.tennis, m["date"])
        self.assertEqual(index.rating(m["team"], m["date"]), RatingIndex(clone).rating(m["team"], m["date"]))
        points = index.rank_points(m["team"], m["date"])
        self.assertTrue(points is None or points > 0)
        self.assertIsNone(index.rank_points(m["team"], "1990-01-01"))


@unittest.skipUnless(REAL, "One-time public data setup not installed")
class TrainedModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.football = Dataset(ROOT / "data/real/football", SPORTS["football"])
        cls.meta = SPORTS["football"]
        cls.query = dict(team="Arsenal FC", opponent="Brentford FC", cutoff="2024-02-01", window=5, venue="home")

    def test_outcome_probabilities_are_valid_and_favour_the_stronger_side(self):
        models = TrainedModels()
        for fmt in ("trained_elo", "trained_logistic"):
            out = models.predict("football", self.football, "winner", {"format": fmt}, [self.query], self.meta)[0]
            self.assertEqual(set(out["value"]), {"team", "draw", "opponent"})
            self.assertAlmostEqual(sum(out["value"].values()), 1.0, places=6)
            self.assertGreater(out["value"]["team"], out["value"]["opponent"])
            self.assertLess(out["provenance"]["context_end"], self.query["cutoff"])
        swapped = dict(self.query, team="Brentford FC", opponent="Arsenal FC", venue="away")
        a, b = (models.predict("football", self.football, "winner", {"format": "trained_elo"}, [q], self.meta)[0]["value"] for q in (self.query, swapped))
        self.assertAlmostEqual(a["team"], b["opponent"], places=2)

    def test_ensemble_blends_valid_probabilities_and_records_components(self):
        out = TrainedModels().predict("football", self.football, "winner",
                                  {"format": "trained_ensemble"}, [self.query], self.meta)[0]
        self.assertEqual(set(out["value"]), {"team", "draw", "opponent"})
        self.assertAlmostEqual(sum(out["value"].values()), 1.0, places=6)
        self.assertEqual(out["provenance"]["weights"], {"trained_elo": 0.5, "trained_logistic": 0.5})
        self.assertEqual(set(out["provenance"]["components"]), {"trained_elo", "trained_logistic"})
        self.assertIn("Probability blend", out["adjustment"])

    def test_score_model_is_nonnegative_and_plausible(self):
        out = TrainedModels().predict("football", self.football, "team_score", {"format": "trained_ridge"}, [self.query], self.meta)[0]
        self.assertTrue(0 <= out["value"] < 6)
        self.assertEqual(out["source"], "model")

    def test_future_results_do_not_change_predictions(self):
        clone = mutate_future(self.football, self.query["cutoff"])
        for task, fmt in (("winner", "trained_logistic"), ("winner", "trained_elo"),
                          ("winner", "trained_ensemble"), ("team_score", "trained_ridge")):
            a = TrainedModels().predict("football", self.football, task, {"format": fmt}, [self.query], self.meta)[0]
            b = TrainedModels().predict("football", clone, task, {"format": fmt}, [self.query], self.meta)[0]
            self.assertEqual(a["value"], b["value"])
            self.assertEqual(a["sha256"], b["sha256"])

    def test_wrong_task_thin_history_and_synthetic_data_are_refused(self):
        models = TrainedModels()
        with self.assertRaisesRegex(ValueError, "winner task"):
            models.predict("football", self.football, "team_score", {"format": "trained_elo"}, [self.query], self.meta)
        with self.assertRaisesRegex(ValueError, "Insufficient"):
            models.predict("football", self.football, "winner", {"format": "trained_elo"}, [dict(self.query, cutoff="2021-09-01")], self.meta)
        demo = Engine(default_config(), ROOT).datasets["football"]
        teams = demo.teams[:2]
        with self.assertRaisesRegex(ValueError, "synthetic"):
            models.predict("football", demo, "winner", {"format": "trained_elo"}, [dict(team=teams[0], opponent=teams[1], cutoff="2026-11-10", window=5)], self.meta)

    def test_engine_serves_trained_models_with_rating_and_measured_record(self):
        config = json.loads((ROOT / "config.pretrained.example.json").read_text(encoding="utf-8"))
        config["sports"] = {"football": config["sports"]["football"]}
        config["sports"]["football"]["models"] = {"winner": {"format": "trained_elo"}, "team_score": {"format": "trained_ridge"}}
        config.pop("pretrained", None)
        engine = Engine(config, ROOT)
        statuses = {m["task"]: m["state"] for m in engine.catalog()[0]["models"]}
        self.assertEqual((statuses["winner"], statuses["team_score"]), ("available", "available"))
        a = engine.analyze(dict(self.query, sport="football"))
        self.assertEqual(a["winner"]["source"], "model")
        self.assertEqual([s["source"] for s in a["scores"]], ["model", "model"])
        self.assertGreater(a["strength"]["team"]["rating"], a["strength"]["opponent"]["rating"])
        if engine.comparison.get("football", {}).get("winner", {}).get("elo_only", {}).get("accuracy"):
            self.assertIn("beats_baseline", a["winner"]["track_record"])
        bad = copy.deepcopy(config)
        bad["sports"]["football"]["models"]["winner"] = {"format": "trained_ridge"}
        self.assertEqual(next(m for m in Engine(bad, ROOT).catalog()[0]["models"] if m["task"] == "winner")["state"], "unavailable")


if __name__ == "__main__":
    unittest.main()
