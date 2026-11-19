import json
import random
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from matchlab import calibration, tracker


def sample(n, true_factor, seed=1):
    """Forecasts whose favourites really win adjust(p, true_factor) of the time."""
    rng = random.Random(seed)
    pairs = []
    for _ in range(n):
        p = rng.uniform(0.52, 0.9)
        pairs.append((p, rng.random() < calibration.adjust(p, true_factor)))
    return pairs


class FitTests(unittest.TestCase):
    def test_nothing_is_applied_below_the_minimum_sample(self):
        info = calibration.fit([(0.9, False)] * (calibration.MIN_GRADED - 1))
        self.assertEqual((info["active"], info["factor"], info["graded"]), (False, 1.0, calibration.MIN_GRADED - 1))

    def test_overconfident_model_is_pulled_toward_even(self):
        info = calibration.fit(sample(600, 0.6))
        self.assertTrue(info["active"])
        self.assertTrue(0.5 <= info["factor"] < 0.8, info)
        self.assertLess(calibration.adjust(0.8, info["factor"]), 0.8)

    def test_cautious_model_is_pushed_away_from_even(self):
        info = calibration.fit(sample(600, 1.4))
        self.assertGreater(info["factor"], 1.15)

    def test_well_calibrated_model_is_left_close_to_alone(self):
        info = calibration.fit(sample(600, 1.0))
        self.assertTrue(0.85 <= info["factor"] <= 1.15, info)

    def test_a_small_sample_moves_less_than_a_large_one(self):
        small = calibration.fit(sample(calibration.MIN_GRADED, 0.5, seed=3))
        large = calibration.fit(sample(1500, 0.5, seed=3))
        self.assertGreater(small["factor"], large["factor"])

    def test_factor_stays_inside_its_limits(self):
        info = calibration.fit([(0.95, False)] * 200)
        self.assertEqual(info["factor"], calibration.LOW)

    def test_either_side_of_the_pair_may_be_given(self):
        self.assertEqual(calibration.fit([(0.3, True)] * 40)["factor"], calibration.fit([(0.7, True)] * 40)["factor"])


class ApplyTests(unittest.TestCase):
    def forecast(self):
        return {"supported": True, "teams": [{"name": "Alpha", "win": 0.8}, {"name": "Beta", "win": 0.2}]}

    def test_active_calibration_corrects_both_sides_and_keeps_the_raw_number(self):
        forecast = calibration.apply(self.forecast(), {"active": True, "factor": 0.7, "graded": 40, "needed": 30})
        first, second = forecast["teams"]
        self.assertEqual((first["win_model"], second["win_model"]), (0.8, 0.2))
        self.assertTrue(0.5 < first["win"] < 0.8)
        self.assertAlmostEqual(first["win"] + second["win"], 1.0)

    def test_inactive_calibration_changes_nothing(self):
        forecast = calibration.apply(self.forecast(), calibration.fit([]))
        self.assertEqual(forecast["teams"][0], {"name": "Alpha", "win": 0.8})
        self.assertEqual(forecast["calibration"]["graded"], 0)

    def test_even_chance_is_never_moved(self):
        self.assertAlmostEqual(calibration.adjust(0.5, 0.6), 0.5)


class TrackerPairsTests(unittest.TestCase):
    def test_pairs_use_the_raw_number_of_counted_forecasts_of_one_sport(self):
        entry = lambda sport, teams, counted, correct: {
            "fixture": {"id": "x"}, "timeline": [], "pre": {"sport": sport, "stage": "pre", "teams": teams},
            "result": {"saved_before_start": counted, "winner_pick": {"correct": correct}}}
        data = {
            "a": entry("cricket", [{"name": "A", "win": 0.7, "win_model": 0.8}, {"name": "B", "win": 0.3, "win_model": 0.2}], True, True),
            "b": entry("cricket", [{"name": "A", "win": 0.4}, {"name": "B", "win": 0.6}], True, False),
            "late": entry("cricket", [{"name": "A", "win": 0.9}, {"name": "B", "win": 0.1}], False, True),
            "t": entry("tennis", [{"name": "A", "win": 0.55}, {"name": "B", "win": 0.45}], True, True),
            "waiting": {"fixture": {"id": "w"}, "timeline": [], "pre": {"stage": "pre", "teams": [{"name": "A", "win": 0.6}, {"name": "B", "win": 0.4}]}},
        }
        del data["b"]["pre"]["sport"]                  # older cricket entries carry no sport
        with TemporaryDirectory() as temp:
            path = Path(temp) / tracker.FILE
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(tracker.graded_pairs(Path(temp), "cricket"), [(0.8, True), (0.6, False)])
            self.assertEqual(tracker.graded_pairs(Path(temp), "tennis"), [(0.55, True)])

    def test_saved_forecast_keeps_the_raw_number(self):
        forecast = {"supported": True, "sport": "tennis", "stage": "pre", "format": "Best of 3", "intel": {"state": "pre"},
                    "set_scores": [{"score": "2-0", "winner": "Alpha"}],
                    "teams": [{"name": "Alpha", "win": 0.7, "win_model": 0.8}, {"name": "Beta", "win": 0.3, "win_model": 0.2}]}
        with TemporaryDirectory() as temp:
            saved = tracker.record(Path(temp), {"id": "tennis-1", "team": "Alpha", "opponent": "Beta"}, forecast)
            self.assertEqual(saved["pre"]["teams"][0], {"name": "Alpha", "win": 0.7, "win_model": 0.8})


if __name__ == "__main__":
    unittest.main()
