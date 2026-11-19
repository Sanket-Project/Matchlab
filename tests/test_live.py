"""Today's-schedule parsing and linking, plus imported match context. No network use."""
import csv
import json
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import fetch_today_matches as feed
from matchlab.live import annotate, name_key


def local_noon_utc(day):
    """UTC timestamp string for 12:00 local time on the given local day."""
    local = datetime(day.year, day.month, day.day, 12).astimezone()
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def team_event(eid, when, state, home="Arsenal", away="Chelsea", description="Scheduled"):
    return {"id": eid, "date": when, "status": {"type": {"state": state, "description": description, "shortDetail": "63'"}},
            "competitions": [{"venue": {"fullName": "Ground"}, "competitors": [
                {"homeAway": "away", "team": {"displayName": away}, "score": "1"},
                {"homeAway": "home", "team": {"displayName": home}, "score": "2"}]}]}


class FeedParsingTests(unittest.TestCase):
    today = date(2026, 11, 11)

    def test_only_todays_or_live_fixtures_are_kept(self):
        board = {"leagues": [{"name": "Premier League"}], "events": [
            team_event("1", local_noon_utc(self.today), "pre"),
            # A finished fixture from an earlier round must never appear as "today".
            team_event("2", local_noon_utc(date(2026, 11, 7)), "post", description="Full Time"),
            # Started on an earlier day but still in progress: keep.
            team_event("3", local_noon_utc(date(2026, 11, 10)), "in"),
            # Far beyond the look-ahead window: never listed.
            team_event("4", local_noon_utc(date(2031, 1, 1)), "pre")]}
        found = feed.parse_team_board("football", "fallback", board, self.today)
        self.assertEqual({m["id"] for m in found}, {"football-1", "football-3"})
        scheduled = next(m for m in found if m["id"] == "football-1")
        self.assertEqual((scheduled["team"], scheduled["opponent"]), ("Arsenal", "Chelsea"))  # home side first
        self.assertEqual((scheduled["team_score"], scheduled["tournament"]), ("", "Premier League"))
        live = next(m for m in found if m["id"] == "football-3")
        self.assertEqual((live["state"], live["team_score"], live["opponent_score"]), ("in", "2", "1"))

    def test_tennis_singles_with_named_players_only(self):
        when = local_noon_utc(self.today)
        comp = lambda cid, names: {"id": cid, "date": when, "status": {"type": {"state": "pre", "description": "Scheduled"}},
                                   "round": {"displayName": "Round 2"}, "venue": {"fullName": "Stockholm", "court": "Court 1"},
                                   "competitors": [{"athlete": {"displayName": n}} if n else {} for n in names]}
        board = {"events": [{"name": "Open", "groupings": [
            {"grouping": {"displayName": "Men's Singles"}, "competitions": [comp("a", ["A One", "B Two"]), comp("b", ["A One", None])]},
            {"grouping": {"displayName": "Men's Doubles"}, "competitions": [comp("c", ["X", "Y"])]}]}]}
        found = feed.parse_tennis("tennis", "ATP", board, self.today)
        self.assertEqual([m["id"] for m in found], ["tennis-a"])
        self.assertEqual((found[0]["detail"], found[0]["venue"]), ("Round 2", "Court 1, Stockholm"))

    def test_cricket_header_layout(self):
        data = {"sports": [{"leagues": [{"name": "Series ", "events": [
            {"id": "9", "date": "2026-11-09T04:30:00Z", "status": "in", "summary": "Day 3", "location": "Oval",
             "fullStatus": {"type": {"state": "in"}}, "class": {"generalClassCard": "Test"},
             "competitors": [{"homeAway": "home", "displayName": "Pakistan", "score": "434/9d"},
                             {"homeAway": "away", "displayName": "Sri Lanka", "score": "188/4"}]}]}]}]}
        found = feed.parse_cricket(data, self.today)
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0]["tournament"], found[0]["detail"], found[0]["team_score"]), ("Series", "Test", "434/9d"))

    def test_schedule_refresh_uses_cricketdata_key_and_keeps_only_today_or_live(self):
        key = "sample+key"
        live = {"id": "live", "dateTimeGMT": "2026-11-10T06:00:00", "teams": ["India", "Australia"],
                "name": "India vs Australia, 1st Test", "matchType": "test", "matchStarted": True,
                "matchEnded": False, "status": "Day 2", "score": [
                    {"inning": "Australia Inning 1", "r": 221, "w": 10},
                    {"inning": "India Inning 1", "r": 319, "w": 10},
                    {"inning": "Australia Inning 2", "r": 0, "w": 0}]}
        finished = dict(live, id="finished", matchEnded=True, dateTimeGMT=local_noon_utc(self.today))
        older = dict(live, id="older", matchEnded=True)
        with TemporaryDirectory() as temp:
            key_file = Path(temp) / "cricketdata.key"
            key_file.write_text(f"{key}\n", encoding="utf-8-sig")
            answers = lambda url: ({"sports": []} if url == feed.CRICKET_URL else
                                   {"status": "success", "apikey": key, "info": {"hitsToday": 7, "hitsLimit": 100},
                                    "data": [older, finished, live]})
            with (patch.object(feed, "CRICKETDATA_KEY_FILE", key_file),
                  patch.object(feed, "ROOT", Path(temp)),   # request ledger and cache stay out of the real project
                  patch.object(feed, "OUTPUT_FILE", Path(temp) / "today_matches.json"),
                  patch.object(feed, "SCOREBOARDS", []),
                  patch.object(feed, "get_json", side_effect=answers) as request):
                payload = feed.fetch_matches(datetime(2026, 11, 11, 12))
                saved = feed.OUTPUT_FILE.read_text(encoding="utf-8")
                feed.fetch_matches(datetime(2026, 11, 11, 12))   # second refresh is served from the cache
                used = feed.budget.status(Path(temp))["cricketdata"]["used"]
        metered = [call.args[0] for call in request.call_args_list if call.args[0] != feed.CRICKET_URL]
        self.assertEqual(len(metered), 1)
        self.assertEqual(used, 7)   # the provider's own count is adopted
        self.assertEqual(parse_qs(urlsplit(metered[0]).query), {"apikey": [key], "offset": ["0"]})
        matches = payload["sports"]["cricket"]
        self.assertEqual([(m["id"], m["state"]) for m in matches],
                         [("cricket-cricapi-live", "in"), ("cricket-cricapi-finished", "post")])
        self.assertEqual((matches[0]["team_score"], matches[0]["opponent_score"]), ("319/10", "221/10 & 0/0"))
        self.assertEqual(matches[0]["source_url"], feed.CRICKETDATA_SCOREBOARD)
        self.assertNotIn(key, saved)

    def test_cricketdata_failure_falls_back_without_leaking_the_key(self):
        key = "sample-key"
        with TemporaryDirectory() as temp:
            key_file = Path(temp) / "cricketdata.key"
            with patch.object(feed, "CRICKETDATA_KEY_FILE", key_file), patch.object(feed, "ROOT", Path(temp)):
                with patch.object(feed, "get_json", return_value={"sports": []}) as request:
                    _, sources = feed.fetch_cricket(self.today)
                request.assert_called_once_with(feed.CRICKET_URL)
                self.assertEqual([source["name"] for source in sources], ["ESPN Cricket"])
                key_file.write_text(key, encoding="utf-8")
                with patch.object(feed, "get_json", side_effect=[OSError(f"Request failed: {key}"), {"sports": []}]):
                    _, sources = feed.fetch_cricket(self.today)
        self.assertEqual([(source["name"], source["ok"]) for source in sources],
                         [("CricketData.org", False), ("ESPN Cricket", True)])
        self.assertNotIn(key, json.dumps(sources))

    def test_merged_cricket_fixture_uses_the_more_advanced_match_state(self):
        start = feed.parse_time(local_noon_utc(self.today))
        for cricketdata_state, espn_state, expected in (("pre", "in", "in"), ("in", "post", "post"),
                                                        ("in", "pre", "in")):
            with self.subTest(cricketdata=cricketdata_state, espn=espn_state):
                primary = feed.record("cricket", "cricapi-a", "Abu Dhabi T10", "UAE Bulls",
                                      "Royal Desert Champions", start, cricketdata_state,
                                      "CricketData status", "Ground", "", "0/0")
                primary["innings"] = [{"team": "Royal Desert Champions", "runs": 0}]
                espn = feed.record("cricket", "b", "Abu Dhabi T10", "Royal Desert Champions",
                                   "UAE Bulls", start, espn_state, "ESPN status", "Ground", "9/0", "")
                espn["espn"] = {"event": "b", "league": "c"}
                with (patch.object(feed, "fetch_cricketdata", return_value=[primary]),
                      patch.object(feed, "get_json", return_value={}),
                      patch.object(feed, "parse_cricket", return_value=[espn])):
                    matches, _ = feed.fetch_cricket(self.today)

                match, = matches
                self.assertEqual((match["id"], match["state"], match["espn"]),
                                 ("cricket-cricapi-a", expected, espn["espn"]))
                self.assertEqual(match["team_score"], "")
                if expected == espn_state:
                    self.assertEqual((match["status"], match["opponent_score"], match["innings"]),
                                     ("ESPN status", "9/0", []))
                else:
                    self.assertEqual((match["status"], match["opponent_score"], match["innings"]),
                                     ("CricketData status", "0/0", [{"team": "Royal Desert Champions", "runs": 0}]))


class LinkingTests(unittest.TestCase):
    def test_names_link_to_local_records_without_guessing(self):
        self.assertEqual(name_key("Brighton & Hove Albion FC"), name_key("Brighton and Hove Albion"))
        self.assertEqual(name_key("Taylor Fritz [126203]"), name_key("Taylor Fritz"))
        football = SimpleNamespace(teams=["Arsenal FC", "Chelsea FC"], matches=[{"date": "2024-05-19"}])
        baseball = SimpleNamespace(teams=["NYA", "BOS"], matches=[{"date": "2023-10-01"}])
        payload = {"sports": {
            "football": [{"team": "Arsenal", "opponent": "Chelsea"}, {"team": "Arsenal", "opponent": "Sunderland"}],
            "baseball": [{"team": "New York Yankees", "opponent": "Boston Red Sox"}],
            "rugby": [{"team": "Crusaders", "opponent": "Blues"}]}}
        annotate(payload, {"football": football, "baseball": baseball})
        ok, missing = payload["sports"]["football"]
        self.assertTrue(ok["analyzable"])
        self.assertEqual((ok["local_team"], ok["local_opponent"], ok["history_through"]), ("Arsenal FC", "Chelsea FC", "2024-05-19"))
        self.assertFalse(missing["analyzable"])
        self.assertIn("Sunderland", missing["unavailable_reason"])
        self.assertEqual(payload["sports"]["baseball"][0]["local_team"], "NYA")
        self.assertFalse(payload["sports"]["rugby"][0]["analyzable"])


@unittest.skipUnless((ROOT / "data/real/cricket/matches.csv").exists(), "One-time public data setup not installed")
class ImportedContextTests(unittest.TestCase):
    def rows(self, sport):
        with (ROOT / "data/real" / sport / "matches.csv").open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def test_cricket_matches_record_ground_and_toss(self):
        rows = self.rows("cricket")
        self.assertTrue(all(r["ground"] and r["city"] and r["toss_decision"] in ("bat", "field") for r in rows))
        self.assertTrue(all(r["toss_winner"] in (r["team"], r["opponent"]) for r in rows))
        self.assertTrue(all(r["venue"] == "neutral" for r in rows))  # home/away is not recorded by the source
        grounds = {r["ground"] for r in rows}
        self.assertNotIn("Feroz Shah Kotla", grounds)  # merged into its current name
        self.assertFalse({"Delhi Daredevils", "Kings XI Punjab", "Royal Challengers Bangalore"} & {r["team"] for r in rows})

    def test_tennis_matches_record_surface_and_rankings(self):
        rows = self.rows("tennis")
        self.assertTrue({"Hard", "Clay", "Grass"} <= {r["surface"] for r in rows})
        ranked = [r for r in rows if r["team_rank"] and r["opponent_rank"]]
        self.assertGreater(len(ranked), 0.95 * len(rows))
        self.assertTrue(all(int(r["team_rank"]) > 0 for r in ranked))


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless((ROOT / "data/real/cricket/matches.csv").exists(), "One-time public data setup not installed")
class BreakdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from matchlab.data import Dataset
        from matchlab.sports import SPORTS
        cls.cricket = Dataset(ROOT / "data/real/cricket", SPORTS["cricket"])
        cls.tennis = Dataset(ROOT / "data/real/tennis", SPORTS["tennis"])

    def test_pair_breakdown_by_ground_adds_up_and_respects_cutoff(self):
        from matchlab.splits import build
        cutoff = "2024-01-01"
        b = build(self.cricket, "Royal Challengers Bengaluru", "Mumbai Indians", "V Kohli", "JJ Bumrah", cutoff)
        rows = [r for r in self.cricket.interactions if r["player"] == "V Kohli" and r["opponent_player"] == "JJ Bumrah" and r["date"] < cutoff]
        self.assertTrue(rows)
        pair = b["pair"]
        self.assertEqual(pair["total"]["opportunities"], sum(r["opportunities"] for r in rows))
        self.assertEqual(pair["total"]["meetings"], len({r["match_id"] for r in rows}))
        grounds = pair["by_context"][0]
        self.assertEqual(grounds["label"], "Ground")
        for field in ("opportunities", "successes", "score", "meetings"):
            self.assertEqual(sum(g[field] for g in grounds["rows"]), pair["total"][field])
        self.assertTrue(all(g["last"] < cutoff for g in grounds["rows"]))
        later = build(self.cricket, "Royal Challengers Bengaluru", "Mumbai Indians", "V Kohli", "JJ Bumrah", "2026-11-11")
        self.assertGreater(later["pair"]["total"]["opportunities"], pair["total"]["opportunities"])
        # The reverse direction is the bowler batting against the batter: a separate record.
        self.assertNotEqual(b["pair_reverse"], b["pair"])

    def test_player_breakdown_by_opponent_and_ground(self):
        from matchlab.splits import player_splits
        s = player_splits(self.cricket, "V Kohli", "2026-11-11")
        self.assertEqual(sum(r["appearances"] for r in s["by_opponent"]), s["appearances"])
        self.assertEqual(sum(r["appearances"] for r in s["by_context"][0]["rows"]), s["appearances"])
        self.assertAlmostEqual(sum(r["total"] for r in s["by_opponent"]) / s["appearances"], s["average"])
        self.assertIsNone(player_splits(self.cricket, "V Kohli", "2000-01-01"))
        self.assertIsNone(player_splits(self.cricket, None, "2026-11-11"))

    def test_side_record_by_surface(self):
        from matchlab.splits import dimensions, side_splits
        self.assertEqual([d["label"] for d in dimensions(self.tennis)], ["Surface", "Tournament"])
        side = next(t for t in self.tennis.teams if t.startswith("Taylor Fritz"))
        s = side_splits(self.tennis, side, "2026-11-11")
        surface = s["by_context"][0]["rows"]
        self.assertTrue({"Hard", "Clay", "Grass"} >= {r["key"] for r in surface})
        for r in surface:
            self.assertEqual(r["wins"] + r["losses"] + r["draws"], r["matches"])
        self.assertLessEqual(sum(r["matches"] for r in surface), s["matches"])

    def test_sports_without_context_columns_report_none(self):
        from matchlab.engine import Engine, default_config
        a = Engine(default_config(), ROOT).analyze({"sport": "football", "team": None, "opponent": None} | {
            k: v for k, v in zip(("team", "opponent"), Engine(default_config(), ROOT).datasets["football"].teams[:2])} | {"cutoff": "2026-11-10"})
        self.assertEqual(a["breakdowns"]["sides"], [])
        self.assertTrue(a["breakdowns"]["player"]["by_opponent"])
        self.assertEqual(a["breakdowns"]["player"]["by_context"], [])
