import csv
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from matchlab.f1 import POST_QUALIFYING, PRE_WEEKEND, RaceEngine, forecast_cutoff, simulate_race
from tools.fetch_f1_timing import live_snapshot
from tools.fetch_today_matches import parse_racing, parse_time
from tools.import_f1 import import_f1
from matchlab.live import annotate


ROOT = Path(__file__).resolve().parents[1]


class RaceSimulationTests(unittest.TestCase):
    def test_live_lap_uses_the_running_race_and_order(self):
        start = parse_time("2026-11-22T04:00:00Z")
        competition = {"date": "2026-11-22T04:00:00Z", "type": {"abbreviation": "Race"},
                       "status": {"period": 9, "type": {"state": "in"}},
                       "competitors": [{"order": 2, "athlete": {"displayName": "Second"}},
                                       {"order": 1, "athlete": {"displayName": "Leader"}}]}
        board = {"events": [{"competitions": [{**competition, "type": {"abbreviation": "Qual"}}, competition]}]}
        with patch("tools.fetch_f1_timing.get", return_value=board):
            self.assertEqual(live_snapshot(start), [{"lap": 9, "order": ["Leader", "Second"],
                                                    "positions": {"Leader": 1, "Second": 2}}])
            competition["status"]["type"]["state"] = "post"
            self.assertEqual(live_snapshot(start), [])

    def test_probabilities_are_coherent_and_seeded(self):
        utility = np.linspace(-2, 2, 20)
        retirement = np.linspace(.05, .3, 20)
        forecast = simulate_race(utility, retirement)
        np.testing.assert_array_equal(forecast, simulate_race(utility, retirement))
        win, podium, points, position = forecast.T
        np.testing.assert_allclose([win.sum(), podium.sum(), points.sum(), position.sum()], [1, 3, 10, 210])
        self.assertTrue(np.all(win <= podium) and np.all(podium <= points))

    def test_import_joins_race_qualifying_and_retirement_records(self):
        tables = {
            "season": (["id", "year"], [[1, 2026]]),
            "round": (["id", "api_id", "season_id", "circuit_id", "is_cancelled", "number", "name", "date"],
                      [[1, "round_example", 1, 1, "f", 1, "Test Grand Prix", "2026-03-08"]]),
            "circuit": (["id", "name"], [[1, "Test circuit"]]),
            "driver": (["id", "api_id", "reference", "forename", "surname"],
                       [[1, "driver_a", "a", "A", "Driver"], [2, "driver_b", "b", "B", "Driver"]]),
            "team": (["id", "api_id", "reference", "name"], [[1, "team_test", "team", "Test team"]]),
            "teamdriver": (["id", "driver_id", "team_id"], [[1, 1, 1], [2, 2, 1]]),
            "roundentry": (["id", "round_id", "team_driver_id"], [[1, 1, 1], [2, 1, 2]]),
            "session": (["id", "round_id", "type", "is_cancelled", "timestamp", "completed_laps"],
                        [[1, 1, "Q1", "f", "2026-03-07T14:00:00+00:00", ""], [2, 1, "R", "f", "2026-03-08T14:00:00+00:00", 54]]),
            "sessionentry": (["session_id", "round_entry_id", "position", "status", "detail", "grid", "points", "is_classified"],
                             [[1, 1, 2, "", "", "", "", ""], [1, 2, 1, "", "", "", "", ""],
                              [2, 1, 1, 0, "", 2, 25, "t"], [2, 2, 2, 11, "Engine", 1, 0, "f"]]),
        }
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            archive = folder / "source.zip"
            with zipfile.ZipFile(archive, "w") as z:
                for name, (header, rows) in tables.items():
                    data = io.StringIO()
                    csv.writer(data).writerows([header, *rows])
                    z.writestr(f"formula_one_{name}.csv", data.getvalue())
            import_f1(archive, folder / "output")
            engine = RaceEngine(folder / "output")
            race = engine.by_round[2026, 1]
            field, _ = engine.field(race)
            self.assertEqual([r["qualifying_position"] for r in field], [2, 1])
            self.assertEqual([r["dnf_type"] for r in field], ["", "mechanical"])
            self.assertEqual(race["regulation_era"], 2026)
            published = engine.published_grid(race, [
                dict(source_driver_id="driver_a", source_constructor_id="team_test", grid=1),
                dict(source_driver_id="driver_reserve", source_constructor_id="team_test", grid=2),
            ])
            self.assertEqual(published["grid"], {"a": 1, "driver_reserve": 2})
            self.assertEqual([r["constructor_id"] for r in published["field"]], ["team", "team"])


@unittest.skipUnless((ROOT / "data/real/f1/races.csv").exists(), "Local F1 data is unavailable")
class RaceHistoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = RaceEngine(ROOT / "data/real/f1")

    def test_future_results_and_grid_cannot_affect_pre_weekend_inputs(self):
        engine = self.engine
        race = engine.completed[-8]
        cutoff = forecast_cutoff(race, PRE_WEEKEND)
        entry = engine.entries[race["race_id"]][0]
        old, n = engine.features(race, entry, cutoff, PRE_WEEKEND, 22)
        for rows in engine.driver_history.values():
            for row in rows:
                if row["available"] >= cutoff:
                    row.update(pace=1000, teammate_gap=1000, dnf_type="mechanical", status="Retired", grid=99)
        new, count = engine.features(race, entry, cutoff, PRE_WEEKEND, 22)
        np.testing.assert_allclose(old, new)
        self.assertEqual(n, count)
        post, _ = engine.features(race, entry, cutoff, POST_QUALIFYING, 22)
        self.assertEqual(len(post), len(old) + 2)

    def test_espn_schedule_links_grand_prix_only(self):
        race = self.engine.completed[-1]
        when = race["start"].isoformat()
        data = {"events": [{"name": race["name"], "competitions": [
            {"id": "1", "type": {"abbreviation": "Qual"}, "date": when},
            {"id": "2", "type": {"abbreviation": "Race"}, "date": when}]}]}
        events = parse_racing("f1", "Formula 1", data, parse_time(when).astimezone().date())
        annotate({"sports": {"f1": events}}, {}, self.engine)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["race_id"], race["race_id"])
        self.assertTrue(events[0]["analyzable"])

    def test_upcoming_grid_is_required_and_duplicate_positions_are_rejected(self):
        race = next(r for r in self.engine.races if not r["completed"])
        with self.assertRaisesRegex(ValueError, "Grid unavailable"):
            self.engine.predict(race, POST_QUALIFYING)
        field, _ = self.engine.field(race)
        with self.assertRaisesRegex(ValueError, "unique"):
            self.engine.validate_grid({row["driver_id"]: 1 for row in field}, field)


if __name__ == "__main__":
    unittest.main()
