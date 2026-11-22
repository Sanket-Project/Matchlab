"""Automatic publishing: what triggers it, the git safety rules, and the push gaps. Uses a throwaway repository."""
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from matchlab import autopublish

ROOT = Path(__file__).resolve().parents[1]


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.rstrip()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


LOG = {"cricket-1": {"pre": {"p": 0.6}, "result": None, "fixture": {"id": "cricket-1"}, "timeline": []}}


class Repo(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.remote, self.root = self.tmp / "remote.git", self.tmp / "work"
        git(self.tmp, "init", "--bare", "-b", "main", str(self.remote))
        git(self.tmp, "clone", str(self.remote), str(self.root))
        for key, value in (("user.name", "Test"), ("user.email", "test@example.invalid"), ("commit.gpgsign", "false")):
            git(self.root, "config", key, value)
        (self.root / "tools").mkdir()
        shutil.copy(ROOT / "tools/publish_snapshot.py", self.root / "tools/publish_snapshot.py")
        write(self.root / "data/today_matches.json", {"sports": {}})
        write(self.root / "data/local/predictions.json", LOG)
        (self.root / ".gitignore").write_text("data/local/\n", encoding="utf-8")
        (self.root / "notes.txt").write_text("v1\n", encoding="utf-8")
        git(self.root, "add", ".")
        git(self.root, "commit", "-m", "start")
        git(self.root, "push", "origin", "main")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def remote_log(self):
        return git(self.remote, "log", "main", "--format=%s").splitlines()

    def test_changes_tell_forecasts_from_timelines(self):
        self.assertEqual(autopublish.changes(self.root), "forecasts")  # nothing published yet
        write(self.root / "data/public/predictions.json", LOG)
        self.assertIsNone(autopublish.changes(self.root))
        timeline = {"cricket-1": {**LOG["cricket-1"], "timeline": [{"at": "x", "p": 0.7}]}}
        write(self.root / "data/local/predictions.json", timeline)
        self.assertEqual(autopublish.changes(self.root), "timelines")
        graded = {"cricket-1": {**timeline["cricket-1"], "result": {"won": True}}}
        write(self.root / "data/local/predictions.json", graded)
        self.assertEqual(autopublish.changes(self.root), "forecasts")
        (self.root / "data/local/predictions.json").write_text("{half", encoding="utf-8")  # being written
        self.assertIsNone(autopublish.changes(self.root))

    def test_publish_commits_only_data_public_and_pushes(self):
        (self.root / "notes.txt").write_text("my edit\n", encoding="utf-8")
        (self.root / "other.txt").write_text("staged\n", encoding="utf-8")
        git(self.root, "add", "other.txt")
        self.assertEqual(autopublish.publish(self.root), "pushed")
        self.assertEqual(self.remote_log(), [autopublish.MESSAGE, "start"])
        files = git(self.remote, "show", "--name-only", "--format=", "main").splitlines()
        self.assertEqual(sorted(files), ["data/public/meta.json", "data/public/predictions.json",
                                         "data/public/today_matches.json"])
        status = git(self.root, "status", "--porcelain")
        self.assertIn(" M notes.txt", status)  # still yours, uncommitted
        self.assertIn("A  other.txt", status)  # still staged, not committed
        self.assertIsNone(autopublish.changes(self.root))

    def test_never_pushes_your_own_unpushed_commits(self):
        (self.root / "notes.txt").write_text("work in progress\n", encoding="utf-8")
        git(self.root, "commit", "-am", "my unfinished work")
        with self.assertRaisesRegex(autopublish.GitError, "not pushed yet"):
            autopublish.publish(self.root)
        self.assertEqual(self.remote_log(), ["start"])
        self.assertFalse((self.root / "data/public").exists())

    def test_refuses_other_branches(self):
        git(self.root, "checkout", "-b", "feature")
        with self.assertRaisesRegex(autopublish.GitError, "main branch"):
            autopublish.publish(self.root)

    def test_failed_push_is_retried_with_the_automatic_commit(self):
        git(self.root, "remote", "set-url", "origin", str(self.tmp / "missing.git"))
        with self.assertRaises(autopublish.GitError):
            autopublish.publish(self.root)
        git(self.root, "remote", "set-url", "origin", str(self.remote))
        self.assertIsNone(autopublish.changes(self.root))  # committed locally, so only the retry can push it
        self.assertEqual(autopublish.publish(self.root), "pushed")
        self.assertEqual(self.remote_log()[-1], "start")
        self.assertTrue(all(line == autopublish.MESSAGE for line in self.remote_log()[:-1]))


class Gaps(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.now = [1_000_000.0]
        self.calls = []
        self.pending = ["forecasts"]
        self.fail = [False]

        def fake_publish(root):
            self.calls.append(self.now[0])
            if self.fail[0]:
                raise autopublish.GitError("git push failed: offline")
            return "pushed"

        self.publisher = autopublish.Publisher(self.tmp, threading.Event(), publish_fn=fake_publish,
                                               clock=lambda: self.now[0])
        self.original = autopublish.changes
        autopublish.changes = lambda root: self.pending[0]

    def tearDown(self):
        autopublish.changes = self.original
        shutil.rmtree(self.tmp, ignore_errors=True)

    def advance(self, seconds):
        self.now[0] += seconds

    def test_new_forecasts_wait_for_the_gap_and_timelines_wait_longer(self):
        self.assertEqual(self.publisher.tick(), "pushed")
        self.advance(60)
        self.assertIsNone(self.publisher.tick())  # within 15 minutes of the last push
        self.advance(autopublish.MIN_GAP)
        self.assertEqual(self.publisher.tick(), "pushed")
        self.pending[0] = "timelines"
        self.advance(autopublish.MIN_GAP)
        self.assertIsNone(self.publisher.tick())
        self.advance(autopublish.TIMELINE_GAP)
        self.assertEqual(self.publisher.tick(), "pushed")
        self.pending[0] = None
        self.advance(autopublish.TIMELINE_GAP)
        self.assertIsNone(self.publisher.tick())
        self.assertEqual(len(self.calls), 3)

    def test_a_failure_is_shown_and_retried_even_when_nothing_else_changed(self):
        self.fail[0] = True
        self.assertEqual(self.publisher.tick(), "failed")
        self.assertIn("offline", self.publisher.status()["error"])
        self.pending[0], self.fail[0] = None, False
        self.advance(60)
        self.assertIsNone(self.publisher.tick())  # waits before retrying
        self.advance(autopublish.RETRY_AFTER)
        self.assertEqual(self.publisher.tick(), "pushed")
        self.assertIsNone(self.publisher.status()["error"])

    def test_publish_now_skips_the_gap(self):
        self.publisher.tick()
        self.pending[0] = None
        self.assertEqual(self.publisher.tick(force=True), "pushed")


if __name__ == "__main__":
    unittest.main()
