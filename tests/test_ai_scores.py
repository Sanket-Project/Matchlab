"""Last-resort AI web search for fixtures and scores: when it runs, what it may change, and what it refuses."""
import io
import json
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import fetch_today_matches as feed
from matchlab import budget, tracker

TODAY = date(2026, 11, 11)
NOW = datetime(2026, 11, 11, 12)


def espn_cricket(home, away, home_score, away_score, state="in", when="2026-11-11T09:00Z"):
    return {"sports": [{"leagues": [{"name": "Series", "events": [{
        "id": "77", "date": when, "fullStatus": {"type": {"state": state}}, "summary": "Live", "class": {"generalClassCard": "T20"},
        "competitors": [{"homeAway": "home", "displayName": home, "score": home_score},
                        {"homeAway": "away", "displayName": away, "score": away_score}]}]}]}]}


SOURCES = [{"title": "espncricinfo.com", "uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"}]


class AiNeededTests(unittest.TestCase):
    def test_runs_only_after_a_limit_or_when_every_source_failed(self):
        ok = {"sport": "cricket", "name": "ESPN Cricket", "ok": True}
        self.assertFalse(feed.ai_needed("cricket", [ok]))
        self.assertTrue(feed.ai_needed("cricket", [ok, {"sport": "cricket", "name": "CricketData.org", "ok": True, "limited": True}]))
        self.assertFalse(feed.ai_needed("cricket", [ok, {"sport": "cricket", "name": "CricketData.org", "ok": False}]))
        self.assertTrue(feed.ai_needed("tennis", [{"sport": "tennis", "name": "ATP", "ok": False}, {"sport": "tennis", "name": "WTA", "ok": False}]))
        self.assertFalse(feed.ai_needed("f1", []))


class FallbackTests(unittest.TestCase):
    def refresh(self, temp, lookup, espn, key="gem-key", spent=True):
        key_file = Path(temp) / "cricketdata.key"
        key_file.write_text("cricket-key", encoding="utf-8")
        if spent:   # today's CricketData budget is used up
            budget.sync(Path(temp), "cricketdata", 100, 100)
        with (patch.object(feed, "ROOT", Path(temp)), patch.object(feed, "CRICKETDATA_KEY_FILE", key_file),
              patch.object(feed, "OUTPUT_FILE", Path(temp) / "today_matches.json"), patch.object(feed, "SCOREBOARDS", []),
              patch.object(feed, "get_json", return_value=espn), patch.object(feed, "_gemini_key", return_value=key),
              patch.object(feed.fetch_ai_scores, "lookup", side_effect=lookup) as call):
            return feed.fetch_matches(NOW), call

    def test_limit_reached_adds_missing_fixtures_and_fills_only_blank_scores(self):
        espn = espn_cricket("India", "Australia", "", "")   # live, but ESPN has no score yet
        answer = {"ok": True, "sources": SOURCES, "model": "gemini-x", "matches": [
            {"team": "Australia", "opponent": "India", "state": "in", "start_utc": "2026-11-11T09:00:00Z",
             "team_score": "120/3 (15 ov)", "opponent_score": "", "tournament": "Series"},
            {"team": "Nepal", "opponent": "Oman", "state": "post", "start_utc": "2026-11-11T05:00:00Z",
             "team_score": "150/7", "opponent_score": "151/4", "format": "T20"},
            {"team": "Invented", "opponent": "", "state": "in"},                       # one side missing: dropped
            {"team": "Old", "opponent": "Match", "state": "post", "start_utc": "2026-10-01T05:00:00Z"},   # not today
            {"team": "A", "opponent": "B", "state": "maybe", "start_utc": "2026-11-11T05:00:00Z"}]}    # bad state
        with TemporaryDirectory() as temp:
            payload, call = self.refresh(temp, lambda *a, **k: answer, espn)
            used = budget.status(Path(temp))["gemini_search"]["used"]
            payload2, call2 = self.refresh(temp, lambda *a, **k: answer, espn, spent=False)   # cached: no second request
        call.assert_called_once()
        call2.assert_not_called()
        self.assertEqual(used, 1)
        cricket = {(m["team"], m["opponent"]): m for m in payload["sports"]["cricket"]}
        self.assertEqual(set(cricket), {("India", "Australia"), ("Nepal", "Oman")})
        espn_match = cricket[("India", "Australia")]
        self.assertTrue(espn_match["id"].startswith("cricket-espn") or "ai-" not in espn_match["id"])
        self.assertEqual((espn_match["team_score"], espn_match["opponent_score"]), ("120/3 (15 ov)", ""))
        self.assertIn("score_source", espn_match)
        added = cricket[("Nepal", "Oman")]
        self.assertTrue(added["id"].startswith("cricket-ai-g"))
        self.assertEqual(added["ai_source"]["sources"], SOURCES)
        self.assertEqual(added["source_url"], SOURCES[0]["uri"])
        ai_source = next(s for s in payload["sources"] if s["name"] == feed.AI_SOURCE)
        self.assertEqual((ai_source["ok"], ai_source["matches"]), (True, 2))
        self.assertNotIn(feed.AI_SOURCE, payload["failed_sources"])

    def test_feed_scores_are_never_replaced(self):
        espn = espn_cricket("India", "Australia", "160/2", "201/8")
        answer = {"ok": True, "sources": SOURCES, "matches": [
            {"team": "India", "opponent": "Australia", "state": "in", "start_utc": "2026-11-11T09:00:00Z",
             "team_score": "999/0", "opponent_score": "1/9"}]}
        with TemporaryDirectory() as temp:
            payload, _ = self.refresh(temp, lambda *a, **k: answer, espn)
        (match,) = payload["sports"]["cricket"]
        self.assertEqual((match["team_score"], match["opponent_score"]), ("160/2", "201/8"))
        self.assertNotIn("score_source", match)

    def test_key_without_web_search_is_quiet_and_not_retried_for_an_hour(self):
        blocked = {"ok": False, "blocked": True, "error": "Gemini web search is not available on this key."}
        espn = espn_cricket("India", "Australia", "160/2", "201/8")
        with TemporaryDirectory() as temp:
            payload, call = self.refresh(temp, lambda *a, **k: blocked, espn)
            _, again = self.refresh(temp, lambda *a, **k: blocked, espn)
        call.assert_called_once()
        again.assert_not_called()
        source = next(s for s in payload["sources"] if s["name"] == feed.AI_SOURCE)
        self.assertIsNone(source["error"])           # not shown as a feed failure on the match list
        self.assertIn("not available", source["note"])   # explained in Settings
        self.assertEqual(payload["failed_sources"], [])
        self.assertEqual(len(payload["sports"]["cricket"]), 1)

    def test_no_gemini_key_or_budget_left_means_no_request(self):
        espn = espn_cricket("India", "Australia", "160/2", "201/8")
        with TemporaryDirectory() as temp:
            payload, call = self.refresh(temp, None, espn, key="")
        call.assert_not_called()
        self.assertFalse(any(s["name"] == feed.AI_SOURCE for s in payload["sources"]))
        with TemporaryDirectory() as temp:
            budget.sync(Path(temp), "gemini_search", 100, 100)
            payload, call = self.refresh(temp, None, espn)
        call.assert_not_called()

    def test_provider_reported_limit_counts_as_reached(self):
        with TemporaryDirectory() as temp:
            key_file = Path(temp) / "cricketdata.key"
            key_file.write_text("k", encoding="utf-8")
            reply = {"status": "failure", "reason": "Daily hits limit exceeded"}
            with (patch.object(feed, "ROOT", Path(temp)), patch.object(feed, "CRICKETDATA_KEY_FILE", key_file),
                  patch.object(feed, "get_json", side_effect=[reply, {"sports": []}])):
                _, sources = feed.fetch_cricket(TODAY)
        self.assertTrue(sources[0]["limited"])


class LookupTests(unittest.TestCase):
    @staticmethod
    def opener(reply=None, error=None):
        http = MagicMock()
        if error:
            http.open.side_effect = error
        else:
            http.open.return_value = io.BytesIO(json.dumps(reply).encode())
        return http

    def test_answers_without_cited_web_sources_are_discarded(self):
        reply = {"candidates": [{"content": {"parts": [{"text": '{"matches": [{"team": "A", "opponent": "B"}]}'}]}}]}
        result = feed.fetch_ai_scores.lookup("k", "cricket", "2026-11-11", opener=self.opener(reply))
        self.assertFalse(result["ok"])
        self.assertIn("citing", result["error"])

    def test_grounded_answer_is_read_and_request_uses_search_tool(self):
        reply = {"candidates": [{"content": {"parts": [{"text": '```json\n{"matches": [{"team": "A", "opponent": "B"}]}\n```'}]},
                                 "groundingMetadata": {"groundingChunks": [{"web": {"uri": SOURCES[0]["uri"], "title": "espncricinfo.com"}},
                                                                           {"web": {"uri": "http://insecure.example", "title": "x"}}]}}]}
        http = self.opener(reply)
        result = feed.fetch_ai_scores.lookup("secret", "cricket", "2026-11-11", [{"team": "India", "opponent": "Australia"}], opener=http)
        self.assertTrue(result["ok"])
        self.assertEqual(result["sources"], SOURCES)
        self.assertEqual(result["matches"], [{"team": "A", "opponent": "B"}])
        request = http.open.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body["tools"], [{"google_search": {}}])
        self.assertIn("India v Australia", body["contents"][0]["parts"][0]["text"])
        self.assertNotIn(b"secret", request.data)
        self.assertNotIn("secret", request.full_url)

    def test_free_tier_without_search_reports_blocked(self):
        result = feed.fetch_ai_scores.lookup("k", "tennis", "2026-11-11", opener=self.opener(error=HTTPError("", 429, "quota", {}, None)))
        self.assertEqual((result["ok"], result["blocked"]), (False, True))
        self.assertIn("billing", result["error"])


class TrackRecordTests(unittest.TestCase):
    def test_ai_only_fixtures_are_never_saved(self):
        with TemporaryDirectory() as temp:
            self.assertIsNone(tracker.record(Path(temp), {"id": "cricket-ai-gabc123"}, {"supported": True, "intel": {"state": "pre"}}))
            self.assertFalse((Path(temp) / "data/local/predictions.json").exists())


if __name__ == "__main__":
    unittest.main()
