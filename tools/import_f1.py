"""Convert the retained Jolpica CSV dump to local Grand Prix and sprint tables."""
import csv
import hashlib
import io
import json
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "data/raw/f1/jolpica-f1-csv.zip"
OUTPUT = ROOT / "data/real/f1"
SOURCE = "https://github.com/jolpica/jolpica-f1/blob/main/docs/database_dumps.md"
STATUS = {"0": "Finished", "1": "Lapped", "10": "Incident", "11": "Retired", "20": "Disqualified",
          "30": "Did not start", "40": "Did not qualify", "41": "Did not prequalify"}
MECHANICAL = ("engine", "gearbox", "transmission", "hydraulic", "electrical", "power unit", "power loss", "mechanical",
              "brake", "clutch", "fuel", "cooling", "overheat", "oil", "exhaust", "turbo", "driveshaft", "battery",
              "water leak", "steering", "differential", "alternator", "suspension", "puncture", "technical")


def dnf_type(row):
    if row["status"] == "10":
        return "incident"
    if row["status"] == "11" and any(reason in row["detail"].lower() for reason in MECHANICAL):
        return "mechanical"
    return "unknown" if row["status"] == "11" else ""


def import_f1(archive=ARCHIVE, folder=OUTPUT):
    with zipfile.ZipFile(archive) as z:
        def table(name):
            with z.open(f"formula_one_{name}.csv") as file:
                return list(csv.DictReader(io.TextIOWrapper(file, encoding="utf-8-sig")))

        seasons = {r["id"]: int(r["year"]) for r in table("season")}
        rounds = {r["id"]: r for r in table("round") if seasons[r["season_id"]] >= 2014 and r["is_cancelled"] == "f"}
        circuits = {r["id"]: r["name"] for r in table("circuit")}
        drivers = {r["id"]: r for r in table("driver")}
        teams = {r["id"]: r for r in table("team")}
        team_drivers = {r["id"]: r for r in table("teamdriver")}
        round_entries = {r["id"]: r for r in table("roundentry") if r["round_id"] in rounds}
        sessions = defaultdict(list)
        for r in table("session"):
            if r["round_id"] in rounds and r["is_cancelled"] == "f" and r["timestamp"]:
                r["start"] = datetime.fromisoformat(r["timestamp"]).isoformat()
                sessions[r["round_id"]].append(r)
        session_ids = {s["id"] for group in sessions.values() for s in group if s["type"] in {"R", "SR", "Q1", "Q2", "Q3", "QA", "QB", "QO"}}
        results = defaultdict(list)
        for r in table("sessionentry"):
            if r["session_id"] in session_ids and r["position"]:
                results[r["session_id"]].append(r)

    races, entries, sprints, rosters = [], [], [], []

    def entrant(round_entry):
        team_driver = team_drivers[round_entry["team_driver_id"]]
        driver, team = drivers[team_driver["driver_id"]], teams[team_driver["team_id"]]
        return dict(driver_id=driver["reference"], source_driver_id=driver["api_id"], driver=f"{driver['forename']} {driver['surname']}",
                    constructor_id=team["reference"], source_constructor_id=team["api_id"], constructor=team["name"])

    def classification(row):
        return dict(finish=int(row["position"]), classified=int(row["is_classified"] == "t"),
                    status=STATUS.get(row["status"], "Unknown"), status_detail=row["detail"],
                    dnf_type=dnf_type(row), points=row["points"])

    for race_id, event in rounds.items():
        group = sessions[race_id]
        race = next((s for s in group if s["type"] == "R"), None)
        if race is None:
            continue
        season = seasons[event["season_id"]]
        qualifying = [s for s in group if s["type"] in {"Q1", "Q2", "Q3", "QA", "QB", "QO"} and s["start"] <= race["start"]]
        qual_positions = {}
        for kind in ("Q1", "Q2", "Q3", "QB", "QO", "QA"):
            for s in qualifying:
                if s["type"] == kind:
                    qual_positions.update({r["round_entry_id"]: r["position"] for r in results[s["id"]]})
        # The delayed dump may include future fixtures and partial weekend data.
        final = results[race["id"]] if race["completed_laps"] or any(r["position"] == "1" and r["status"] in ("0", "1") for r in results[race["id"]]) else []
        race_start = datetime.fromisoformat(race["start"])
        qual_start = max((s["start"] for s in qualifying), default="")
        races.append(dict(race_id=race_id, source_round_id=event["api_id"], season=season, round=event["number"], name=event["name"],
                          circuit=circuits[event["circuit_id"]], date=event["date"], start=race["start"],
                          weekend_start=min(s["start"] for s in group), qualifying_start=qual_start,
                          qualifying_date=qual_start[:10],
                          regulation_era=2026 if season >= 2026 else 2022 if season >= 2022 else 2014,
                          result_available=(race_start + timedelta(hours=6)).isoformat(), completed=int(bool(final))))
        for r in final:
            entries.append(dict(race_id=race_id, **entrant(round_entries[r["round_entry_id"]]), grid=r["grid"],
                                qualifying_position=qual_positions.get(r["round_entry_id"], ""), **classification(r)))
        for s in group:
            if s["type"] != "SR":
                continue
            available = (datetime.fromisoformat(s["start"]) + timedelta(hours=2)).isoformat()
            for r in results[s["id"]]:
                sprints.append(dict(race_id=race_id, **entrant(round_entries[r["round_entry_id"]]),
                                    available=available, **classification(r)))

    upcoming = {r["race_id"] for r in races if not r["completed"]}
    for r in round_entries.values():
        if r["round_id"] in upcoming:
            rosters.append(dict(race_id=r["round_id"], **entrant(r)))
    races.sort(key=lambda r: r["start"])
    completed = [r for r in races if r["completed"]]
    if not completed:
        raise ValueError("The Jolpica dump contains no completed Grands Prix from 2014 onward")
    folder.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, records, columns in (
        ("races.csv", races, races[0].keys()),
        ("entries.csv", entries, entries[0].keys()),
        ("sprints.csv", sprints, ("race_id", "driver_id", "source_driver_id", "driver", "constructor_id", "source_constructor_id", "constructor", "available",
                                  "finish", "classified", "status", "status_detail", "dnf_type", "points")),
        ("rosters.csv", rosters, ("race_id", "driver_id", "source_driver_id", "driver", "constructor_id", "source_constructor_id", "constructor")),
    ):
        path = folder / name
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()
            writer.writerows(records)
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    provenance = dict(source="Jolpica F1 public delayed CSV database dump (Ergast successor)", url=SOURCE,
                      license="CC BY-NC-SA 4.0 (noncommercial use)", sport="f1", synthetic=False,
                      archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(), files=files,
                      races=len(completed), entries=len(entries), sprints=len({r['race_id'] for r in sprints}),
                      earliest=completed[0]["date"], latest=completed[-1]["date"], limitations=[
                          "Completed Grands Prix from 2014 onward. Sprint results contribute only to prior form and standings.",
                          "The public dump is delayed. Upcoming driver fields use the listed entries or the latest available same-season field.",
                          "Jolpica combines mechanical and other retirements. Unspecified causes remain unknown.",
                          "A recorded grid of zero denotes a driver without a regular grid slot. Top ten is the points proxy.",
                      ])
    (folder / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(f"f1: {len(completed)} completed Grands Prix, {len(entries)} entries, {provenance['sprints']} sprints")


if __name__ == "__main__":
    import_f1()
