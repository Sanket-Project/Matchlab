"""Download ATP and WTA match results (2020 onward) for the tennis forecast.

python tools/fetch_tennis_archive.py
Source: Jeff Sackmann / Tennis Abstract, retained archive by Aneeshers (CC BY-NC-SA 4.0),
the same source as the older data/raw/tennis files. Past seasons are downloaded once;
the current season is refreshed when its copy is more than a day old. Sends nothing.
"""
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://raw.githubusercontent.com/Aneeshers/tennis-sackmann-archive/main"
FOLDER = ROOT / "data/raw/tennis_tour"
FIRST_YEAR = 2020
FILES = {"atp": ("atp_matches_{year}.csv", "atp_matches_qual_chall_{year}.csv"),
         "wta": ("wta_matches_{year}.csv", "wta_matches_qual_itf_{year}.csv")}


def main():
    this_year, failed = date.today().year, []
    for tour, patterns in FILES.items():
        (FOLDER / tour).mkdir(parents=True, exist_ok=True)
        for year in range(FIRST_YEAR, this_year + 1):
            for pattern in patterns:
                name = pattern.format(year=year)
                path = FOLDER / tour / name
                fresh = path.exists() and (year < this_year or time.time() - path.stat().st_mtime < 86400)
                if fresh:
                    continue
                try:
                    request = urllib.request.Request(f"{BASE}/{tour}/{name}", headers={"User-Agent": "MatchLab-data-setup/1.0"})
                    with urllib.request.urlopen(request, timeout=120) as response:
                        body = response.read(60_000_000)
                    if not body.startswith(b"tourney_id,"):
                        raise ValueError("unexpected file layout")
                    partial = path.with_name(name + ".partial")
                    partial.write_bytes(body)
                    partial.replace(path)
                    print(f"Downloaded {tour}/{name} ({len(body):,} bytes)", flush=True)
                except Exception as exc:
                    failed.append(f"{tour}/{name}: {type(exc).__name__}: {exc}")
    for line in failed:
        print("!", line)
    (FOLDER / "SOURCE.txt").write_text(
        "Jeff Sackmann / Tennis Abstract match results, retained archive by Aneeshers.\n"
        "https://github.com/Aneeshers/tennis-sackmann-archive  License: CC BY-NC-SA 4.0 (noncommercial).\n", encoding="utf-8")
    return 1 if failed and not any((FOLDER / tour).glob("*.csv") for tour in FILES) else 0


if __name__ == "__main__":
    sys.exit(main())
