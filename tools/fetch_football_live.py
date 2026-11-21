"""Query Football-Data.org (football-data.org) for live football fixtures, scores, and standings.

Reads FOOTBALL_DATA_API_KEY from environment or .env file.
Usage:
  python tools/fetch_football_live.py --competition PL --endpoint matches
  python tools/fetch_football_live.py --competition PL --endpoint standings
"""
import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from matchlab.openrouter_key import get_api_key  # noqa: E402

BASE_URL = "https://api.football-data.org/v4"


def fetch_football(competition="PL", endpoint="matches", key=None):
    api_key = key or get_api_key("FOOTBALL_DATA_API_KEY")
    if not api_key:
        return {
            "ok": False,
            "error": "Missing FOOTBALL_DATA_API_KEY. Add it to .env or environment variables.",
        }

    url = f"{BASE_URL}/competitions/{competition}/{endpoint.lstrip('/')}"
    req = Request(
        url,
        headers={
            "X-Auth-Token": api_key,
            "Accept": "application/json",
            "User-Agent": "MatchLab/1.0",
        },
    )

    try:
        with build_opener().open(req, timeout=15) as res:
            data = json.loads(res.read().decode("utf-8"))
            return {"ok": True, "competition": competition, "data": data}
    except HTTPError as err:
        return {"ok": False, "error": f"HTTP {err.code}: {err.reason}"}
    except (URLError, OSError, ValueError) as err:
        return {"ok": False, "error": f"Connection error: {err}"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query Football-Data.org")
    parser.add_argument("--competition", default="PL")
    parser.add_argument("--endpoint", default="matches")
    parser.add_argument("--key", default=None)
    args = parser.parse_args()

    result = fetch_football(args.competition, args.endpoint, args.key)
    print(json.dumps(result, indent=2))
