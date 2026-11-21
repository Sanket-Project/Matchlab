"""Query Live Tennis API, Matchstat, or API-Tennis for live scores, fixtures, or player stats.

Reads API keys from environment or .env file (LIVE_TENNIS_API_KEY, MATCHSTAT_API_KEY, API_TENNIS_KEY).
Usage:
  python tools/fetch_tennis_live.py --provider live_tennis --endpoint matches
  python tools/fetch_tennis_live.py --provider matchstat --endpoint matches
"""
import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from matchlab.openrouter_key import get_api_key  # noqa: E402

PROVIDERS = {
    "live_tennis": {
        "base": "https://api.livetennisapi.com/api/public/v1",
        "env": "LIVE_TENNIS_API_KEY",
        "header_key": "X-API-Key",
    },
    "matchstat": {
        "base": "https://matchstat.com/api/v1",
        "env": "MATCHSTAT_API_KEY",
        "header_key": "x-api-key",
    },
    "api_tennis": {
        "base": "https://api-tennis.com/api",
        "env": "API_TENNIS_KEY",
        "header_key": "x-api-key",
    },
}


def query(provider_name="live_tennis", endpoint="matches", params=None, key=None):
    cfg = PROVIDERS.get(provider_name)
    if not cfg:
        return {"ok": False, "error": f"Unknown provider: {provider_name}"}

    api_key = key or get_api_key(cfg["env"])
    if not api_key:
        return {
            "ok": False,
            "error": f"Missing {cfg['env']}. Add it to your .env file or environment variables.",
        }

    url = f"{cfg['base']}/{endpoint.lstrip('/')}"
    if params:
        url += f"?{urlencode(params)}"

    headers = {
        cfg["header_key"]: api_key,
        "Accept": "application/json",
        "User-Agent": "MatchLab/1.0",
    }
    req = Request(url, headers=headers)
    try:
        with build_opener().open(req, timeout=15) as res:
            data = json.loads(res.read().decode("utf-8"))
            return {"ok": True, "provider": provider_name, "data": data}
    except HTTPError as err:
        return {"ok": False, "provider": provider_name, "error": f"HTTP {err.code}: {err.reason}"}
    except (URLError, OSError, ValueError) as err:
        return {"ok": False, "provider": provider_name, "error": f"Connection error: {err}"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query tennis data APIs")
    parser.add_argument("--provider", default="live_tennis", choices=list(PROVIDERS.keys()))
    parser.add_argument("--endpoint", default="matches")
    parser.add_argument("--key", default=None)
    args = parser.parse_args()

    result = query(args.provider, args.endpoint, key=args.key)
    print(json.dumps(result, indent=2))
