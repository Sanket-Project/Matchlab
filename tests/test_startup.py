"""Server lifecycle regressions; no model loading or external requests."""
import contextlib
import errno
import io
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import app


class StartupTests(unittest.TestCase):
    def test_manual_tennis_refresh_bypasses_cache_and_marks_failed_feed_stale(self):
        handler = app.Handler.__new__(app.Handler)
        cached = {"ok": True, "state": "in"}
        handler.server = SimpleNamespace(intel_cache={("tennis", "123"): (time.monotonic(), cached)})
        match = {"id": "tennis-123", "start": "2026-11-17T12:00:00Z"}
        with patch.object(app.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps({"ok": False}))) as fetch:
            self.assertIs(handler._tennis_intel(match), cached)
            fetch.assert_not_called()
            self.assertTrue(handler._tennis_intel(match, max_age=0)["stale"])
            fetch.assert_called_once()
        self.assertNotIn("stale", cached)

    def test_occupied_port_preserves_bind_error_and_does_not_start_monitor(self):
        engine = SimpleNamespace(config={})
        with app.LocalServer(("127.0.0.1", 0), engine) as running:
            with patch.object(app.threading.Thread, "start") as start:
                with self.assertRaises(OSError) as caught:
                    app.LocalServer(running.server_address, engine, monitor_fixtures=True)
            self.assertTrue(caught.exception.errno == errno.EADDRINUSE
                            or getattr(caught.exception, "winerror", None) == 10048)
            start.assert_not_called()
            self.assertFalse(running.stop_forecasts.is_set())
        self.assertTrue(running.stop_forecasts.is_set())

    def test_failed_bind_closes_socket(self):
        server = app.LocalServer.__new__(app.LocalServer)
        with patch.object(app.LocalServer, "server_bind", side_effect=OSError(errno.EADDRINUSE, "busy")):
            with self.assertRaises(OSError):
                server.__init__(("127.0.0.1", 0), SimpleNamespace(config={}))
        self.assertTrue(server.stop_forecasts.is_set())
        self.assertEqual(server.socket.fileno(), -1)

    def test_main_reports_port_conflict_without_opening_browser(self):
        output = io.StringIO()
        with patch("sys.argv", ["app.py", "--port", "8766", "--open"]), \
             patch.object(app, "Engine"), \
             patch.object(app, "LocalServer", side_effect=OSError(errno.EADDRINUSE, "busy")), \
             patch("webbrowser.open") as open_browser, contextlib.redirect_stderr(output):
            with self.assertRaises(SystemExit) as caught:
                app.main()
        self.assertEqual(caught.exception.code, 1)
        self.assertIn("port 8766 is already in use", output.getvalue())
        self.assertIn("http://127.0.0.1:8766", output.getvalue())
        open_browser.assert_not_called()


if __name__ == "__main__":
    unittest.main()
