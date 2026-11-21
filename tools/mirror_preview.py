"""Run the public mirror on this computer, laid out as on Vercel: dash.html at /, its assets, and api/index.py.

Use it to see the hosted, read-only dashboard before publishing. It reads data/public/ only.
Run: python tools/mirror_preview.py [port]   (default 8767), then open http://127.0.0.1:8767/
"""
import importlib.util
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
spec = importlib.util.spec_from_file_location("mirror", ROOT / "api" / "index.py")
mirror = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror)
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".svg": "image/svg+xml", ".woff2": "font/woff2", ".jpg": "image/jpeg", ".webp": "image/webp", ".json": "application/json"}


class Preview(mirror.handler):
    def do_GET(self):
        path = self.path.split("?")[0].split("#")[0]
        if path.startswith("/api/"):
            return super().do_GET()
        if path in ("/lab", "/dash", "/dash.html"):
            self.send_response(308)
            self.send_header("Location", "/")
            self.end_headers()
            return None
        target = (WEB / ("dash.html" if path == "/" else path.lstrip("/"))).resolve()
        allowed = target.is_file() and target.is_relative_to(WEB) and target.suffix in TYPES and target.name not in ("index.html", "app.js", "style.css")
        if not allowed or "Formula 1 Drivers" in str(target) or "Tennis Players" in str(target):
            return self._send(404, {"error": "Not found"})
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", TYPES[target.suffix])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Security-Policy", mirror.CSP)
        self.end_headers()
        self.wfile.write(body)
        return None


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8767
    print(f"MatchLab public mirror preview at http://127.0.0.1:{port}/ (read-only, data/public/)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Preview).serve_forever()
