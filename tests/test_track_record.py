"""Track record rules, the hosted read-only mirror, and the Gen-AI guards. No network use."""
import json
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from matchlab import ai_check, tracker, world  # noqa: E402


def entry(sport="cricket", wins=(0.6, 0.4), before=True, result=None, names=("Alpha", "Beta"), **extra):
    pre = {"sport": sport, "stage": "pre_toss", "saved_at": "2026-11-11T09:40:00+00:00", "saved_before_start": before,
           "teams": [{"name": n, "win": w} for n, w in zip(names, wins)]}
    item = {"fixture": {"id": "x", "team": names[0], "opponent": names[1], "start": "2026-11-11T10:00:00Z"}, "pre": pre, "timeline": []}
    if result is not None:
        item["result"] = {"saved_before_start": before, **result}
    item.update(extra)
    return item


def won(correct, **more):
    return {"winner": "Alpha", "winner_pick": {"pick": "Alpha", "probability": 0.6, "correct": correct}, **more}


class TrackRecordRules(unittest.TestCase):
    def write(self, root, data):
        path = Path(root) / tracker.FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        tracker._SUMMARY.clear()

    def test_post_start_forecasts_are_listed_labelled_and_never_counted(self):
        with TemporaryDirectory() as temp:
            self.write(temp, {"a": entry(result=won(True)), "b": entry(before=False, result=won(True)), "c": entry(before=False)})
            record = tracker.track_record(temp)
            s = record["sports"]["cricket"]["summary"]
            self.assertEqual((s["saved"], s["graded"], s["waiting"], s["after_start"]), (3, 1, 0, 2))
            self.assertEqual(s["winner"], {"n": 1, "correct": 1})
            listed = {row["id"]: row["saved_before_start"] for row in record["sports"]["cricket"]["matches"]}
            self.assertEqual(listed, {"a": True, "b": False, "c": False})

    def test_a_grade_that_disagrees_with_the_saved_flag_is_not_counted(self):
        with TemporaryDirectory() as temp:
            item = entry(result=won(True))
            item["result"]["saved_before_start"] = False
            self.write(temp, {"a": item})
            s = tracker.track_record(temp)["sports"]["cricket"]["summary"]
            self.assertEqual((s["graded"], s["winner"]["n"], s["after_start"]), (0, 0, 1))

    def test_ai_rate_and_model_rate_share_one_sample(self):
        ai = lambda correct: {"pick": "Alpha", "probability": 0.62, "shift": 2, "correct": correct}  # noqa: E731
        with TemporaryDirectory() as temp:
            self.write(temp, {"a": entry(result=won(True, ai_pick=ai(True))), "b": entry(result=won(False, ai_pick=ai(True))),
                              "c": entry(result=won(True)), "d": entry(result=won(False))})
            s = tracker.track_record(temp)["sports"]["cricket"]["summary"]
            self.assertEqual(s["winner"], {"n": 4, "correct": 2})
            self.assertEqual(s["ai_winner"], {"n": 2, "correct": 2})
            self.assertEqual(s["model_on_ai_sample"], {"n": 2, "correct": 1})     # same two forecasts, model alone

    def test_calibration_bins_have_fixed_edges_and_their_own_n(self):
        pairs = [(0.5, True), (0.599, False), (0.6, True), (0.75, True), (0.8, False), (0.9, True), (1.0, True)]
        bins = tracker.calibration_bins(pairs)
        self.assertEqual([(b["low"], b["high"]) for b in bins], [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0)])
        self.assertEqual([b["n"] for b in bins], [2, 1, 1, 1, 2])
        self.assertEqual([b["won"] for b in bins], [1, 1, 1, 0, 2])
        self.assertEqual(bins[0]["predicted"], round((0.5 + 0.599) / 2, 3))
        self.assertEqual(bins[3]["observed"], 0.0)
        self.assertEqual(sum(b["n"] for b in bins), len(pairs))
        self.assertTrue(all(b["observed"] is None for b in tracker.calibration_bins([])))

    def test_bins_use_only_counted_two_sided_graded_forecasts(self):
        with TemporaryDirectory() as temp:
            self.write(temp, {"a": entry(wins=(0.72, 0.28), result=won(True)), "b": entry(wins=(0.72, 0.28), before=False, result=won(False)),
                              "c": entry(wins=(0.72, 0.28)), "t": entry(sport="tennis", wins=(0.55, 0.45), result=won(False))})
            record = tracker.track_record(temp)
            self.assertEqual([b["n"] for b in record["sports"]["cricket"]["bins"]], [0, 0, 1, 0, 0])
            self.assertEqual([b["n"] for b in record["sports"]["tennis"]["bins"]], [1, 0, 0, 0, 0])

    def test_summary_is_cached_until_the_log_changes(self):
        fixture = {"id": "cricket-1", "team": "Alpha", "opponent": "Beta", "start": "2026-11-11T10:00:00Z"}
        forecast = {"supported": True, "sport": "tennis", "stage": "pre", "format": "Best of 3", "intel": {"state": "pre"},
                    "teams": [{"name": "Alpha", "win": 0.6}, {"name": "Beta", "win": 0.4}], "set_scores": [{"score": "2-0", "winner": "Alpha"}]}
        with TemporaryDirectory() as temp:
            tracker._SUMMARY.clear()
            first = tracker.track_record(temp)
            self.assertIs(tracker.track_record(temp), first)                  # same object: nothing recomputed
            tracker.record(temp, {**fixture, "id": "tennis-1"}, forecast)      # a write clears the cache
            self.assertEqual(tracker.track_record(temp)["sports"]["tennis"]["summary"]["saved"], 1)

    def test_table_is_paged_and_the_summary_still_covers_everything(self):
        with TemporaryDirectory() as temp:
            data = {f"m{i:02d}": entry(result=won(i % 2 == 0)) for i in range(60)}
            for i, item in enumerate(data.values()):
                item["fixture"]["start"] = f"2026-11-{1 + i // 3:02d}T{i % 3:02d}:00:00Z"
            self.write(temp, data)
            record = tracker.track_record(temp)
            group = record["sports"]["cricket"]
            self.assertEqual((len(group["matches"]), group["total"], group["summary"]["winner"]["n"]), (tracker.TABLE_ROWS, 60, 60))
            page = tracker.record_rows(temp, "cricket", offset=50)
            self.assertEqual((page["total"], len(page["matches"])), (60, 10))
            self.assertNotIn("matches", record)                                # no second copy of the rows

    def test_read_only_mode_never_writes(self):
        fixture = {"id": "tennis-1", "team": "Alpha", "opponent": "Beta", "start": "2026-11-11T10:00:00Z"}
        forecast = {"supported": True, "sport": "tennis", "stage": "pre", "format": "Best of 3", "intel": {"state": "pre"},
                    "teams": [{"name": "Alpha", "win": 0.6}, {"name": "Beta", "win": 0.4}], "set_scores": [{"score": "2-0", "winner": "Alpha"}]}
        with TemporaryDirectory() as temp, patch.dict(os.environ, {"MATCHLAB_READ_ONLY": "1"}):
            tracker.record(temp, fixture, forecast)
            tracker.ai_save(temp, fixture, "pre", {"shift": 3})
            self.assertFalse((Path(temp) / tracker.FILE).exists())

    def test_locks_name_only_forecasts_saved_before_the_start(self):
        with TemporaryDirectory() as temp:
            self.write(temp, {"a": entry(wins=(0.3, 0.7)), "b": entry(before=False)})
            locks = tracker.locks(temp)
            self.assertEqual(list(locks), ["a"])
            self.assertEqual((locks["a"]["favourite"], locks["a"]["win"]), ("Beta", 0.7))
            schedule = {"sports": {"cricket": [{"id": "a"}, {"id": "b"}]}}
            tracker.attach_locks(schedule, locks)
            self.assertIn("lock", schedule["sports"]["cricket"][0])
            self.assertNotIn("lock", schedule["sports"]["cricket"][1])

    def test_public_entry_keeps_grades_and_drops_ai_texts(self):
        item = entry(result=won(True), ai={"pre": {"shift": 2, "win": [0.62, 0.38], "at": "t", "model": "m", "headline": "secret-ish text", "reasons": ["r"]}})
        public = tracker.public_entry(item)
        self.assertEqual(public["ai"]["pre"]["shift"], 2)
        self.assertNotIn("headline", public["ai"]["pre"])
        self.assertEqual(public["result"]["winner_pick"]["correct"], True)

    def test_the_real_log_matches_an_independent_recomputation(self):
        path = ROOT / tracker.FILE
        if not path.exists():
            self.skipTest("no local prediction log")
        done = subprocess.run([sys.executable, str(ROOT / "tools/verify_track_record.py")], capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stdout[-2000:])


class GenAIGuards(unittest.TestCase):
    def test_a_stored_ai_check_can_never_move_more_than_the_cap(self):
        forecast = {"stage": "pre_toss", "intel": {"state": "pre"}, "teams": [{"win": 0.6}, {"win": 0.4}]}
        for stored in (40, -40, 5, -5, 0):
            block = ai_check.attach(dict(forecast), {"pre_toss": {"shift": stored, "at": "t"}}, True, 10, 20)
            moved = round(100 * (block["win"][0] - 0.6))
            self.assertLessEqual(abs(moved), ai_check.MAX_SHIFT)
            self.assertEqual(block["check"]["shift"], max(-5, min(5, stored)))    # the page states the shift it applied
            self.assertAlmostEqual(block["win"][0] + block["win"][1], 1.0)

    def test_parsed_shift_is_capped_at_five_points(self):
        names = ["Alpha", "Beta"]
        self.assertEqual(ai_check.parse('{"favours": "Alpha", "points": 30}', names)["shift"], ai_check.MAX_SHIFT)
        self.assertEqual(ai_check.parse('{"favours": "Beta", "points": 9}', names)["shift"], -ai_check.MAX_SHIFT)
        self.assertEqual(ai_check.MAX_SHIFT, 5)

    def test_an_uncited_sentence_is_stripped_from_the_briefing(self):
        items = {"m1": "Model X released by Lab Y", "q1": "ANT: 88.91, -8.50% over the last 5 sessions"}
        raw = json.dumps({"headline": "Busy day", "bullets": [
            {"topic": "Models", "text": "Model X arrived.", "refs": ["m1"]},
            {"topic": "Markets", "text": "Markets will rally tomorrow."},                 # no refs at all
            {"topic": "Markets", "text": "Rates were cut overnight.", "refs": []},        # empty refs
            {"topic": "Markets", "text": "ANT fell 8.5%.", "refs": ["q1"]}]})
        brief = world.parse_brief(raw, items)
        shown = json.dumps(brief)
        self.assertNotIn("rally tomorrow", shown)
        self.assertNotIn("Rates were cut", shown)
        self.assertEqual(brief["dropped"], 2)
        self.assertTrue(all(b["refs"] and set(b["refs"]) <= set(items) for b in brief["bullets"]))


class HostedMirror(unittest.TestCase):
    """api/index.py in its own process (it switches the tracker to read-only for the whole process)."""

    def test_live_schedule_keeps_saved_ids_drops_stale_live_rows_and_falls_back(self):
        script = textwrap.dedent(r'''
            import json, sys, time
            sys.path.insert(0, ROOT)
            import importlib.util
            spec = importlib.util.spec_from_file_location("mirror", ROOT + "/api/index.py")
            mirror = importlib.util.module_from_spec(spec); spec.loader.exec_module(mirror)
            soon = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 7200))
            past = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 7200))
            published = {"sports": {"cricket": [
                {"id": "cricket-cricapi-a", "state": "pre", "start": soon, "espn": {"league": "1", "event": "111"}},
                {"id": "cricket-cricapi-b", "state": "in", "start": past, "team": "Old", "team_score": "10/1"},
                {"id": "cricket-cricapi-c", "state": "pre", "start": soon, "team": "Later"}], "tennis": [], "f1": []},
                "last_updated": "2026-01-01T00:00:00+00:00"}
            live = {"connected_to_internet": True, "last_updated": "now", "sports": {"cricket": [
                {"id": "cricket-111", "state": "in", "start": past, "team_score": "55/2", "espn": {"league": "1", "event": "111"}}],
                "tennis": [{"id": "tennis-9", "state": "pre", "start": soon}], "f1": []}}
            mirror._snapshot_schedule = lambda: published
            mirror.tracker._read = lambda root: {}
            mirror.tracker.locks = lambda root: {"cricket-cricapi-a": {"favourite": "A", "win": 0.6}}
            mirror._worker = lambda *a, **k: live
            ok = mirror.today()
            mirror._worker = lambda *a, **k: None
            down = mirror.today()
            print(json.dumps({"ok": ok, "down": down}))
        ''')
        done = subprocess.run([sys.executable, "-c", f"ROOT = {str(ROOT)!r}\n" + script], capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        cricket = {m["id"]: m for m in out["ok"]["sports"]["cricket"]}
        self.assertTrue(out["ok"]["live_feed"])
        self.assertEqual(cricket["cricket-cricapi-a"]["team_score"], "55/2")          # live score, owner's id
        self.assertEqual(cricket["cricket-cricapi-a"]["lock"]["favourite"], "A")       # saved forecast still attached
        self.assertNotIn("cricket-cricapi-b", cricket)                                 # stale "live" row dropped
        self.assertTrue(cricket["cricket-cricapi-c"]["from_snapshot"])                 # upcoming row kept
        self.assertEqual(out["ok"]["counts"], {"in": 1, "pre": 2, "post": 0})
        self.assertFalse(out["down"]["live_feed"])
        self.assertIn("refresh_error", out["down"])
        self.assertIn("cricket-cricapi-b", {m["id"] for m in out["down"]["sports"]["cricket"]})

    def test_hosted_schedule_worker_uses_free_feeds_only_and_writes_nothing(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import fetch_today_matches as feed
        with TemporaryDirectory() as temp, patch.object(feed, "HOSTED", True), \
                patch.object(feed, "OUTPUT_FILE", Path(temp) / "today.json"), \
                patch.object(feed, "get_json", return_value={}), \
                patch.object(feed, "fetch_ai", side_effect=AssertionError("AI search must not run when hosted")), \
                patch.object(feed.budget, "spend", side_effect=AssertionError("no metered call when hosted")):
            payload = feed.fetch_matches()
            self.assertFalse((Path(temp) / "today.json").exists())
        self.assertIsNone(payload["budget"])
        self.assertNotIn("CricketData.org", [s["name"] for s in payload["sources"]])

    def test_mirror_serves_the_snapshot_refuses_writes_and_rate_limits(self):
        script = textwrap.dedent(r'''
            import json, sys, threading, http.client
            from http.server import ThreadingHTTPServer
            sys.path.insert(0, ROOT)
            import importlib.util
            spec = importlib.util.spec_from_file_location("mirror", ROOT + "/api/index.py")
            mirror = importlib.util.module_from_spec(spec); spec.loader.exec_module(mirror)
            mirror.LIMIT = 8
            server = ThreadingHTTPServer(("127.0.0.1", 0), mirror.handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            def call(method, path, body=None):
                c = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
                c.request(method, path, body=body, headers={"Content-Type": "application/json"} if body else {})
                r = c.getresponse(); data = r.read()
                return r.status, dict(r.getheaders()), data
            out = {}
            s, h, b = call("GET", "/api/session"); out["session"] = (s, json.loads(b))
            s, h, b = call("GET", "/api/track-record"); out["record"] = (s, h.get("Cache-Control"), sorted(json.loads(b)))
            s, h, b = call("POST", "/api/cricket-forecast", b'{"match_id": "x"}'); out["post"] = (s, json.loads(b).get("hosted"))
            s, h, b = call("POST", "/api/openrouter-key", b'{"action": "save", "key": "sk-or-v1-x"}'); out["key"] = s
            s, h, b = call("GET", "/config.local.json"); out["config"] = s
            codes = [call("GET", "/api/health")[0] for _ in range(10)]
            out["limited"] = codes[-1]
            print(json.dumps(out))
        ''')
        done = subprocess.run([sys.executable, "-c", f"ROOT = {str(ROOT)!r}\n" + script], capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        self.assertEqual(out["session"][0], 200)
        self.assertTrue(out["session"][1]["hosted"] and out["session"][1]["read_only"])
        self.assertEqual(out["session"][1]["token"], "")
        self.assertEqual(out["record"][0], 200)
        self.assertIn("s-maxage", out["record"][1])
        self.assertIn("summary", out["record"][2])
        self.assertEqual(out["post"], [403, True])
        self.assertEqual(out["key"], 403)
        self.assertEqual(out["config"], 404)
        self.assertEqual(out["limited"], 429)


if __name__ == "__main__":
    unittest.main()
