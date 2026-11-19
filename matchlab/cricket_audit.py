"""Fixture coverage and field-level comparisons with published references."""

from collections import Counter

from matchlab.cricket_archive import ALIASES, JURISDICTIONS, index_by, normalized
from matchlab.cricket_sources import COUNTRIES_URL, CRICSHEET_COVERAGE, ICC_MEMBERS


REQUIRED = {
    **{label: lambda row, name=name: row["league"] == name for label, name in ALIASES.items()
       if label in {"IPL", "BBL", "EPL", "Abu Dhabi League"}},
    "T10": lambda row: row["format"] == "T10",
    "International cricket": lambda row: row["competition_level"] == "international",
}


def fixture_key(match):
    return (match["start_date_local"], frozenset(team_key(match[key]) for key in ("team_a", "team_b")))


def audit_records(matches, innings, references):
    by_fixture = index_by(matches, fixture_key)
    scores = index_by(innings, lambda row: row["match_id"])
    for ref, ref_scores in references:
        found = [m for m in by_fixture[fixture_key(ref)]
                 if m["format"] == ref["format"] and m["source"] != ref["source"]
                 and m["team_category"] == ref["team_category"]]
        base = {"reference_url": ref["source_url"], "reference_id": ref["match_id"],
                "competition": ref["league"] or ref["tournament"], "season": ref["season"],
                "format": ref["format"], "team_category": ref["team_category"]}
        if len(found) != 1:
            yield dict(base, field="fixture_link", status="unlinked", expected="One unique source match",
                       observed=len(found))
            continue
        match = found[0]
        base.update(match_id=match["match_id"], source_url=match["source_url"])
        fields = ("result", "winner", "result_margin", "batting_first", "toss_winner", "toss_decision")
        for field in fields:
            if ref.get(field):
                yield comparison(base, field, ref[field], match.get(field, ""))
        for inning in ref_scores:
            scored = [item for item in scores[match["match_id"]]
                      if team_key(item["batting_team"]) == team_key(inning["batting_team"])
                      and (not inning["innings_number"] or item["innings_number"] == inning["innings_number"])]
            for field in ("runs", "wickets", "legal_balls"):
                if inning.get(field, "") != "":
                    observed = scored[0].get(field, "") if len(scored) == 1 else ""
                    yield comparison(base, f"{inning['batting_team']} innings {inning['innings_number']} {field}",
                                     inning[field], observed)


def team_key(value):
    return normalized(value).removesuffix(" men").removesuffix(" women")


def comparison(base, field, expected, observed):
    if isinstance(expected, str) and isinstance(observed, str):
        same = team_key(expected) == team_key(observed)
    else:
        same = expected == observed
    status = "missing" if observed == "" else "correct" if same else "conflict"
    return dict(base, field=field, expected=expected, observed=observed, status=status)


def coverage_counts(rows, verified):
    return {
        "matches_captured": len(rows),
        "results_verified": sum(row["match_id"] in verified and bool(row["result"]) for row in rows),
    }


def coverage_rows(matches, countries, schedules, published_coverage, verified, gaps=()):
    grouped = index_by(matches, lambda row: (row["competition_id"], row["season"], row["format"], row["team_category"]))
    for key, cohort in sorted(grouped.items()):
        first = cohort[0]
        competition_id, season, match_format, category = key
        schedule = schedules.get(key)
        counts = coverage_counts(cohort, verified)
        expected, schedule_url = schedule or ("", "")
        captured = counts["matches_captured"]
        status = "schedule_captured" if expected == captured else "partial" if schedule else "denominator_unknown"
        if schedule and captured > expected:
            status = "schedule_mismatch"
        yield dict(counts, scope="competition_season", country_or_region=first["country_or_region"],
                   competition_id_or_requested_label=competition_id or "Unnamed source event",
                   competition_name=first["league"] or first["tournament"], season=season, format=match_format,
                   team_category=category, expected_matches=expected, coverage_status=status,
                   coverage_fraction=captured / expected if expected and captured <= expected else "",
                   gap_reason="" if status == "schedule_captured" else "No complete season denominator" if not schedule
                   else "Match count differs from published schedule",
                   source_urls=" | ".join(sorted({m["source_url"] for m in cohort} | ({schedule_url} if schedule_url else set()))),
                   confidence="Medium" if schedule else "Low")

    archive = index_by((row for row in matches if row["source"] == "Cricsheet"), lambda row: row["league"])
    for event, publisher_count, expected in published_coverage:
        rows = archive[event]
        if publisher_count != len(rows):
            continue  # The publisher and retained archive describe different snapshots or event groupings.
        yield dict(coverage_counts(rows, verified), scope="archive_coverage_window",
                   competition_id_or_requested_label=event, competition_name=event,
                   country_or_region=JURISDICTIONS.get(event, ""), expected_matches=expected,
                   coverage_fraction=len(rows) / expected if expected else "",
                   coverage_status="partial" if len(rows) < expected else "publisher_window_captured",
                   gap_reason="Cricsheet coverage window only",
                   source_urls=CRICSHEET_COVERAGE, confidence="Medium")

    for label, condition in REQUIRED.items():
        rows = [row for row in matches if condition(row)]
        yield dict(coverage_counts(rows, verified), scope="requested", competition_id_or_requested_label=label,
                   competition_name=ALIASES.get(label, label), coverage_status="partial" if rows else "unresolved",
                   gap_reason="Some seasons, events, or local sources may be missing" if rows else "No match feed imported",
                   source_urls=" | ".join(sorted({m["source_url"] for m in rows})),
                   confidence="Medium" if rows else "Unknown")

    for title, url in gaps:
        yield dict(scope="competition_gap", competition_id_or_requested_label=title or url,
                   competition_name=title, matches_captured=0, results_verified=0,
                   coverage_status="source_needed", gap_reason="A series was listed without usable fixture rows",
                   source_urls=url, confidence="Unknown")

    by_jurisdiction = index_by(matches, lambda row: row["country_or_region"])
    for name in ("England", "Wales"):
        by_jurisdiction[name].extend(by_jurisdiction["England and Wales"])
    jurisdictions = {**countries, "ICC-EAW": "England and Wales", "ICC-SCO": "Scotland", "ICC-WI": "West Indies"}
    for code, name in sorted(jurisdictions.items(), key=lambda item: item[1]):
        domestic = [row for row in by_jurisdiction[name] if row["competition_level"] == "club"]
        yield dict(coverage_counts(domestic, verified), scope="jurisdiction",
                   country_or_region=name, country_code=code,
                   coverage_status="partial" if domestic else "source_needed",
                   gap_reason="Domestic records found. Full domestic inventory remains open." if domestic
                   else "No domestic feed imported for this jurisdiction",
                   source_urls=f"{COUNTRIES_URL} | {ICC_MEMBERS}", confidence="Low" if domestic else "Unknown")


def accuracy_stats(audit):
    counts = Counter(row["status"] for row in audit)
    checked = counts["correct"] + counts["conflict"]
    return dict(correct=counts["correct"], conflicts=counts["conflict"], checked=checked, missing=counts["missing"],
                unlinked=counts["unlinked"], accuracy=counts["correct"] / checked if checked else None,
                matches=len({row["match_id"] for row in audit if row["status"] in {"correct", "conflict"}}))
