"""Shape AcesAPI tennis data (acesapi.com) for the match page. Pure local logic; no network access.

One check costs CREDITS: two player searches (1 each), a head-to-head (3) and a surface Elo list (2).
A free key carries 500 credits a month, metered in matchlab/budget.py as "acesapi".
"""
import unicodedata

SOURCE = "AcesAPI"
SOURCE_URL = "https://acesapi.com/"
CREDITS = 7
RATINGS_LIMIT = 200
SURFACES = {"hard": "hard", "clay": "clay", "grass": "grass", "carpet": "carpet"}
LEAGUES = {"atp": "tennis", "wta": "wta"}


def plain(name):
    text = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(text.replace("-", " ").split())


def surface(name):
    key = plain(name).split(" ")[0] if name else ""
    return SURFACES.get(key)


def search_term(name):
    """Surname is the most reliable search key ("Carlos Alcaraz" -> "alcaraz")."""
    words = plain(name).split()
    return words[-1] if words else ""


def pick_player(players, name):
    """The search hit whose full name matches; else the only hit sharing the surname; else None."""
    wanted = plain(name)
    players = [p for p in players or [] if p.get("player_id")]
    exact = [p for p in players if plain(p.get("name")) == wanted]
    if exact:
        return exact[0]
    surname = search_term(name)
    initial = wanted[:1]
    close = [p for p in players if plain(p.get("name")).split()[-1:] == [surname] and plain(p.get("name"))[:1] == initial]
    return close[0] if len(close) == 1 else None


def rating_for(ratings, player_id):
    for row in (ratings or {}).get("ratings") or []:
        if str(row.get("player_id")) == str(player_id):
            return {"rating": row.get("rating"), "rank": row.get("rank"), "matches": row.get("surface_matches")}
    return None


def elo_chance(a, b):
    return 1 / (1 + 10 ** ((b - a) / 400))


def shape(names, players, h2h, ratings, surface_name, checked_at):
    ids = [p["player_id"] if p else None for p in players]
    out = {"ok": True, "source": SOURCE, "source_url": SOURCE_URL, "checked_at": checked_at, "credits": CREDITS,
           "surface": surface_name, "players": []}
    for name, player in zip(names, players):
        out["players"].append({"name": name, "found": bool(player), "id": player.get("player_id") if player else None,
                               "rank": player.get("current_rank") if player else None,
                               "surface_elo": rating_for(ratings, player["player_id"]) if player else None})
    elos = [p["surface_elo"]["rating"] if p["surface_elo"] and isinstance(p["surface_elo"].get("rating"), (int, float)) else None
            for p in out["players"]]
    out["elo_win"] = round(elo_chance(*elos), 3) if None not in elos else None
    summary = (h2h or {}).get("summary") or {}
    if all(ids) and summary:
        wins = summary.get("wins") or {}
        on_surface = (summary.get("by_surface") or {}).get(surface_name) or {}
        out["h2h"] = {"matches": summary.get("matches") or 0, "wins": [wins.get(str(i), 0) for i in ids],
                      "surface_wins": [on_surface.get(str(i), 0) for i in ids],
                      "last": [{"date": (m.get("starts_at") or "")[:10], "round": m.get("round") or "", "surface": m.get("surface") or "",
                                "score": m.get("score") or "", "winner": names[ids.index(str(m.get("winner_id")))] if str(m.get("winner_id")) in ids else ""}
                               for m in ((h2h or {}).get("matches") or [])[:5]]}
    else:
        out["h2h"] = None
    missing = [p["name"] for p in out["players"] if not p["found"]]
    out["notes"] = ([f"AcesAPI could not match {' or '.join(missing)} by name."] if missing else []) + \
        ([f"Not in AcesAPI's top {RATINGS_LIMIT} {surface_name}-court Elo list: " + ", ".join(p["name"] for p in out["players"] if p["found"] and not p["surface_elo"]) + "."]
         if any(p["found"] and not p["surface_elo"] for p in out["players"]) else [])
    return out
