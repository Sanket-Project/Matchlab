"""Descriptive breakdowns of recorded history by opponent and match context.

Plain counts and averages of results dated strictly before the cutoff. These
are observed records, not model outputs, and small samples are reported as
they are (the count is always included).
"""
from collections import defaultdict


def dimensions(ds):
    """Context columns this dataset actually records, with display labels."""
    cached = getattr(ds, "_split_dimensions", None)
    if cached is None:
        cached = []
        if any(m.get("surface") for m in ds.matches):
            cached.append({"key": "surface", "label": "Surface"})
        if any(m.get("ground") for m in ds.matches):
            # With a surface column the ground is a tournament (tennis).
            cached.append({"key": "ground", "label": "Tournament" if cached else "Ground"})
        ds._split_dimensions = cached
    return cached


def _ordered(groups, size):
    rows = list(groups.values())
    rows.sort(key=lambda r: (-r[size], r["key"]))
    return rows


def _player_groups(rows, key_of):
    groups = {}
    for p in rows:
        key = key_of(p)
        if not key:
            continue
        g = groups.setdefault(key, {"key": key, "appearances": 0, "total": 0.0, "best": 0.0, "last": ""})
        g["appearances"] += 1
        g["total"] += p["score"]
        g["best"] = max(g["best"], p["score"])
        g["last"] = max(g["last"], p["date"])
    for g in groups.values():
        g["average"] = g["total"] / g["appearances"]
    return _ordered(groups, "appearances")


def player_splits(ds, player, cutoff):
    """Selected player's scoring record across all sides they appeared for."""
    if not player:
        return None
    rows = [p for p in ds.players if p["player"] == player and p["date"] < cutoff]
    if not rows:
        return None
    result = {"player": player, "appearances": len(rows), "average": sum(p["score"] for p in rows) / len(rows),
              "by_opponent": _player_groups(rows, lambda p: p["opponent"]), "by_context": []}
    for dim in dimensions(ds):
        result["by_context"].append({**dim, "rows": _player_groups(rows, lambda p: ds.by_id[p["match_id"]].get(dim["key"], ""))})
    return result


def _pair_groups(rows, key_of):
    groups, meetings = {}, defaultdict(set)
    for r in rows:
        key = key_of(r)
        if not key:
            continue
        g = groups.setdefault(key, {"key": key, "meetings": 0, "opportunities": 0.0, "successes": 0.0, "score": 0.0, "last": ""})
        meetings[key].add(r["match_id"])
        for field in ("opportunities", "successes", "score"):
            g[field] += r[field]
        g["last"] = max(g["last"], r["date"])
    for key, g in groups.items():
        g["meetings"] = len(meetings[key])
        g["rate"] = g["successes"] / g["opportunities"] if g["opportunities"] else None
    return _ordered(groups, "opportunities")


def pair_splits(ds, player, other, cutoff):
    """Every recorded meeting of the selected player against the opposing player."""
    if not player or not other:
        return None
    rows = [r for r in ds.interactions if r["player"] == player and r["opponent_player"] == other and r["date"] < cutoff]
    if not rows:
        return None
    total = _pair_groups(rows, lambda r: "all")[0]
    result = {"player": player, "opponent_player": other, "total": {k: v for k, v in total.items() if k != "key"}, "by_context": []}
    for dim in dimensions(ds):
        result["by_context"].append({**dim, "rows": _pair_groups(rows, lambda r: ds.by_id[r["match_id"]].get(dim["key"], ""))})
    return result


def side_splits(ds, team, cutoff):
    """A side's win/loss and scoring record by each recorded context."""
    history = ds.history(team, cutoff)
    result = {"side": team, "matches": len(history), "by_context": []}
    for dim in dimensions(ds):
        groups = {}
        for h in history:
            key = ds.by_id[h["match_id"]].get(dim["key"], "")
            if not key:
                continue
            g = groups.setdefault(key, {"key": key, "matches": 0, "wins": 0, "draws": 0, "losses": 0, "scored": 0.0, "conceded": 0.0, "last": ""})
            g["matches"] += 1
            g[{"W": "wins", "D": "draws", "L": "losses"}[h["result"]]] += 1
            g["scored"] += h["score"]
            g["conceded"] += h["conceded"]
            g["last"] = max(g["last"], h["date"])
        for g in groups.values():
            g["win_rate"] = g["wins"] / g["matches"]
            g["average_scored"] = g.pop("scored") / g["matches"]
            g["average_conceded"] = g.pop("conceded") / g["matches"]
        result["by_context"].append({**dim, "rows": _ordered(groups, "matches")})
    return result


def build(ds, team, opponent, player, other, cutoff):
    return {"note": "Observed records before the prediction date, all seasons in the local data. Not model outputs.",
            "sides": [side_splits(ds, team, cutoff), side_splits(ds, opponent, cutoff)] if dimensions(ds) else [],
            "player": player_splits(ds, player, cutoff),
            "opponent_player": player_splits(ds, other, cutoff),
            "pair": pair_splits(ds, player, other, cutoff),
            "pair_reverse": pair_splits(ds, other, player, cutoff)}
