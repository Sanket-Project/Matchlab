"""Refresh and publish MatchLab's source-backed global cricket CSV snapshot."""

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import formatdate
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from matchlab.cricket_archive import CRICSHEET, index_by, read_cricsheet
from matchlab.cricket_audit import REQUIRED, accuracy_stats, audit_records, coverage_rows, fixture_key
from matchlab.cricket_correlations import correlation_rows
from matchlab.cricket_sources import (
    ABU_DHABI_FEEDS, ABU_DHABI_URL, COUNTRIES_URL, CREX_CALENDAR, CREX_EPL, CREX_T10, CRICSHEET_COVERAGE, ESPN_URL,
    EPL_REFERENCE, abu_dhabi_matches, country_register, crex_matches, crex_series_links, crex_series_title, cricsheet_coverage,
    epl_scorecard_references, espn_fixtures, utc_stamp,
)


ARCHIVE_URL = CRICSHEET + "all_json.zip"
RAW = ROOT / "data/raw/cricket"
OUTPUT = ROOT / "data/real/cricket_global"
ARCHIVED_SERIES = [
    ("epl.html", CREX_EPL, "Everest Premier League", "2021", "T20", "Nepal"),
    ("apl.html", "https://crex.com/series/afghanistan-premier-league-2018-2J/matches",
     "Afghanistan Premier League", "2018", "T20", "Afghanistan"),
    ("zim-t10.html", "https://crex.com/series/zim-afro-t10-2024-1MU/matches", "Zim Afro T10", "2024", "T10", "Zimbabwe"),
    ("us-t10.html", "https://crex.com/series/1GY/us-masters-t10-league-2023/matches", "US Masters T10", "2023", "T10", "United States of America"),
    *((f"t10-{season.replace('/', '-')}.html", url, "Abu Dhabi T10", season, "T10", "United Arab Emirates")
      for season, url in CREX_T10.items()),
]
AUDIT_SERIES = [
    ("ipl-audit.html", "https://crex.com/series/indian-premier-league-2026-1PW/matches",
     "Indian Premier League", "2026", "T20", "India", "male", "club"),
    ("bbl-audit.html", "https://crex.com/series/big-bash-league-2025-26-1VD/matches",
     "Big Bash League", "2025/26", "T20", "Australia", "male", "club"),
    ("wodi-audit.html", "https://crex.com/series/womens-world-cup-2025-1UW/matches",
     "", "2025/26", "ODI", "", "female", "international"),
    ("t20i-audit.html", "https://crex.com/series/t20-world-cup-2026-1UY/matches",
     "", "2026", "T20I", "", "male", "international"),
]
KNOWN_SERIES = {"https://crex.com/series/big-bash-league-2026-27-2KQ/matches"}

SCHEMAS = {
    "competitions": """competition_id requested_label official_name season organizer country_or_region
        competition_level team_category age_group format source_url confidence confidence_reason""",
    "matches": """match_id competition_id league tournament season stage format match_classification competition_level
        team_category age_group team_a team_b start_date_local start_time_utc end_date_local venue city country_or_region host_country
        match_status result result_as_published winner result_margin result_method toss_winner toss_decision batting_first
        score_a_as_published score_b_as_published source source_match_id source_url retrieved_at_utc confidence confidence_reason""",
    "innings": """match_id innings_number batting_team runs wickets legal_balls score_as_published is_super_over
        declared forfeited source_url confidence confidence_reason""",
    "coverage": """scope country_or_region country_code competition_id_or_requested_label competition_name season format
        team_category expected_matches matches_captured results_verified coverage_fraction coverage_status gap_reason
        source_urls confidence""",
    "correlations": """competition_id competition_or_group format team_category age_group competition_level date_range factor
        outcome method estimate ci_lower ci_upper confidence_interval sample_size group_a_size group_b_size excluded_count
        confidence confidence_reason""",
    "accuracy_audit": """match_id competition season format team_category field expected observed status source_url
        reference_id reference_url""",
}


def request(url, headers=None):
    return urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0", **(headers or {})}), timeout=55)


def download_archive(url, destination, previous):
    headers = {"Range": "bytes=0-0"}
    if previous.exists():
        headers["If-Modified-Since"] = formatdate(previous.stat().st_mtime, usegmt=True)
    with request(url, headers) as response:
        if response.status == 200:
            shutil.copyfileobj(response, destination)
            return
        total = int(response.headers["Content-Range"].rsplit("/", 1)[1])
        etag = response.headers.get("ETag")

    with TemporaryDirectory(dir=previous.parent) as folder:
        def get_part(start):
            end = min(start + 8 * 1024 * 1024, total) - 1
            part = Path(folder) / str(start)
            part_headers = {"Range": f"bytes={start}-{end}"}
            if etag and not etag.startswith("W/"):
                part_headers["If-Range"] = etag
            with request(f"{url}?chunk={start}", part_headers) as response, part.open("wb") as handle:
                if response.headers.get("Content-Range") != f"bytes {start}-{end}/{total}":
                    raise ValueError("Cricsheet archive changed or returned an invalid byte range")
                if etag and response.headers.get("ETag") not in {None, etag}:
                    raise ValueError("Cricsheet archive changed during download")
                shutil.copyfileobj(response, handle)
            if part.stat().st_size != end - start + 1:
                raise ValueError("Cricsheet archive byte range was incomplete")
            return part

        with ThreadPoolExecutor(max_workers=6) as pool:
            for part in pool.map(get_part, range(0, total, 8 * 1024 * 1024)):
                with part.open("rb") as handle:
                    shutil.copyfileobj(handle, destination)


class SourceCache:
    def __init__(self, folder, refresh, offline):
        self.folder = folder
        self.refresh = refresh
        self.offline = offline
        self.warnings = []
        folder.mkdir(parents=True, exist_ok=True)

    def get(self, name, url):
        path = self.folder / name
        if path.exists() and not self.refresh:
            return path
        if self.offline:
            self.warnings.append(f"Offline cache missing for {url}")
            return None
        temp = None
        try:
            with NamedTemporaryFile(dir=self.folder, suffix=".part", delete=False) as handle:
                temp = Path(handle.name)
                if name == "all_json.zip":
                    download_archive(url, handle, path)
                else:
                    with request(url) as response:
                        shutil.copyfileobj(response, handle)
            if name.endswith(".zip"):
                with ZipFile(temp) as archive:
                    if not any(item.endswith(".json") for item in archive.namelist()):
                        raise ValueError("Archive contains no match JSON")
            elif name.endswith(".json"):
                json.loads(temp.read_bytes())
            temp.replace(path)
            print(f"Downloaded {name}", flush=True)
        except (OSError, ValueError, BadZipFile) as exc:
            if not (isinstance(exc, HTTPError) and exc.code == 304 and path.exists()):
                fallback = "retained cached copy" if path.exists() else "source unavailable"
                self.warnings.append(f"{name}: {exc} ({fallback})")
        finally:
            if temp:
                temp.unlink(missing_ok=True)
        return path if path.exists() else None


def retrieved(path):
    return utc_stamp(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc))


def schedule_keys(records, source_url):
    groups = index_by((match for match, _ in records), lambda m: (m["competition_id"], m["season"], m["format"], m["team_category"]))
    return {key: (len(rows), source_url) for key, rows in groups.items()}


def read_optional(cache, name, url, parse):
    path = cache.get(name, url)
    if path is None:
        return []
    try:
        return list(parse(path))
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        cache.warnings.append(f"{name}: source data could not be parsed ({exc})")
        return []


def merge_records(records, additions, references):
    by_id = {match["match_id"] for match, _ in records}
    by_fixture = index_by((match for match, _ in records), fixture_key)
    for match, scores in additions:
        key = fixture_key(match)
        candidates = [row for row in by_fixture[key] if row["source"] != match["source"]
                      and match["format"] == row["format"] and match["team_category"] == row["team_category"]]
        if match["match_id"] in by_id:
            continue
        if key[0] and len(key[1]) == 2 and "" not in key[1] and len(candidates) == 1:
            if match["result"]:
                references.append((match, scores))
            continue
        records.append((match, scores))
        by_fixture[key].append(match)
        by_id.add(match["match_id"])


def retain_match_ids(records, previous):
    def identity(row):
        return fixture_key(row), row["format"], row["team_category"]

    prior = index_by(previous, identity)
    current = index_by(records, lambda item: identity(item[0]))
    used = {row["match_id"] for row, _ in records}
    for key, items in current.items():
        (day, teams), _, _ = key
        if len(items) != 1 or len(prior[key]) != 1 or not day or len(teams) != 2 or "" in teams:
            continue
        row, innings = items[0]
        old = prior[key][0]
        if old["match_id"] in used:
            continue
        row["match_id"] = old["match_id"]
        used.add(old["match_id"])
        for inning in innings:
            inning["match_id"] = old["match_id"]


def previous_snapshot(output):
    latest = output / "latest.json"
    if not latest.exists():
        return []
    name = json.loads(latest.read_bytes())["snapshot"]
    if not re.fullmatch(r"\d{8}T\d{12}Z", name):
        raise ValueError("Invalid cricket snapshot name in latest.json")
    with (output / name / "matches.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_calendar(cache, skip_abu_dhabi):
    links = read_optional(cache, "crex-series.html", CREX_CALENDAR,
                          lambda path: crex_series_links(path.read_text(encoding="utf-8")))
    if not links:
        cache.warnings.append("CREX calendar supplied no competition links")
    catalog = cache.folder / "crex-catalog.json"
    retained = json.loads(catalog.read_bytes()) if catalog.exists() else []
    links = sorted(set(links) | set(retained) | KNOWN_SERIES)
    links = [url for url in links if re.fullmatch(r"https://crex\.com/series/[a-z0-9-]+-[A-Z0-9]+/matches", url)]
    if not cache.offline:
        with NamedTemporaryFile(dir=cache.folder, delete=False) as handle:
            handle.write(json.dumps(links, indent=2).encode("utf-8"))
        Path(handle.name).replace(catalog)

    def read_series(url):
        key = url.removesuffix("/matches").rsplit("-", 1)[1]
        found = read_optional(cache, f"series-{key}.html", url, lambda path: crex_matches(
            path.read_text(encoding="utf-8"), url, "", "", "", "", retrieved(path)))
        if not found:
            cache.warnings.append(f"No fixture rows available for {url}")
            cached = cache.folder / f"series-{key}.html"
            title = crex_series_title(cached.read_text(encoding="utf-8")) if cached.exists() else ""
        else:
            title = ""
        return url, found, title

    if skip_abu_dhabi:
        links = [url for url in links if "/abu-dhabi-t10-" not in url]
    with ThreadPoolExecutor(max_workers=6) as executor:
        return list(executor.map(read_series, links))


def load_records(cache):
    archive = cache.get("all_json.zip", ARCHIVE_URL)
    if archive is None:
        raise SystemExit("The full Cricsheet archive is required. See source errors or provide all_json.zip in the cache.")
    print("Reading Cricsheet match archive", flush=True)
    records = list(read_cricsheet(archive, retrieved(archive)))
    references = []
    schedules = {}
    gaps = []
    current_t10 = set()
    index = read_optional(cache, "abudhabi-index.json", f"{ABU_DHABI_FEEDS}/Competition.json",
                          lambda path: json.loads(path.read_bytes()))
    for comp in index:
        code = str(comp["CompID"])
        season = re.search(r"\b\d{4}\b", comp["CompName"])
        if not code.isdecimal() or not season:
            continue
        url = f"{ABU_DHABI_FEEDS}/Comp/{code}/fixtures.json"
        found = read_optional(cache, f"abudhabi-{code}.json", url,
                              lambda path: abu_dhabi_matches(json.loads(path.read_bytes()), season[0], retrieved(path)))
        if found:
            current_t10.add(season[0])
            schedules.update(schedule_keys(found, ABU_DHABI_URL))
            records.extend(found)
    for name, url, league, season, fmt, country in ARCHIVED_SERIES:
        found = read_optional(cache, name, url, lambda path: crex_matches(
            path.read_text(encoding="utf-8"), url, league, season, fmt, country, retrieved(path)))
        if league == "Abu Dhabi T10" and season in current_t10:
            references.extend(found)
        else:
            schedules.update(schedule_keys(found, url))
            records.extend(found)

    current_year = str(datetime.now(timezone.utc).year)
    for url, found, title in load_calendar(cache, current_year in current_t10):
        if found:
            schedules.update(schedule_keys(found, url))
            merge_records(records, found, references)
        else:
            gaps.append((title, url))
    fixtures = read_optional(cache, "espn.json", ESPN_URL,
                             lambda path: espn_fixtures(json.loads(path.read_bytes()), retrieved(path)))
    merge_records(records, fixtures, references)
    for name, url, league, season, fmt, country, category, level in AUDIT_SERIES:
        found = read_optional(cache, name, url, lambda path: crex_matches(
            path.read_text(encoding="utf-8"), url, league, season, fmt, country, retrieved(path), category, level))
        merge_records(records, found, references)
        # Domestic aliases are shared with Cricsheet, so its season count can
        # be checked against the independently published fixture list.
        if level == "club":
            schedules.update(schedule_keys(found, url))
    references.extend(read_optional(cache, "epl-audit.html", EPL_REFERENCE,
                                    lambda path: epl_scorecard_references(path.read_text(encoding="utf-8"))))
    return records, schedules, references, gaps


def competitions(matches):
    by_comp = index_by((row for row in matches if row["competition_id"]),
                       lambda row: (row["competition_id"], row["tournament"], row["season"], row["format"]))
    for _, cohort in sorted(by_comp.items()):
        first = cohort[0]
        label = next((label for label, check in REQUIRED.items() if label not in {"T10", "International cricket"} and check(first)), "")
        yield dict(competition_id=first["competition_id"], requested_label=label, official_name=first["tournament"],
                   season=first["season"], country_or_region=first["country_or_region"],
                   competition_level=first["competition_level"], team_category=first["team_category"], age_group=first.get("age_group", ""),
                   format=first["format"], source_url=first["source_url"], confidence=first["confidence"],
                   confidence_reason="Name as published by the match source")


def summary_text(matches, coverage, audit, correlations, stamp, warnings):
    dates = [row["start_date_local"] for row in matches if row["start_date_local"]]
    types = Counter(m["format"] or "Unclassified" for m in matches)
    levels = Counter(m["competition_level"] for m in matches)
    statuses = Counter(m["match_status"] for m in matches)
    accuracy = accuracy_stats(audit)
    accuracy_value = accuracy["accuracy"]
    accuracy_label = f'{accuracy_value:.1%}' if accuracy_value is not None else "unmeasured"
    target = ("unmeasured" if accuracy_value is None else "above the target range" if accuracy_value > .9
              else "below the target range" if accuracy_value < .8 else "within the target range")
    lines = [
        "# Global cricket coverage and correlations", "",
        f"Snapshot built {stamp}. Match dates run from {min(dates)} to {max(dates)}.",
        f"The export has **{len(matches):,} matches** ({levels['international']:,} international and "
        f"{levels['club']:,} club records). The available schedules include **{statuses['scheduled']:,} scheduled fixtures**.", "",
        "Formats include " + ", ".join(f"{name} ({count:,})" for name, count in sorted(types.items())) + ".", "",
        "## Coverage checklist", "",
    ]
    for row in coverage:
        if row["scope"] == "requested":
            label = row["competition_id_or_requested_label"]
            name = f" ({row['competition_name']})" if row["competition_name"] != label else ""
            lines.append(f"- **{label}**{name} · {row['matches_captured']:,} matches, {row['coverage_status']}.")
    jurisdictions = [r for r in coverage if r["scope"] == "jurisdiction"]
    by_audit_group = index_by(audit, lambda row: (row["competition"], row["season"]))
    lines.extend([
        "",
        f"The coverage table lists {len(jurisdictions)} country, territory and cricket-jurisdiction entries. "
        f"{sum(bool(r['matches_captured']) for r in jurisdictions)} have domestic records assigned to them. "
        "The other entries need domestic feeds. Many school, club, regional and historical competitions lack a sourced schedule.",
        "",
        "Cricsheet supplies the main historical archive. Its missing and withheld matches and the seasons "
        "absent from supplemental feeds leave gaps. A blank expected count means the full fixture denominator is unknown.",
        "",
        "## Field accuracy", "",
        f"Target **80%–90%**. The reference sample measured **{accuracy_label}** ({target}) "
        f"across {accuracy['checked']:,} populated fields in {accuracy['matches']:,} matched fixtures. "
        f"The audit also records {accuracy['missing']:,} missing values and {accuracy['unlinked']:,} unlinked reference fixtures. "
        "The reference sample covers only the competitions and seasons identified in the audit table. "
        "Overall global accuracy remains unmeasured.",
        "",
    ])
    for (competition, season), rows in sorted(by_audit_group.items()):
        stats = accuracy_stats(rows)
        if stats["checked"]:
            lines.append(f"- {competition} · {season} · {stats['accuracy']:.1%} of "
                         f"{stats['checked']:,} checked fields across {stats['matches']:,} fixtures.")
    lines.extend([
        "",
        "## Associations", "",
        "Form uses each team's last five decisive results, available before the match date. Toss and batting-order comparisons "
        "use decisive matches. Venue comparisons use first-innings scoring per six legal balls and omit matches with a special "
        "result method. Estimates describe associations. Intervals account for repeated teams when enough team clusters are available.",
        "",
    ])
    examples = [row for row in correlations if not row["competition_id"] and row["format"] == "T20I"
                and row["team_category"] == "male" and not row["age_group"] and row["estimate"] != "" and row["factor"] in
                {"Higher pre-match form", "Toss winner bats vs fields", "Batting first"}]
    for row in examples:
        lines.append(f"- Men's T20I · {row['factor']} · {row['estimate'] * 100:+.1f} percentage points "
                     f"({row['sample_size']:,} matches).")
    if warnings:
        lines.extend(["", "Source refresh or parsing gaps are listed in `manifest.json`."])
    lines.extend(["", "Historical ball-by-ball data © Cricsheet contributors, ODC-BY-1.0. "
                  "Supplemental sources are identified in each row.", ""])
    return "\n".join(lines)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def publish(output, tables, summary, manifest, run_time):
    output.mkdir(parents=True, exist_ok=True)
    name = run_time.strftime("%Y%m%dT%H%M%S%fZ")
    with TemporaryDirectory(prefix=".build-", dir=output) as staging:
        stage = Path(staging) / name
        stage.mkdir()
        for table, rows in tables.items():
            with (stage / f"{table}.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, SCHEMAS[table].split(), extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
        (stage / "summary.md").write_text(summary, encoding="utf-8")
        manifest["files"] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in stage.iterdir()}
        write_json(stage / "manifest.json", manifest)
        final = output / name
        stage.rename(final)
        latest = Path(staging) / "latest.json"
        write_json(latest, {"snapshot": name, "built_at_utc": manifest["built_at_utc"]})
        latest.replace(output / "latest.json")
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=RAW, help="Source cache directory")
    parser.add_argument("--output", type=Path, default=OUTPUT, help="Destination for versioned CSV snapshots")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--refresh", action="store_true", help="Refresh all connected sources before building")
    mode.add_argument("--offline", action="store_true", help="Build only from the existing source cache")
    args = parser.parse_args()
    cache = SourceCache(args.raw, args.refresh, args.offline)
    run_time = datetime.now(timezone.utc)
    records, schedules, references, gaps = load_records(cache)
    retain_match_ids(records, previous_snapshot(args.output))
    country_file = cache.get("m49.html", COUNTRIES_URL)
    if country_file is None:
        raise SystemExit("The UN M49 country register is required to build the coverage audit.")
    countries = country_register(country_file.read_text(encoding="utf-8"))
    published_coverage = read_optional(cache, "cover.html", CRICSHEET_COVERAGE,
                                       lambda path: cricsheet_coverage(path.read_text(encoding="utf-8")))
    matches = sorted((match for match, _ in records), key=lambda row: (row["start_date_local"], row["match_id"]))
    innings = [inning for _, scores in records for inning in scores]
    audit = list(audit_records(matches, innings, references))
    conflicts = {row["match_id"] for row in audit if row["status"] == "conflict"}
    verified = {row["match_id"] for row in audit if row["field"] == "result" and row["status"] == "correct"}
    for row in matches:
        if row["match_id"] in conflicts:
            row.update(confidence="Low", confidence_reason="Conflicting field in independent scorecard audit")
        elif row["confidence"] == "High":
            verified.add(row["match_id"])
    coverage = list(coverage_rows(matches, countries, schedules, published_coverage, verified - conflicts, gaps))
    correlations = list(correlation_rows(matches, innings))
    stamp = utc_stamp(run_time)
    tables = {"competitions": list(competitions(matches)), "matches": matches, "innings": innings,
              "coverage": coverage, "correlations": correlations, "accuracy_audit": audit}
    summary = summary_text(matches, coverage, audit, correlations, stamp, cache.warnings)
    manifest = {"built_at_utc": stamp, "row_counts": {name: len(rows) for name, rows in tables.items()},
                "audit": accuracy_stats(audit), "accuracy_target": [.8, .9], "source_warnings": sorted(cache.warnings),
                "licenses": {"Cricsheet": "ODC-BY-1.0", "UN M49": "United Nations Statistics Division"}}
    snapshot = publish(args.output, tables, summary, manifest, run_time)
    print(f"Published {len(matches):,} matches and {len(innings):,} innings to {snapshot}", flush=True)
    for warning in cache.warnings:
        print(f"Source: {warning}", file=sys.stderr)


if __name__ == "__main__":
    main()
