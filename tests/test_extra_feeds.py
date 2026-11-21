"""Open-Meteo weather notes, OpenF1 weekend shaping, AcesAPI matching and monthly credit metering."""
import tempfile
import unittest
from datetime import datetime, timezone

from matchlab import acesapi, budget, conditions, openf1

START = datetime(2026, 11, 21, 14, 0, tzinfo=timezone.utc)


def forecast(rain=0, temp=20, dew=10, humidity=50, wind=5):
    times = [f"2026-11-21T{h:02d}:00" for h in range(10, 20)]
    n = len(times)
    return {"hourly": {"time": times, "temperature_2m": [temp] * n, "dew_point_2m": [dew] * n,
                       "relative_humidity_2m": [humidity] * n, "precipitation_probability": [rain] * n,
                       "precipitation": [0] * n, "wind_speed_10m": [wind] * n, "cloud_cover": [10] * n}}


class Conditions(unittest.TestCase):
    def test_place_candidates_prefer_the_town(self):
        self.assertEqual(conditions.place_candidates("Inalpi Arena, Turin, Italy")[0], "Turin")
        self.assertEqual(conditions.place_candidates("Entebbe Cricket Oval, Entebbe"), ["Entebbe", "Entebbe Cricket Oval"])
        self.assertEqual(conditions.place_candidates(""), [])

    def test_window_and_notes(self):
        out = conditions.summarize(forecast(rain=70), {"name": "X"}, START, "cricket")
        self.assertTrue(out["ok"])
        self.assertEqual([r["time"][11:13] for r in out["hours"]], ["13", "14", "15", "16", "17", "18"])
        self.assertIn("Overs could be lost", out["notes"][0])
        self.assertFalse(out["model_uses"])

    def test_dew_only_for_cricket(self):
        self.assertTrue(any("dew" in n for n in conditions.notes(conditions.hours(forecast(temp=20, dew=18), START), "cricket")))
        self.assertFalse(any("dew" in n for n in conditions.notes(conditions.hours(forecast(temp=20, dew=18), START), "tennis")))

    def test_calm_weather_says_so(self):
        self.assertEqual(conditions.notes(conditions.hours(forecast(), START), "f1"), ["No rain, wind or heat of note is forecast around the start."])

    def test_no_hours_is_unavailable(self):
        self.assertFalse(conditions.summarize({"hourly": {"time": []}}, {}, START, "f1")["ok"])


class OpenF1(unittest.TestCase):
    SESSIONS = [
        {"session_key": 1, "session_name": "Practice 1", "session_type": "Practice", "meeting_key": 9, "location": "Las Vegas",
         "date_start": "2026-11-20T00:30:00+00:00", "date_end": "2026-11-20T01:30:00+00:00"},
        {"session_key": 2, "session_name": "Qualifying", "session_type": "Qualifying", "meeting_key": 9, "location": "Las Vegas",
         "date_start": "2026-11-21T04:00:00+00:00", "date_end": "2026-11-21T05:00:00+00:00"},
        {"session_key": 3, "session_name": "Race", "session_type": "Race", "meeting_key": 9, "location": "Las Vegas",
         "date_start": "2026-11-22T04:00:00+00:00", "date_end": "2026-11-22T06:00:00+00:00"},
        {"session_key": 4, "session_name": "Race", "session_type": "Race", "meeting_key": 8,
         "date_start": "2026-11-08T17:00:00+00:00", "date_end": "2026-11-08T19:00:00+00:00"},
    ]

    def test_weekend_keeps_one_meeting_in_order(self):
        weekend = openf1.weekend(self.SESSIONS, datetime(2026, 11, 22, 4, tzinfo=timezone.utc))
        self.assertEqual([s["session_key"] for s in weekend], [1, 2, 3])
        self.assertEqual(openf1.weekend(self.SESSIONS, datetime(2026, 12, 1, tzinfo=timezone.utc)), [])

    def test_qualifying_best_time_is_last_part_reached(self):
        self.assertEqual(openf1.best_time([94.6, 94.3, None]), 94.3)
        self.assertEqual(openf1.best_time(93.893), 93.893)
        self.assertIsNone(openf1.best_time([None, None]))
        self.assertEqual(openf1.lap_text(93.893), "1:33.893")

    def test_summary_lists_finished_sessions_only(self):
        weekend = openf1.weekend(self.SESSIONS, datetime(2026, 11, 22, 4, tzinfo=timezone.utc))
        details = {2: {"results": [{"position": 2, "driver_number": 3, "duration": [95.0, 94.2, 94.15]},
                                   {"position": 1, "driver_number": 12, "duration": [94.7, 95.1, 93.893], "number_of_laps": 26}],
                       "weather": [{"date": "2026-11-21T04:10:00", "air_temperature": 12.5, "rainfall": 0},
                                   {"date": "2026-11-21T04:50:00", "air_temperature": 12.0, "track_temperature": 15, "rainfall": 1}]}}
        drivers = [{"driver_number": 12, "first_name": "Kimi", "last_name": "Antonelli", "team_name": "Mercedes"}]
        out = openf1.summary(weekend, details, drivers, datetime(2026, 11, 21, 12, tzinfo=timezone.utc))
        self.assertEqual([s["state"] for s in out["sessions"]], ["done", "done", "pre"])
        quali = out["sessions"][1]
        self.assertEqual(quali["top"][0], {"position": 1, "name": "Kimi Antonelli", "team": "Mercedes", "code": "", "time": "1:33.893", "laps": 26, "out": False})
        self.assertEqual(quali["top"][1]["name"], "Car 3")
        self.assertEqual(quali["weather"]["air"], 12.0)
        self.assertTrue(quali["weather"]["rain"])
        live = openf1.summary(weekend, details, drivers, datetime(2026, 11, 21, 4, 30, tzinfo=timezone.utc))
        self.assertEqual(live["sessions"][1]["state"], "live")
        self.assertNotIn("top", live["sessions"][1])


class AcesApi(unittest.TestCase):
    def test_pick_player(self):
        hits = [{"player_id": "1", "name": "Carlos Alcaraz"}, {"player_id": "2", "name": "Carlos Alcaraz Jr"}]
        self.assertEqual(acesapi.pick_player(hits, "Carlos Alcaraz")["player_id"], "1")
        self.assertEqual(acesapi.pick_player([{"player_id": "7", "name": "Joao Fonseca"}], "João Fonseca")["player_id"], "7")
        self.assertIsNone(acesapi.pick_player([{"player_id": "3", "name": "A Zverev"}, {"player_id": "4", "name": "A Zverev"}], "Alexander Zverev"))
        self.assertIsNone(acesapi.pick_player([{"player_id": "5", "name": "Mischa Zverev"}], "Alexander Zverev"))

    def test_surface_and_search(self):
        self.assertEqual(acesapi.surface("Hard"), "hard")
        self.assertEqual(acesapi.surface("Clay court"), "clay")
        self.assertIsNone(acesapi.surface("ice"))
        self.assertEqual(acesapi.search_term("Félix Auger-Aliassime"), "aliassime")

    def test_shape(self):
        players = [{"player_id": "3623", "current_rank": 2}, {"player_id": "3782", "current_rank": 1}]
        ratings = {"ratings": [{"player_id": "3782", "rating": 2247, "rank": 1, "surface_matches": 121},
                               {"player_id": "3623", "rating": 2247, "rank": 2, "surface_matches": 90}]}
        h2h = {"summary": {"matches": 17, "wins": {"3623": 7, "3782": 10}, "by_surface": {"clay": {"3623": 2, "3782": 3}}},
               "matches": [{"starts_at": "2026-04-12T13:10:00Z", "round": "Final", "surface": "clay", "score": "7-6 6-3", "winner_id": "3623"}]}
        out = acesapi.shape(["Jannik Sinner", "Carlos Alcaraz"], players, h2h, ratings, "clay", "now")
        self.assertEqual(out["elo_win"], 0.5)
        self.assertEqual(out["h2h"]["wins"], [7, 10])
        self.assertEqual(out["h2h"]["surface_wins"], [2, 3])
        self.assertEqual(out["h2h"]["last"][0]["winner"], "Jannik Sinner")
        self.assertEqual(out["notes"], [])
        missing = acesapi.shape(["A", "B"], [players[0], None], None, ratings, "clay", "now")
        self.assertIsNone(missing["h2h"])
        self.assertIsNone(missing["elo_win"])
        self.assertIn("could not match B", missing["notes"][0])


class EnvFile(unittest.TestCase):
    def test_reads_keys_from_env_file(self):
        import os
        from pathlib import Path
        from unittest import mock
        from matchlab.openrouter_key import AcesApiKey, env_file_value
        with tempfile.TemporaryDirectory() as root:
            env = Path(root) / ".env"
            env.write_text('# keys\nexport OTHER=1\nACESAPI_KEY = "abc123def456ghi789"  \nEMPTY=\nNOTE=plain value # comment\n', encoding="utf-8")
            self.assertEqual(env_file_value("ACESAPI_KEY", env), "abc123def456ghi789")
            self.assertEqual(env_file_value("OTHER", env), "1")
            self.assertEqual(env_file_value("NOTE", env), "plain value")
            self.assertEqual(env_file_value("EMPTY", env), "")
            self.assertEqual(env_file_value("MISSING", env), "")
            self.assertEqual(env_file_value("X", Path(root) / "none"), "")
            with mock.patch.dict(os.environ, {"ACESAPI_KEY": ""}):
                key = AcesApiKey(Path(root) / "no.dpapi", env)
                self.assertEqual((key.status(), key.get()), ("file", "abc123def456ghi789"))
                self.assertEqual(AcesApiKey(Path(root) / "no.dpapi", Path(root) / "none").status(), "missing")
            with mock.patch.dict(os.environ, {"ACESAPI_KEY": "fromenvironment123"}):
                key = AcesApiKey(Path(root) / "no.dpapi", env)
                self.assertEqual((key.status(), key.get()), ("environment", "fromenvironment123"))

    def test_multi_api_key_registry(self):
        import os
        from pathlib import Path
        from unittest import mock
        from matchlab.openrouter_key import KEY_CLASSES, get_api_key
        with tempfile.TemporaryDirectory() as root:
            env = Path(root) / ".env"
            env.write_text(
                'GEMINI_API_KEY=AIzaSyTest1234567890\n'
                'LIVE_TENNIS_API_KEY=twjp_test_key_12345\n'
                'THE_ODDS_API_KEY=odds_test_key_abcdef\n',
                encoding="utf-8"
            )
            with mock.patch("matchlab.openrouter_key.ENV_FILE", env):
                self.assertEqual(get_api_key("GEMINI_API_KEY"), "AIzaSyTest1234567890")
                self.assertEqual(get_api_key("LIVE_TENNIS_API_KEY"), "twjp_test_key_12345")
                self.assertEqual(get_api_key("THE_ODDS_API_KEY"), "odds_test_key_abcdef")
                self.assertEqual(get_api_key("NOT_SET", "fallback"), "fallback")

                gemini = KEY_CLASSES["gemini"](Path(root) / "gemini.dpapi", env)
                self.assertEqual(gemini.get(), "AIzaSyTest1234567890")
                self.assertEqual(gemini.status(), "file")

                live_tennis = KEY_CLASSES["live_tennis"](Path(root) / "tennis.dpapi", env)
                self.assertEqual(live_tennis.get(), "twjp_test_key_12345")
                self.assertEqual(live_tennis.status(), "file")


class Credits(unittest.TestCase):
    def test_monthly_credits_with_cost_and_reserve(self):
        with tempfile.TemporaryDirectory() as root:
            spent = 0
            while budget.spend(root, "acesapi", "check", cost=acesapi.CREDITS):
                spent += acesapi.CREDITS
            self.assertEqual(spent, 476)          # 500 minus a 20-credit reserve, in 7-credit steps
            status = budget.status(root)["acesapi"]
            self.assertEqual((status["used"], status["period"], len(status["day"])), (476, "month", 7))
            self.assertTrue(budget.spend(root, "acesapi", "check", priority=True, cost=7))
            self.assertEqual(budget.status(root)["cricketdata"]["period"], "day")


if __name__ == "__main__":
    unittest.main()
