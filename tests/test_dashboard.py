"""Request budgets, the cricket simulator, the forecast builder and the track record. No network use."""
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from matchlab import budget, cricket_forecast, tracker
from matchlab import cricket_sim as sim

HAVE_BALLS = (ROOT / "data/real/cricket_sim/balls.npz").exists()


class BudgetTests(unittest.TestCase):
    def test_reserve_is_kept_for_priority_calls_and_the_limit_is_never_passed(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            spent = sum(budget.spend(root, "cricketdata", "list") for _ in range(150))
            self.assertEqual(spent, 95)                       # 100 a day, 5 held back
            self.assertFalse(budget.spend(root, "cricketdata", "list"))
            self.assertEqual(sum(budget.spend(root, "cricketdata", "pre-match", priority=True) for _ in range(20)), 5)
            self.assertEqual(budget.status(root)["cricketdata"]["remaining"], 0)
            self.assertEqual(budget.refresh_interval(root), 3600)

    def test_provider_count_is_adopted_and_a_new_day_resets(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            budget.spend(root, "cricketdata", "list")
            budget.sync(root, "cricketdata", 41, 100)
            self.assertEqual(budget.status(root)["cricketdata"]["used"], 41)
            with patch.object(budget, "_today", return_value="2099-01-01"):
                self.assertEqual(budget.status(root)["cricketdata"]["used"], 0)

    def test_cache_expires(self):
        with TemporaryDirectory() as temp:
            cache = budget.Cache(Path(temp), "x")
            self.assertIsNone(cache.get(60))
            cache.put([1, 2])
            self.assertEqual(cache.get(60), [1, 2])
            self.assertIsNone(cache.get(-1))


class ClassifyTests(unittest.TestCase):
    def test_formats(self):
        kind = lambda **fixture: cricket_forecast.classify({"team": "A", "opponent": "B", **fixture}, None)
        self.assertEqual(kind(detail="t20", tournament="Tri-Series"), (1, False))
        self.assertEqual(kind(detail="Women's T20", tournament="WBBL"), (1, True))
        self.assertEqual(kind(detail="t10", tournament="Abu Dhabi T10 League"), (0, False))
        self.assertEqual(kind(detail="List A", tournament="Ford Trophy"), (2, False))
        self.assertEqual(kind(detail="Test", tournament="Pakistan v Sri Lanka T20 and Test tour")[0], None)
        self.assertEqual(kind(detail="First-class", tournament="Shield")[0], None)

    def test_scorecard_uses_completed_espn_over_and_truthful_winner_flags(self):
        from tools.fetch_match_intel import summarize

        sides = [{"id": "1", "team": {"displayName": "Alpha"}, "winner": "false"},
                 {"id": "2", "team": {"displayName": "Beta"}, "winner": "true"}]
        intel = summarize({"header": {"competitions": [{"competitors": sides}]}})
        self.assertEqual([side["winner"] for side in intel["teams"]], [False, True])
        self.assertEqual(cricket_forecast._balls(23.6), 144)


@unittest.skipUnless(HAVE_BALLS, "run tools/build_cricket_balls.py first")
class SimulatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = sim.load(ROOT)
        cls.model = sim.model(ROOT, sim.today_ordinal(), "short", False)
        match = next(m for m in reversed(cls.data.matches) if m["fmt"] == 1 and m["gender"] == "male" and m["intl"])
        cls.lineups = [side[:11] for side in match["xi"]]

    def test_totals_are_plausible_and_both_orders_are_played(self):
        _, results = self.model.run(1, self.lineups, sims=600, seed=1)
        for order in (0, 1):
            first, second = results[order]["first"], results[order]["second"]
            self.assertTrue(110 < first["runs"].mean() < 220)
            self.assertTrue((first["wickets"] <= 10).all() and (first["balls"] <= 120).all())
            self.assertTrue((second["runs"] <= first["runs"] + 7).all())      # a chase stops at the target
            np.testing.assert_allclose(first["bat_runs"].sum(1).mean(), first["runs"].mean(), rtol=0.12)
            self.assertTrue(0.02 < results[order]["first_wins"].mean() < 0.98)

    def test_no_causal_leak(self):
        self.assertTrue((self.data.day[self.model.match_ids] < self.model.cutoff).all())

    def test_live_chase_continues_from_the_current_score(self):
        state = {"innings": 2, "order": 0, "runs": 150, "wickets": 9, "balls": 110, "target": 200}
        _, results = self.model.run(1, self.lineups, sims=400, seed=2, orders=(0,), state=state)
        chase = results[0]["second"]
        self.assertTrue((chase["runs"] >= 150).all())
        self.assertGreater(results[0]["first_wins"].mean(), 0.95)             # 50 needed from 10 balls, one wicket left

    def test_live_projection_uses_the_scorecard_and_changes_with_the_chase(self):
        fixture = {"team": "Alpha", "opponent": "Beta", "detail": "T20"}
        xi = [{"name": f"Alpha {i}", "stats": {"1": {"batted": 1, "runs": 20}} if i == 0 else {}}
              for i in range(11)]
        xi[0]["stats"]["2"] = {"bowled": 1, "wickets": 2}
        chase_xi = [{"name": f"Beta {i}", "stats": {"2": {"batted": 1, "runs": 40}} if i == 8 else {}}
                    for i in range(11)]
        builder = cricket_forecast.Builder(ROOT, fixture, {"teams": [{"name": "Alpha", "xi": xi}, {"name": "Beta", "xi": chase_xi}]})
        builder.edge, builder.blend_weights = 0, (1, 0)
        labels = [[player["name"] for player in side] for side in (xi, chase_xi)]
        state = {"innings": 2, "order": 0, "runs": 130, "wickets": 8, "balls": 102, "target": 180,
                 "first_runs": 179, "first_wickets": 6, "first_period": 1, "lead": list(range(10)),
                 "player_figures_ready": True}
        with patch.object(cricket_forecast, "SIMS", 600):
            behind = builder.live(self.model, self.lineups, labels, None, dict(state), 4)
            closer = builder.live(self.model, self.lineups, labels, None, {**state, "runs": 170}, 4)
        self.assertGreater(closer["win"][1], behind["win"][1])
        self.assertGreaterEqual(closer["projected"]["low"], 170)
        self.assertTrue(behind["scenarios"])
        for scenario in behind["scenarios"]:
            self.assertAlmostEqual(sum(scenario["win"]), 1.0)
        players = {p["name"]: p for p in closer["players"]}
        self.assertIsNone(players["Alpha 0"]["final_runs"])
        self.assertEqual(players["Alpha 0"]["runs"], 20)
        self.assertGreaterEqual(players["Alpha 0"]["final_wickets"], 2)
        self.assertGreaterEqual(players["Beta 8"]["final_runs"], 40)

    def test_unknown_players_fall_back_to_position_averages(self):
        side = self.model.side([-1] * 11)
        self.assertEqual(side["known"], 0)
        self.assertTrue(np.isfinite(side["bat"]).all() and (side["use"] > 0).all())


class TrackerTests(unittest.TestCase):
    def forecast(self, state):
        team = lambda name, win: {"name": name, "win": win, "lineup_confirmed": True, "wickets_taken": 6.0,
                                  "first_innings": {"mean": 160, "low": 120, "high": 200, "wickets_lost": 6.5},
                                  "batters": [{"name": f"{name} Bat", "runs": 30, "top": 0.25}],
                                  "bowlers": [{"name": f"{name} Bowl", "wickets": 1.4, "top": 0.3}]}
        return {"supported": True, "stage": "post_toss", "format": "T20", "intel": {"state": state},
                "teams": [team("Alpha", 0.6), team("Beta", 0.4)]}

    def test_pre_match_forecast_is_saved_then_graded(self):
        fixture = {"id": "cricket-1", "team": "Alpha", "opponent": "Beta", "start": "2026-11-11T10:00:00Z", "espn": {"league": "1", "event": "2"}}
        player = lambda name, runs, wickets: {"name": name, "stats": {"1": {"batted": 1, "runs": runs}, "2": {"bowled": 1, "wickets": wickets}}}
        intel = {"ok": True, "state": "post", "status_text": "Alpha won by 12 runs", "teams": [
            {"name": "Alpha", "winner": True, "innings": [{"period": 1, "runs": 171, "wickets": 6}], "xi": [player("Alpha Bat", 80, 0), player("Alpha Bowl", 2, 3)]},
            {"name": "Beta", "winner": False, "innings": [{"period": 2, "runs": 159, "wickets": 9}], "xi": [player("Beta Bat", 10, 0), player("Beta Other", 60, 2)]}]}
        with TemporaryDirectory() as temp, patch.object(tracker, "_now", return_value="2026-11-11T09:45:00+00:00"):
            root = Path(temp)
            tracker.record(root, fixture, self.forecast("pre"))
            self.assertEqual([m for m, _ in tracker.pending(root)], ["cricket-1"])
            late = self.forecast("in")
            late["teams"][0]["win"] = 0.99                    # a later look must not overwrite the pre-match forecast
            tracker.record(root, fixture, late)
            result = tracker.grade(root, "cricket-1", intel)
            self.assertTrue(result["winner_pick"]["correct"])
            self.assertEqual(result["winner_pick"]["probability"], 0.6)
            self.assertEqual((result["first_innings"]["actual"], result["first_innings"]["in_range"]), (171, True))
            picks = {(p["team"], p["kind"]): p["correct"] for p in result["picks"]}
            self.assertEqual(picks, {("Alpha", "top_batter"): True, ("Alpha", "top_bowler"): True,
                                     ("Beta", "top_batter"): False})
            summary = tracker.track_record(root)["summary"]
            self.assertEqual((summary["winner"], summary["graded"]), ({"n": 1, "correct": 1}, 1))

    def test_checkpoint_freezes_the_pre_match_forecast_even_when_the_xi_changes(self):
        fixture = {"id": "cricket-1", "start": "2026-11-11T10:00:00Z"}
        with TemporaryDirectory() as temp, patch.object(tracker, "_now") as now:
            root = Path(temp)
            now.return_value = "2026-11-11T09:30:00+00:00"
            self.assertFalse(tracker.record(root, fixture, self.forecast("pre"))["pre"]["at_checkpoint"])
            now.return_value = "2026-11-11T09:45:03+00:00"
            forecast = self.forecast("pre")
            forecast["teams"][0]["win"] = 0.7
            forecast["teams"][0]["reasons"] = ["Confirmed opener"]
            saved = tracker.record(root, fixture, forecast)["pre"]
            self.assertTrue(saved["at_checkpoint"])
            now.return_value = "2026-11-11T09:57:00+00:00"
            self.assertEqual(tracker.record(root, fixture, self.forecast("pre"))["pre"], saved)
            now.return_value = "2026-11-11T10:01:00+00:00"
            self.assertEqual(tracker.record(root, fixture, self.forecast("in"))["pre"], saved)
            stale = tracker.record(root, {**fixture, "id": "stale"}, self.forecast("pre"))["pre"]
            self.assertFalse(stale["saved_before_start"])

    def test_forecast_first_made_after_the_start_is_not_counted(self):
        fixture = {"id": "cricket-9", "team": "Alpha", "opponent": "Beta", "start": "", "espn": {"event": "3"}}
        with TemporaryDirectory() as temp:
            root = Path(temp)
            tracker.record(root, fixture, self.forecast("in"))
            tracker.grade(root, "cricket-9", {"ok": True, "state": "post", "status_text": "", "teams": [
                {"name": "Alpha", "winner": True, "innings": [], "xi": []}, {"name": "Beta", "winner": False, "innings": [], "xi": []}]})
            self.assertEqual(tracker.track_record(root)["summary"]["graded"], 0)

    def test_cricket_keeps_one_observation_per_over_and_ignores_older_updates(self):
        live = {"innings": 1, "batting": "Alpha", "batting_index": 0, "win": [0.6, 0.4],
                "projected": {"mean": 120}, "score": "live", "wickets": 0}
        timeline = []
        for balls, runs in ((4, 5), (6, 9), (8, 12), (12, 15), (9, 13)):
            tracker._cricket_update(timeline, dict(live, balls=balls, runs=runs), "2026-11-11T10:01:00+00:00")
        self.assertEqual([row["position"] for row in timeline], [[1, 9, 0, 6], [1, 15, 0, 12]])
        self.assertIn("This over · 6 runs", timeline[-1]["note"])
        legacy_partial = {**timeline[0], "position": [1, 5, 0, 4]}
        self.assertEqual(tracker.cricket_overs([legacy_partial, *timeline]), timeline)

    def test_f1_forecast_counts_only_in_its_sport_and_can_be_graded(self):
        race = {"race_id": "test-gp", "season": 2026, "round": 22, "name": "Test GP",
                "start": "2026-11-11T10:00:00Z", "stage": "post_qualifying", "completed": False,
                "drivers": [{"driver": "Example Driver", "win": 0.55}]}
        with TemporaryDirectory() as temp, patch.object(tracker, "_now", return_value="2026-11-11T09:45:00+00:00"):
            root = Path(temp)
            tracker.record_race(root, race)
            tracker.record_race(root, {**race, "stage": "pre_weekend"})
            tracker.grade_race(root, "f1-test-gp", "Example Driver")
            groups = tracker.track_record(root)["sports"]
            self.assertEqual(groups["f1"]["summary"]["winner"], {"n": 1, "correct": 1})
            self.assertEqual(groups["f1"]["matches"][0]["stage"], "post_qualifying")
            self.assertEqual([groups[s]["summary"]["saved"] for s in ("cricket", "tennis")], [0, 0])


if __name__ == "__main__":
    unittest.main()
