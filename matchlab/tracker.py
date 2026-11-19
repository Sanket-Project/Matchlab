"""Prediction log and track record.

Every pre-match forecast is saved before the match starts and graded against the real
result afterwards, so the dashboard can show how far its numbers deserve to be trusted.
Live checks are appended to a per-match timeline. One local JSON file.
"""
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import calibration
from .cricket_sim import team_key

FILE = "data/local/predictions.json"
_LOCK = threading.Lock()
PRE_MATCH_WINDOW = timedelta(minutes=15)
CHECKPOINT_TOLERANCE = timedelta(minutes=2)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def start_time(fixture):
    try:
        start = datetime.fromisoformat(str(fixture.get("start")).replace("Z", "+00:00"))
        return start if start.tzinfo is not None else None
    except ValueError:
        return None


def at_checkpoint(start, now):
    return start is not None and PRE_MATCH_WINDOW - CHECKPOINT_TOLERANCE <= start - now <= PRE_MATCH_WINDOW


def _read(root):
    try:
        from . import supabase_db
        db_preds = supabase_db.get_all_predictions()
        if db_preds:
            return db_preds
    except Exception:
        pass
    try:
        data = json.loads((Path(root) / FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(root, data):
    try:
        from . import supabase_db
        for mid, entry in list(data.items())[-10:]:
            sport = entry.get("fixture", {}).get("sport") or (entry.get("pre", {}).get("sport")) or "cricket"
            supabase_db.save_prediction(mid, sport, entry)
    except Exception:
        pass
    try:
        path = Path(root) / FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(data, indent=1), encoding="utf-8")
        temporary.replace(path)
    except Exception:
        pass


def _win(team):
    """Win chance as shown, plus the model's own number when calibration changed it."""
    return {"win": team["win"]} | ({"win_model": team["win_model"]} if "win_model" in team else {})


def _compact(forecast):
    if forecast.get("sport") == "tennis":
        return {"saved_at": _now(), "sport": "tennis", "stage": forecast["stage"], "format": forecast["format"], "lineups_confirmed": True,
                "teams": [{"name": t["name"]} | _win(t) for t in forecast["teams"]], "set_score": forecast["set_scores"][0]}
    return {"saved_at": _now(), "stage": forecast["stage"], "format": forecast["format"],
            "lineups_confirmed": all(t["lineup_confirmed"] for t in forecast["teams"]),
            "teams": [{"name": t["name"]} | _win(t) | {"first_innings": t["first_innings"], "wickets_taken": t["wickets_taken"],
                       "batters": [{"name": b["name"], "runs": b["runs"], "top": b["top"]} for b in t["batters"][:3]],
                       "bowlers": [{"name": b["name"], "wickets": b["wickets"], "top": b["top"]} for b in t["bowlers"][:3]]}
                      for t in forecast["teams"]]}


def _cricket_snapshot(forecast, at):
    return {key: forecast[key] for key in ("teams", "stage", "format", "toss", "venue", "marks") if key in forecast} | {
        "saved_at": at, "saved_before_start": True,
        "lineups_confirmed": all(t["lineup_confirmed"] for t in forecast["teams"]),
    }


def _append_over(timeline, current):
    innings, runs, wickets, balls = current["position"]
    if timeline:
        last = timeline[-1]
        previous_innings, _, _, previous_balls = last["position"]
        if (innings, balls) < (previous_innings, previous_balls):
            return
        if current["position"] == last["position"] and last.get("target") == current.get("target"):
            return
        if innings == previous_innings and (balls + 5) // 6 == (previous_balls + 5) // 6:
            timeline.pop()
    previous = timeline[-1] if timeline else None
    note = "First live update." if previous is None else "New innings."
    if previous and innings == previous["position"][0]:
        _, prev_runs, prev_wickets, prev_balls = previous["position"]
        swing = round(100 * (current["win"] - previous["win"]))
        interval = ("This over" if balls - prev_balls == 6 and balls % 6 == 0
                    else f"Since {prev_balls // 6}.{prev_balls % 6} overs")
        note = (f"{interval} · {runs - prev_runs} runs, {wickets - prev_wickets} wickets. "
                f"Projected total {current['projected'] - previous['projected']:+d} runs. "
                f"{current['batting']} win chance {swing:+d} points.")
    timeline.append({**current, "note": note})


def cricket_overs(timeline):
    """Roll up older ball-level records into the same over format."""
    overs = []
    for row in timeline:
        _append_over(overs, row)
    return overs


def _cricket_update(timeline, live, at):
    _append_over(timeline, {"at": at, "position": [live[key] for key in ("innings", "runs", "wickets", "balls")],
                            "score": live["score"], "batting": live["batting"], "target": live.get("target"),
                            "projected": live["projected"]["mean"], "win": live["win"][live["batting_index"]],
                            "win_by_team": live["win"]})
    del timeline[:-120]


def record(root, fixture, forecast):
    """Save the forecast while the match has not started; append live checks once it has.
    Returns the stored entry (pre-match forecast and timeline) for the page."""
    if not forecast.get("supported"):
        return None
    with _LOCK:
        data = _read(root)
        entry = data.setdefault(fixture["id"], {"fixture": {}, "timeline": []})
        entry["fixture"].update(fixture)
        state = forecast["intel"]["state"]
        tennis = forecast.get("sport") == "tennis"
        at = _now()
        now = datetime.fromisoformat(at)
        start = start_time(fixture)
        before_start = state == "pre" and (tennis or (start and now < start))
        if not tennis and before_start and not (entry.get("pre") or {}).get("at_checkpoint"):
            entry["pre"] = _cricket_snapshot(forecast, at)
            entry["pre"]["at_checkpoint"] = at_checkpoint(start, now)
        elif "pre" not in entry or (tennis and before_start):
            entry["pre"] = _compact(forecast)
            entry["pre"]["saved_before_start"] = bool(before_start)
        live = forecast.get("live")
        if live and tennis:
            last = entry["timeline"][-1] if entry["timeline"] else None
            if not last or list(last["position"]) != live["position"]:
                swing = round(100 * (live["win"][0] - last["win"])) if last else 0
                first = forecast["teams"][0]["name"]
                entry["timeline"].append({"at": _now(), "position": live["position"], "score": live["score"], "batting": first, "projected": None,
                                          "win": live["win"][0], "note": f"{first} win chance {swing:+d} points since the last check." if last else "First live check."})
                entry["timeline"] = entry["timeline"][-60:]
        elif live:
            _cricket_update(entry["timeline"], live, at)
        _write(root, data)
        return entry


def grade(root, match_id, intel):
    """Grade a finished match from ESPN's final scorecard. Returns the result or None."""
    if not intel or not intel.get("ok") or intel.get("state") != "post":
        return None
    with _LOCK:
        data = _read(root)
        entry = data.get(match_id)
        if not entry or "pre" not in entry or "result" in entry:
            return (entry or {}).get("result")
        pre = entry["pre"]
        mine = {team_key(t["name"]): t for t in pre["teams"]}
        teams = [t for t in intel["teams"] if team_key(t["name"]) in mine]
        if len(teams) != 2:
            return None
        winner = next((t["name"] for t in teams if t["winner"]), None)
        result = {"graded_at": _now(), "status": intel.get("status_text"), "winner": winner,
                  "saved_before_start": pre.get("saved_before_start", False), "stage": pre["stage"]}
        if winner:
            favourite = max(pre["teams"], key=lambda t: t["win"])
            result["winner_pick"] = {"pick": favourite["name"], "probability": favourite["win"],
                                     "correct": team_key(favourite["name"]) == team_key(winner)}
            before = [c for name, c in (entry.get("ai") or {}).items() if not name.startswith("live") and c.get("win")]
            if before:       # the last AI check made before the start, graded on its own adjusted number
                check = max(before, key=lambda c: c.get("at") or "")
                first = pre["teams"][0]["name"] if check["win"][0] >= 0.5 else pre["teams"][1]["name"]
                result["ai_pick"] = {"pick": first, "probability": max(check["win"]), "shift": check["shift"],
                                     "correct": team_key(first) == team_key(winner)}
        innings = sorted(((line["period"], t) for t in teams for line in t["innings"]), key=lambda x: x[0])
        if innings:
            first = innings[0][1]
            line = next(l for l in first["innings"] if l["period"] == innings[0][0])
            predicted = mine[team_key(first["name"])]["first_innings"]
            result["first_innings"] = {"team": first["name"], "actual": line["runs"], "predicted": predicted["mean"],
                                       "low": predicted["low"], "high": predicted["high"],
                                       "in_range": predicted["low"] <= line["runs"] <= predicted["high"]}
        picks = []
        for t in teams:
            forecast_team = mine[team_key(t["name"])]
            runs = {p["name"]: sum(s.get("runs", 0) for s in p["stats"].values() if s.get("batted")) for p in t["xi"]}
            wickets = {p["name"]: sum(s.get("wickets", 0) for s in p["stats"].values() if s.get("bowled")) for p in t["xi"]}
            for kind, actual, listed in (("top_batter", runs, forecast_team["batters"][:3]), ("top_bowler", wickets, forecast_team["bowlers"][:3])):
                if not actual or max(actual.values()) <= 0 or not listed:
                    continue
                best = max(actual.values())
                leaders = [name for name, value in actual.items() if value == best]
                named = [row["name"] for row in listed]
                if not any(name in actual for name in named):
                    continue   # names could not be lined up with the scorecard
                picks.append({"team": t["name"], "kind": kind, "pick": named[0], "actual": leaders, "value": best,
                              "correct": named[0] in leaders, "in_top3": any(name in leaders for name in named)})
        result["picks"] = picks
        entry["result"] = result
        _write(root, data)
        return result


def ai_checks(root, match_id):
    """{checkpoint: check} of AI second opinions saved for a match."""
    return (_read(root).get(match_id) or {}).get("ai") or {}


def ai_save(root, fixture, checkpoint, check):
    with _LOCK:
        data = _read(root)
        entry = data.setdefault(fixture["id"], {"fixture": {k: fixture.get(k) for k in ("id", "team", "opponent", "tournament", "start", "espn")},
                                                "timeline": []})
        entry.setdefault("ai", {})[checkpoint] = check
        _write(root, data)


def grade_tennis(root, match_id, intel):
    """Grade a finished tennis match from the feed's final set scores."""
    if not intel or not intel.get("ok") or intel.get("state") != "post" or intel.get("winner") not in (0, 1):
        return None
    with _LOCK:
        data = _read(root)
        entry = data.get(match_id)
        if not entry or "pre" not in entry or "result" in entry:
            return (entry or {}).get("result")
        pre = entry["pre"]
        winner = pre["teams"][intel["winner"]]["name"]
        favourite = max(pre["teams"], key=lambda t: t["win"])
        sets = [sum(1 for s in intel["sets"] if (s["a"] > s["b"]) == (side == 0) and s["a"] != s["b"]) for side in (0, 1)]
        result = {"graded_at": _now(), "status": intel.get("note") or intel.get("status"), "winner": winner, "sport": "tennis",
                  "saved_before_start": pre.get("saved_before_start", False), "stage": pre["stage"],
                  "winner_pick": {"pick": favourite["name"], "probability": favourite["win"], "correct": favourite["name"] == winner},
                  "set_score": {"pick": pre["set_score"]["score"], "pick_winner": pre["set_score"]["winner"], "actual": f"{sets[0]}-{sets[1]}",
                                "correct": pre["set_score"]["score"] == f"{sets[0]}-{sets[1]}"}, "picks": []}
        before = [c for name, c in (entry.get("ai") or {}).items() if not name.startswith("live") and c.get("win")]
        if before:
            check = max(before, key=lambda c: c.get("at") or "")
            first = pre["teams"][0]["name"] if check["win"][0] >= 0.5 else pre["teams"][1]["name"]
            result["ai_pick"] = {"pick": first, "probability": max(check["win"]), "shift": check["shift"], "correct": first == winner}
        entry["result"] = result
        _write(root, data)
        return result


def pending(root):
    """Tracked matches that have a pre-match forecast, an ESPN link and no result yet."""
    return [(match_id, entry["fixture"]) for match_id, entry in _read(root).items()
            if "pre" in entry and "result" not in entry and (entry["fixture"].get("espn") or {}).get("event")
            and entry["pre"].get("sport") != "tennis"]


def entry(root, match_id):
    return _read(root).get(match_id)


def record_race(root, forecast):
    start = start_time(forecast)
    saved_at = _now()
    if forecast["completed"] or not start or datetime.fromisoformat(saved_at) >= start:
        return
    race_id = f"f1-{forecast['race_id']}"
    favourite = forecast["drivers"][0]
    with _LOCK:
        data = _read(root)
        previous = data.get(race_id, {})
        if previous.get("result") or (previous.get("pre", {}).get("stage") == "post_qualifying"
                                      and forecast["stage"] != "post_qualifying"):
            return
        data[race_id] = {
            "fixture": {"id": race_id, "sport": "f1", "team": forecast["name"], "start": forecast["start"],
                        "season": forecast["season"], "round": forecast["round"]},
            "pre": {"sport": "f1", "stage": forecast["stage"], "saved_at": saved_at, "saved_before_start": True,
                    "teams": [{"name": favourite["driver"], "win": favourite["win"]}]},
        }
        _write(root, data)


def pending_races(root):
    now = datetime.now(timezone.utc)
    return [item["fixture"] for item in _read(root).values()
            if item.get("pre", {}).get("sport") == "f1" and not item.get("result")
            and (start := start_time(item["fixture"])) and now >= start + timedelta(hours=2)]


def grade_race(root, match_id, winner):
    with _LOCK:
        data = _read(root)
        item = data.get(match_id)
        if not item or item.get("result"):
            return
        favourite = item["pre"]["teams"][0]
        item["result"] = {"graded_at": _now(), "winner": winner, "saved_before_start": True,
                          "winner_pick": {"pick": favourite["name"], "probability": favourite["win"],
                                          "correct": team_key(favourite["name"]) == team_key(winner)}}
        _write(root, data)


def graded_pairs(root, sport):
    """(favourite's raw model win chance, favourite won) for each counted, graded forecast of a sport."""
    pairs = []
    for item in _read(root).values():
        pre, result = item.get("pre"), item.get("result")
        if (pre and result and result.get("saved_before_start") and "winner_pick" in result
                and pre.get("sport", "cricket") == sport and len(pre.get("teams") or []) == 2):
            pairs.append((max(t.get("win_model", t["win"]) for t in pre["teams"]), bool(result["winner_pick"]["correct"])))
    return pairs


def track_record(root):
    rows = []
    for match_id, item in _read(root).items():
        if "pre" not in item:
            continue
        result = item.get("result")
        rows.append({"id": match_id, "fixture": item["fixture"], "stage": item["pre"]["stage"], "saved_at": item["pre"]["saved_at"],
                     "saved_before_start": item["pre"].get("saved_before_start", False),
                     "sport": item["pre"].get("sport", "cricket"),
                     "teams": [{"name": t["name"], "win": t["win"], "first_innings": (t.get("first_innings") or {}).get("mean")} for t in item["pre"]["teams"]],
                     "result": result})
    rows.sort(key=lambda row: row["fixture"].get("start") or "", reverse=True)
    summary = _record_summary(rows)
    summary["calibration"] = {sport: calibration.fit(graded_pairs(root, sport)) for sport in ("cricket", "tennis")}
    groups = {}
    for sport in ("cricket", "tennis", "f1"):
        group = [row for row in rows if row["sport"] == sport]
        groups[sport] = {"summary": _record_summary(group), "matches": group[:100]}
    return {"summary": summary, "matches": rows[:100], "sports": groups}


def _record_summary(rows):
    graded = [row["result"] for row in rows if row["result"] and row["result"].get("saved_before_start")]

    def rate(items):
        return {"n": len(items), "correct": sum(items)} if items else {"n": 0, "correct": 0}
    winners = [r["winner_pick"]["correct"] for r in graded if "winner_pick" in r]
    firsts = [r["first_innings"] for r in graded if "first_innings" in r]
    picks = [p for r in graded for p in r.get("picks", [])]
    return {
        "saved": len(rows), "graded": len(graded),
        "waiting": sum(1 for row in rows if row["saved_before_start"] and not row["result"]),
        "winner": rate(winners),
        "ai_winner": rate([r["ai_pick"]["correct"] for r in graded if "ai_pick" in r]),
        "first_innings": {"n": len(firsts), "mean_error": round(sum(abs(f["actual"] - f["predicted"]) for f in firsts) / len(firsts), 1) if firsts else None,
                          "in_range": sum(f["in_range"] for f in firsts)},
        "top_batter": rate([p["correct"] for p in picks if p["kind"] == "top_batter"]),
        "top_bowler": rate([p["correct"] for p in picks if p["kind"] == "top_bowler"]),
        "set_score": rate([r["set_score"]["correct"] for r in graded if "set_score" in r]),
    }
