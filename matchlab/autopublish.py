"""Publish new forecasts to the public site by itself while the owner's MatchLab runs.

The hosted site (api/index.py on Vercel) reads live scores itself but can only show the forecasts in data/public/,
which reach it by a git push. This module checks every minute whether the prediction log or the World briefing has
changed since the last publish and, if so, runs tools/publish_snapshot.py, commits only data/public/ and pushes.

Safety rules, because a push updates a public site:
- Only data/public/ is committed (`git commit -- data/public`); other edits and staged files are left alone.
- Nothing is pushed unless the checkout is on `main` with no merge or rebase in progress, and every commit that is
  ahead of origin/main is one of these automatic publishes. Your own unpushed commits are never pushed for you.
- At most one push every 15 minutes. Live timelines alone (no new or graded forecast) wait 3 hours, so a long match
  does not deploy the site again and again (Vercel's free plan allows 100 deployments a day).
- Git never prompts (GIT_TERMINAL_PROMPT=0) and every git call has a timeout. A failure is reported and retried later.
"""
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

MESSAGE = "data: publish snapshot (automatic)"
CHECK_EVERY = 60
MIN_GAP = 15 * 60
TIMELINE_GAP = 3 * 60 * 60
RETRY_AFTER = 5 * 60
SOURCES = {"predictions": ("data/local/predictions.json", "data/public/predictions.json"),
           "brief": ("data/local/cache/world_brief.json", "data/public/world_brief.json")}


def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _forecasts(log):
    """What a visitor cares about: each saved forecast and its grade, without the live timeline."""
    if not isinstance(log, dict):
        return {}
    return {key: {"pre": row.get("pre"), "result": row.get("result")}
            for key, row in log.items() if isinstance(row, dict)}


def changes(root):
    """'forecasts' when a forecast, grade or the briefing differs from data/public, 'timelines' when only live
    timelines differ, otherwise None. A source that cannot be read (being written) counts as unchanged."""
    root = Path(root)
    local, public = _read(root / SOURCES["predictions"][0]), _read(root / SOURCES["predictions"][1])
    brief, public_brief = _read(root / SOURCES["brief"][0]), _read(root / SOURCES["brief"][1])
    if local is not None and _hash(_forecasts(local)) != _hash(_forecasts(public)):
        return "forecasts"
    if brief is not None and _hash(brief) != _hash(public_brief):
        return "forecasts"
    if local is not None and _hash(local) != _hash(public):
        return "timelines"
    return None


class GitError(RuntimeError):
    pass


def _git(root, *args, timeout=30):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    try:
        done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise GitError(f"git {args[0]} timed out") from None
    except OSError as exc:
        raise GitError(f"git could not start: {exc}") from None
    if done.returncode:
        detail = (done.stderr or done.stdout).strip().splitlines()
        raise GitError(f"git {args[0]} failed: {detail[-1] if detail else 'no output'}")
    return done.stdout.strip()


def check_checkout(root):
    """Raise GitError unless an automatic push is safe from this checkout."""
    root = Path(root)
    if _git(root, "rev-parse", "--abbrev-ref", "HEAD") != "main":
        raise GitError("this checkout is not on the main branch")
    git_dir = Path(_git(root, "rev-parse", "--absolute-git-dir"))
    if any((git_dir / name).exists() for name in ("MERGE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD")):
        raise GitError("a merge or rebase is in progress")
    ahead = _git(root, "log", "origin/main..HEAD", "--format=%s")
    if any(line != MESSAGE for line in ahead.splitlines()):
        raise GitError("you have commits that are not pushed yet; push them and publishing resumes")


def publish(root, python=sys.executable):
    """Write data/public, commit it alone and push. Returns 'pushed' or 'unchanged'. Raises GitError/RuntimeError."""
    root = Path(root)
    check_checkout(root)
    try:
        done = subprocess.run([python, str(root / "tools/publish_snapshot.py")], cwd=root,
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"the snapshot could not be written: {exc}") from None
    if done.returncode:
        detail = (done.stderr or done.stdout).strip().splitlines()
        raise RuntimeError(f"the snapshot was not written: {detail[-1] if detail else 'unknown error'}")
    _git(root, "add", "--", "data/public")
    staged = subprocess.run(["git", "diff", "--cached", "--quiet", "--", "data/public"], cwd=root, timeout=30)
    if staged.returncode:
        _git(root, "commit", "--no-verify", "-m", MESSAGE, "--", "data/public")
    elif not _git(root, "log", "origin/main..HEAD", "--format=%s"):
        return "unchanged"
    _git(root, "push", "origin", "HEAD:main", timeout=90)
    return "pushed"


class Publisher:
    """Background thread for the local app. `status()` is shown under Settings."""

    def __init__(self, root, stop_event, *, publish_fn=publish, clock=time.time):
        self.root, self.stop, self.publish_fn, self.clock = Path(root), stop_event, publish_fn, clock
        self.lock = threading.Lock()
        meta = _read(self.root / "data/public/meta.json") or {}
        self.state = {"enabled": True, "published_at": meta.get("published_at"), "error": None, "pending": None,
                      "checked_at": None}
        self.last_push = 0.0
        self.retry_at = 0.0

    def start(self):
        threading.Thread(target=self._run, name="auto-publish", daemon=True).start()
        return self

    def status(self):
        with self.lock:
            return dict(self.state)

    def _run(self):
        while not self.stop.wait(CHECK_EVERY):
            self.tick()

    def tick(self, force=False):
        """One check. Returns the result string, or None when nothing was due."""
        now = self.clock()
        if not self.lock.acquire(blocking=False):
            return None
        try:
            pending = changes(self.root)
            self.state.update(pending=pending, checked_at=_iso(now))
            if not force:
                # After a failure the commit may be made but not pushed, so data/public already matches: retry anyway.
                failed = self.state["error"] is not None
                if (pending is None and not failed) or now < self.retry_at:
                    return None
                gap = TIMELINE_GAP if pending == "timelines" else MIN_GAP
                if not failed and now - self.last_push < gap:
                    return None
            try:
                result = self.publish_fn(self.root)
            except (GitError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
                self.retry_at = now + RETRY_AFTER
                self.state["error"] = str(exc)
                return "failed"
            self.last_push, self.retry_at = now, 0.0
            meta = _read(self.root / "data/public/meta.json") or {}
            self.state.update(error=None, pending=None, published_at=meta.get("published_at") or _iso(now))
            return result
        finally:
            self.lock.release()


def _iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec="seconds")
