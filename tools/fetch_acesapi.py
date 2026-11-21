"""Ask AcesAPI for two players' surface Elo and head-to-head. Reads a JSON request over stdin.

stdin: {"key": "...", "tour": "atp"|"wta", "names": [a, b], "surface": "hard"}   -> JSON on stdout
Costs 7 credits (see matchlab/acesapi.py); the server meters them before starting this worker.
Runs as a short-lived process so the dashboard server stays offline.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from matchlab import acesapi  # noqa: E402

BASE = "https://mcp.acesapi.com/v1"
ERRORS = {401: "AcesAPI did not accept the key.", 402: "The AcesAPI key has no credits left this month.",
          429: "AcesAPI is rate limiting requests. Try again in a minute."}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # never send the key anywhere else
        return None


OPENER = build_opener(_NoRedirect)


def call(key, tool, body):
    request = Request(f"{BASE}/{tool}", data=json.dumps(body).encode("utf-8"), method="POST",
                      headers={"Content-Type": "application/json", "Accept": "application/json", "x-api-key": key,
                               "User-Agent": "MatchLab/1.0"})
    try:
        with OPENER.open(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise RuntimeError(ERRORS.get(error.code, f"AcesAPI answered {error.code}.")) from None


def fetch(job):
    key, names = job["key"], job["names"]
    league, surface = acesapi.LEAGUES[job["tour"]], acesapi.surface(job.get("surface")) or "hard"
    players = [acesapi.pick_player(call(key, "search_players", {"name": acesapi.search_term(n), "league": league, "limit": 20}).get("players"), n)
               for n in names]
    ratings = call(key, "get_ratings", {"surface": surface, "league": league, "limit": acesapi.RATINGS_LIMIT})
    h2h = call(key, "get_head_to_head", {"player_id": players[0]["player_id"], "opponent_id": players[1]["player_id"], "league": league}) \
        if all(players) else None
    return acesapi.shape(names, players, h2h, ratings, surface, datetime.now(timezone.utc).isoformat(timespec="seconds"))


if __name__ == "__main__":
    try:
        job = json.loads(sys.stdin.read())
        if job.get("tour") not in acesapi.LEAGUES or len(job.get("names") or []) != 2 or not job.get("key"):
            raise ValueError("bad request")
        print(json.dumps(fetch(job)))
    except Exception as exc:  # reported to the server as data; never a traceback or the key
        print(json.dumps({"ok": False, "error": str(exc) if isinstance(exc, RuntimeError) else f"{type(exc).__name__}"}))
