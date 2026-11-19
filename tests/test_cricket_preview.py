"""Preview regression coverage for archive cutoffs and provider responses."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from zipfile import ZipFile

from matchlab.cricket_preview import _recent, build_context
from matchlab.cricket_projections import _scorecard, project
from tools.fetch_openrouter_preview import generate


class CricketPreviewTests(unittest.TestCase):
    def test_preview_only_uses_matches_completed_before_fixture(self):
        match = {"team": "Pakistan", "opponent": "Sri Lanka", "detail": "Test",
                 "start": "2026-11-09T04:30:00Z"}
        rows = [{"id": end, "end": end, "teams": ("pakistan", "sri lanka"),
                 "published": {"end": end}, "data_source": "Fixture archive"}
                for end in ("2026-11-08", "2026-11-09", "2026-11-10")]
        with (patch("matchlab.cricket_preview._snapshot", return_value=Path("snapshot")),
              patch("matchlab.cricket_preview._archive", return_value=rows),
              patch("matchlab.cricket_preview.forecast", return_value={}) as forecast):
            context = build_context(Path.cwd(), match, "5:54 PM")
        self.assertEqual(context["head_to_head"], [{"end": "2026-11-08"}])
        self.assertEqual(forecast.call_args.args[0], rows[:1])

    def test_provider_request_uses_free_routing_and_reports_selected_model(self):
        model = "google/gemma-4-31b-it:free"
        reply = {"model": model, "choices": [{"message": {"content": "Archive review."}}]}
        with patch("tools.fetch_openrouter_preview.build_opener") as opener:
            http = opener.return_value
            http.open.return_value = io.BytesIO(json.dumps(reply).encode())
            player = {"name": "A", "runs": 20, "wickets": 1, "matches": [{"runs": 12}, {"runs": 30}]}
            result = generate("test-secret", {"fixture": {"team": "Pakistan"},
                                             "projections": {"sides": [{"players": [player]}]}})
            request = http.open.call_args.args[0]
            self.assertEqual(request.get_header("Authorization"), "Bearer test-secret")
            self.assertNotIn(b"test-secret", request.data)
            body = json.loads(request.data)
            self.assertEqual(body["model"], "openrouter/free")
            self.assertEqual(body["provider"]["max_price"], {"prompt": 0, "completion": 0, "request": 0})
            self.assertEqual(body["plugins"], [{"id": "web", "enabled": False}])
            self.assertNotIn("models", body)
            self.assertNotIn("tools", body)
            projected = json.loads(body["messages"][1]["content"])["projections"]["sides"][0]["players"]
            self.assertEqual(projected, [{"name": "A", "runs": 20, "wickets": 1, "appearances": 2}])
            self.assertEqual(result, {"text": "Archive review.", "model": model, "web_sources": []})

    def test_provider_authentication_failure_is_actionable(self):
        with patch("tools.fetch_openrouter_preview.build_opener") as opener:
            opener.return_value.open.side_effect = HTTPError("", 401, "private upstream error", {}, None)
            result = generate("test-secret", {})
        self.assertIn("Data & models", result["error"])
        self.assertNotIn("private upstream error", result["error"])


class CricketProjectionTests(unittest.TestCase):
    @staticmethod
    def delivery(batter="A", bowler="B", runs=1, extra=None, wicket=None):
        return {"batter": batter, "bowler": bowler, "runs": {"batter": runs, "total": runs + bool(extra)},
                "extras": {extra: 1} if extra else {}, "wickets": [{"kind": wicket}] if wicket else []}

    def test_scorecard_excludes_non_bowler_wickets_and_counts_legal_balls(self):
        balls = [self.delivery(extra="wides", runs=0), self.delivery(wicket="run out"),
                 self.delivery(extra="noballs"), self.delivery(wicket="caught", runs=0),
                 self.delivery(runs=4)]
        innings = {"team": "Alpha", "overs": [{"deliveries": balls}], "penalty_runs": {"pre": 5, "post": 5}}
        doc = {"info": {"registry": {"people": {"A": "a", "B": "b"}}},
               "innings": [innings, {**innings, "super_over": True}]}
        scores, runs, wickets, _, _, _ = _scorecard(doc, [2, 3, 4], str.lower)
        self.assertEqual(scores["alpha"], [9, 18, 18])
        self.assertEqual(runs["a"], 6)
        self.assertEqual(wickets["b"], 1)

    def test_last_15_appearances_follow_player_identity_and_test_has_90_overs(self):
        history = []
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "matches.zip"
            with ZipFile(path, "w") as archive:
                for day in range(1, 19):
                    date = f"2026-01-{day:02d}"
                    batting = "Alpha" if day > 5 else "Gamma"
                    alias = "A" if day > 5 else "A Alias"
                    teams = [batting, "Beta"]
                    info = {"players": {batting: [alias], "Beta": ["B"]},
                            "registry": {"people": {alias: "a", "B": "b"}}}
                    innings = [{"team": batting, "overs": [{"deliveries": [self.delivery(batter=alias, runs=day)]}]},
                               {"team": "Beta", "overs": [{"deliveries": [self.delivery(batter="B", bowler=alias)]}]}]
                    archive.writestr(f"{day}.json", json.dumps({"info": info, "innings": innings}))
                    history.append({"id": str(day), "source_id": str(day), "data_source": "Cricsheet",
                                    "teams": tuple(name.lower() for name in teams),
                                    "start": date, "end": date, "published": {"teams": teams},
                                    "scores": {batting.lower(): day, "beta": 1}})
            teams = ("alpha", "beta")
            recent = _recent(history, teams)
            test = project(path, history, recent, teams, ((), ()), "2026-01-19", "Test", str.lower)
            t20 = project(path, history, recent, teams, ((), ()), "2026-01-19", "T20", str.lower)
        self.assertEqual(test["checkpoints"], list(range(5, 91, 5)))
        self.assertEqual(t20["checkpoints"], [5, 10, 15, 20])
        side = test["sides"][0]
        self.assertEqual(side["runs"], sorted(side["runs"]))
        player, = side["players"]
        self.assertEqual(len(player["matches"]), 15)
        self.assertEqual(player["matches"][0]["runs"], 18)
        self.assertEqual(player["matches"][-1]["team"], "Gamma")
        self.assertIsNotNone(player["runs"])
