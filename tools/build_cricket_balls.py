"""Extract every white-ball delivery from the Cricsheet archive into compact arrays.

Run once after the archive is refreshed:  python tools/build_cricket_balls.py
Output: data/real/cricket_sim/balls.npz and matches.json. Local files only.
"""
import json
import sys
from datetime import date
from multiprocessing import Pool
from pathlib import Path
from zipfile import ZipFile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ZIP = ROOT / "data/raw/cricket/all_json.zip"
OUT = ROOT / "data/real/cricket_sim"
BOWLER_WICKETS = {"bowled", "caught", "caught and bowled", "lbw", "stumped", "hit wicket"}
NOT_OUT = {"retired hurt", "retired not out", "obstructing the field (non-dismissal)"}
FORMATS = {10: 0, 20: 1, 50: 2}  # scheduled overs -> format code (T10, T20, one-day)
COLUMNS = ("inn", "over", "wk", "runs_before", "target", "bat", "bowl", "out", "total", "bat_runs", "pos")


def outcome(ball):
    extras = ball.get("extras", {})
    kinds = [w["kind"] for w in ball.get("wickets", []) if w["kind"] not in NOT_OUT]
    if kinds:
        return 6 if kinds[0] in BOWLER_WICKETS else 7
    if extras.get("wides"):
        return 8
    if extras.get("noballs"):
        return 9
    if extras.get("byes") or extras.get("legbyes"):
        return 10
    return (0, 1, 2, 3, 4, 4, 5)[min(ball["runs"]["batter"], 6)]


def parse(document, source_id):
    info = document["info"]
    fmt = FORMATS.get(info.get("overs"))
    if fmt is None or info.get("balls_per_over", 6) != 6 or info["match_type"] not in ("T20", "IT20", "ODI", "ODM"):
        return None
    teams = info["teams"]
    people = info.get("registry", {}).get("people", {})
    xi = {team: [people.get(name) for name in info.get("players", {}).get(team, [])] for team in teams}
    if any(len(v) < 11 or None in v for v in xi.values()):
        return None
    names, local = {}, {}
    for name, pid in people.items():
        names[pid] = name
    rows = []
    summary = []
    innings = [i for i in document.get("innings", []) if not i.get("super_over") and not i.get("forfeited")][:2]
    for number, inning in enumerate(innings, 1):
        target = (inning.get("target") or {}).get("runs") or (summary[0]["runs"] + 1 if summary else 0)
        runs = wickets = legal = 0
        order = {}
        for over in inning.get("overs", []):
            for ball in over["deliveries"]:
                batter, bowler = people.get(ball["batter"]), people.get(ball["bowler"])
                for name in (ball["batter"], ball.get("non_striker")):
                    order.setdefault(people.get(name), len(order) + 1)
                kind = outcome(ball)
                if batter is not None and bowler is not None and over["over"] < info["overs"] and wickets < 10:
                    rows.append((number, over["over"], wickets, min(runs, 32000), min(target, 32000),
                                 local.setdefault(batter, len(local)), local.setdefault(bowler, len(local)),
                                 kind, min(ball["runs"]["total"], 100), min(ball["runs"]["batter"], 100),
                                 order[batter]))
                runs += ball["runs"]["total"]
                wickets += kind in (6, 7)
                legal += kind not in (8, 9)
        summary.append({"team": inning["team"], "runs": runs, "wickets": wickets, "balls": legal})
    if not rows:
        return None
    outcome_info = info.get("outcome", {})
    toss = info.get("toss", {})
    event = info.get("event", {})
    meta = {
        "id": source_id, "date": info["dates"][0], "fmt": fmt, "gender": info.get("gender", "male"),
        "intl": info.get("team_type") == "international", "event": event.get("name", ""),
        "venue": info.get("venue", ""), "city": info.get("city", ""), "teams": teams,
        "xi": [xi[t] for t in teams], "toss_winner": toss.get("winner", ""), "toss_decision": toss.get("decision", ""),
        "winner": outcome_info.get("winner", ""), "adjusted": bool(outcome_info.get("method")),
        "result": outcome_info.get("result", ""), "innings": summary,
        "players": sorted(local, key=local.get), "names": {pid: names[pid] for pid in local},
        "all_names": {pid: names[pid] for team in xi.values() for pid in team},
    }
    return meta, np.array(rows, dtype=np.int16)


def work(names):
    found = []
    with ZipFile(ZIP) as archive:
        for name in names:
            source_id = Path(name).stem
            try:
                parsed = parse(json.loads(archive.read(name)), source_id)
            except (KeyError, ValueError, TypeError, IndexError):
                parsed = None
            if parsed:
                found.append(parsed)
    return found


def main():
    with ZipFile(ZIP) as archive:
        names = sorted(n for n in archive.namelist() if n.endswith(".json") and Path(n).stem.isdecimal())
    chunks = [names[i::48] for i in range(48)]
    with Pool(10) as pool:
        parsed = [item for chunk in pool.map(work, chunks) for item in chunk]
    parsed.sort(key=lambda item: (item[0]["date"], item[0]["id"]))
    players, player_names, matches, blocks = {}, {}, [], []
    for index, (meta, rows) in enumerate(parsed):
        for pid in [*meta["players"], *meta["xi"][0], *meta["xi"][1]]:
            players.setdefault(pid, len(players))
        player_names.update(meta.pop("all_names"))
        player_names.update(meta.pop("names"))
        remap = np.array([players[pid] for pid in meta.pop("players")], dtype=np.int32)
        block = {name: rows[:, i] for i, name in enumerate(COLUMNS)}
        block["bat"], block["bowl"] = remap[rows[:, 5]], remap[rows[:, 6]]
        block["match"] = np.full(len(rows), index, dtype=np.int32)
        blocks.append(block)
        meta["xi"] = [[players[pid] for pid in side] for side in meta["xi"]]
        meta["day"] = date.fromisoformat(meta["date"]).toordinal()
        matches.append(meta)
    small = {"inn", "over", "wk", "out", "total", "bat_runs", "pos"}
    arrays = {name: np.concatenate([b[name] for b in blocks]).astype(
        np.int8 if name in small else np.int32 if name in ("bat", "bowl", "match") else np.int16)
        for name in (*COLUMNS, "match")}
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT / "balls.npz", **arrays)
    ordered = sorted(players, key=players.get)
    (OUT / "matches.json").write_text(json.dumps({
        "built_from": ZIP.name, "archive_mtime_ns": ZIP.stat().st_mtime_ns,
        "players": ordered, "player_names": [player_names[pid] for pid in ordered], "matches": matches,
    }), encoding="utf-8")
    print(f"{len(matches)} matches, {len(arrays['out'])} deliveries, {len(players)} players -> {OUT}")


if __name__ == "__main__":
    sys.exit(main())
