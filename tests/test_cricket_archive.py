import json
import unittest

from matchlab.cricket_archive import cricsheet_match
from matchlab.cricket_audit import accuracy_stats, audit_records
from matchlab.cricket_correlations import pre_match_form
from matchlab.cricket_sources import crex_matches, legal_balls
from tools.build_cricket_coverage import retain_match_ids


class CricketArchiveTests(unittest.TestCase):
    def test_hundred_innings_keep_penalties_and_exclude_illegal_deliveries(self):
        document = {
            "info": {
                "dates": ["2025-07-01"], "teams": ["A", "B"], "gender": "female",
                "match_type": "T20", "team_type": "club", "overs": 20, "balls_per_over": 5,
                "event": {"name": "The Hundred Women's Competition"}, "outcome": {"winner": "A", "by": {"runs": 1}},
            },
            "innings": [{
                "team": "A", "penalty_runs": {"post": 5},
                "overs": [{"deliveries": [
                    {"runs": {"total": 1}, "extras": {"wides": 1}},
                    {"runs": {"total": 3}, "extras": {"noballs": 1}},
                    {"runs": {"total": 0}, "wickets": [{"kind": "retired hurt"}]},
                    {"runs": {"total": 0}, "wickets": [{"kind": "bowled"}]},
                ]}],
            }],
        }
        match, innings = cricsheet_match("123", document, "2026-11-11")
        self.assertEqual(match["format"], "100-ball")
        self.assertEqual(match["tournament"], "The Hundred Women's Competition")
        self.assertEqual(match["result_margin"], "1 run")
        self.assertEqual((innings[0]["runs"], innings[0]["wickets"], innings[0]["legal_balls"]), (9, 1, 2))
        self.assertEqual(legal_balls("9.4"), 58)
        self.assertEqual(legal_balls("9.6"), "")

    def test_archive_keeps_draws_and_super_over_results(self):
        info = {
            "dates": ["2025-01-01", "2025-01-04"], "teams": ["A", "B"], "match_type": "Test",
            "gender": "male", "team_type": "international", "outcome": {"result": "draw"},
        }
        draw, _ = cricsheet_match("1", {"info": info}, "")
        self.assertEqual((draw["result"], draw["end_date_local"]), ("draw", "2025-01-04"))
        info.update(match_type="T20", overs=20, outcome={"result": "tie", "eliminator": "B"})
        match, innings = cricsheet_match("2", {"info": info, "innings": [{"team": "B", "super_over": True}]}, "")
        self.assertEqual((match["winner"], match["result"], match["result_method"]), ("B", "win", "Super Over"))
        self.assertTrue(innings[0]["is_super_over"])

    def test_crex_fixture_id_survives_transition_from_schedule_to_result(self):
        fixture = {"id": 123, "nf": "A1", "sf": "X", "t1f": "A", "t2f": "B", "status": 0,
                   "ft": 2, "g": 0, "fo": "T20", "date": "11/12/2026", "t": 1794490200000}

        def parse(game):
            state = {
                "https://stats.crickapi.com/series/getMatchesForSeriesID": [game],
                "https://oc.crickapi.com/mapping/getHomeMapDataseriesmain": {
                    "s": [{"f_key": "X", "n": "Series 2026"}],
                    "t": [{"f_key": "A", "n": "Team A"}, {"f_key": "B", "n": "Team B"}],
                },
            }
            html = '<script id="app-root-state" type="application/json">' + json.dumps(state) + "</script>"
            return next(crex_matches(html, "https://example.com/series", "", "", "", "", ""))

        upcoming, _ = parse(fixture)
        finished, innings = parse(dict(fixture, mf="A1", status=2, w="B", bf="A", s1="99/4", o1="20.0",
                                       s2="100/1", o2="18.2", result="Team B won by 9 wickets"))
        self.assertEqual(upcoming["match_id"], finished["match_id"])
        self.assertEqual((upcoming["match_status"], upcoming["winner"]), ("scheduled", ""))
        self.assertEqual((finished["result"], finished["winner"]), ("win", "Team B"))
        self.assertEqual(innings[1]["legal_balls"], 110)

    def test_form_waits_until_the_day_after_the_result(self):
        def match(day, end, winner):
            return dict(match_id=day, start_date_local=day, end_date_local=end,
                        team_a="A", team_b="B", winner=winner, result="win")

        history = [match(f"2025-01-0{i}", f"2025-01-0{i}", "A") for i in range(1, 5)]
        history.extend([match("2025-01-05", "2025-01-08", "A"),
                        match("2025-01-08", "2025-01-10", "B"),
                        match("2025-01-09", "2025-01-10", "A")])
        self.assertEqual([(m["match_id"], hit) for m, hit in pre_match_form(history)], [("2025-01-09", 1)])

    def test_audit_counts_missing_separately_from_checked_values(self):
        match = dict(match_id="a", source="archive", source_url="https://example.com/archive", start_date_local="2026-01-01",
                     team_a="A", team_b="B", format="T20", team_category="male", result="win", winner="B")
        ref = dict(match, match_id="b", source="reference", source_url="https://example.com/reference",
                   league="League", season="2026", winner="A", result_margin="1 run")
        stats = accuracy_stats(list(audit_records([match], [], [(ref, [])])))
        self.assertEqual((stats["checked"], stats["correct"], stats["conflicts"], stats["missing"]), (2, 1, 1, 1))

    def test_snapshot_keeps_match_id_after_the_source_changes(self):
        prior = dict(match_id="crex-10", source="CREX", start_date_local="2026-01-01", team_a="A", team_b="B",
                     format="T20", team_category="male")
        for _ in range(2):
            updated = dict(prior, match_id="cricket-20", source="Cricsheet")
            innings = [{"match_id": updated["match_id"]}]
            retain_match_ids([(updated, innings)], [prior])
            self.assertEqual(updated["match_id"], "crex-10")
            self.assertEqual(innings[0]["match_id"], "crex-10")
            prior = updated


if __name__ == "__main__":
    unittest.main()
