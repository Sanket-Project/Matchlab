"""Fetch one published Jolpica race grid on explicit request."""
import argparse
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def fetch_grid(round_id):
    if not re.fullmatch(r"round_[a-zA-Z0-9]+", round_id):
        raise ValueError("Invalid Jolpica round ID")
    query = urlencode({"round_id": round_id, "session_type": "R"})
    request = Request(f"https://api.jolpi.ca/f1/alpha/core/session-entries/?{query}",
                      headers={"User-Agent": "MatchLab/1.0", "Accept": "application/json"})
    with urlopen(request, timeout=10) as response:
        data = json.load(response)
    return [{"source_driver_id": row["driver"]["id"],
             "driver": f"{row['driver']['given_name']} {row['driver']['family_name']}",
             "source_constructor_id": row["team"]["id"], "constructor": row["team"]["name"],
             "grid": row["grid"]} for row in data["data"] if type(row.get("grid")) is int]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("round_id")
    args = parser.parse_args()
    print(json.dumps(fetch_grid(args.round_id)))
