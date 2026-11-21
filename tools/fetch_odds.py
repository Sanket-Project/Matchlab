"""Query The Odds API (the-odds-api.com) for bookmaker betting odds & consensus win probabilities.

Reads THE_ODDS_API_KEY from environment or .env file.
Usage:
  python tools/fetch_odds.py --sport tennis_atp
  python tools/fetch_odds.py --sport soccer_epl
"""
import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from matchlab.openrouter_key import get_api_key  # noqa: E402

BASE_URL = "https://api.the-odds-api.com/v4/sports"


def fetch_odds(sport="tennis_atp", regions="us,eu,uk", markets="h2h", key=None):
    api_key = key or get_api_key("THE_ODDS_API_KEY")
    if not api_key:
        return {
            "ok": False,
            "error": "Missing THE_ODDS_API_KEY. Add it to .env or environment variables.",
        }

    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal",
    }
    url = f"{BASE_URL}/{sport}/odds?{urlencode(params)}"
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "MatchLab/1.0"})

    try:
        with build_opener().open(req, timeout=15) as res:
            headers = dict(res.info())
            remaining = headers.get("x-requests-remaining")
            used = headers.get("x-requests-used")
            data = json.loads(res.read().decode("utf-8"))
            return {
                "ok": True,
                "sport": sport,
                "quota": {"remaining": remaining, "used": used},
                "matches": data,
            }
    except HTTPError as err:
        return {"ok": False, "error": f"HTTP {err.code}: {err.reason}"}
    except (URLError, OSError, ValueError) as err:
        return {"ok": False, "error": f"Connection error: {err}"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query The Odds API")
    parser.add_argument("--sport", default="tennis_atp")
    parser.add_argument("--regions", default="us,eu,uk")
    parser.add_argument("--markets", default="h2h")
    parser.add_argument("--key", default=None)
    args = parser.parse_args()

    result = fetch_odds(args.sport, args.regions, args.markets, args.key)
    print(json.dumps(result, indent=2))
