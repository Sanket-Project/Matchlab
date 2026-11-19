SPORTS = {
    "football": {"name": "Football", "unit": "goals", "player_unit": "goals", "side": "Team", "threat": "Successful take-ons per duel", "draw": True},
    "cricket": {"name": "Cricket", "unit": "runs", "player_unit": "runs", "side": "Team", "threat": "Boundaries per ball faced", "draw": True},
    "tennis": {"name": "Tennis", "unit": "sets", "player_unit": "aces", "side": "Competitor", "threat": "Points won per point played", "draw": False},
    "badminton": {"name": "Badminton", "unit": "games", "player_unit": "points", "side": "Competitor", "threat": "Rallies won per rally played", "draw": False},
    "baseball": {"name": "Baseball", "unit": "runs", "player_unit": "hits", "side": "Team", "threat": "Hits per plate appearance", "draw": False},
    "rugby": {"name": "Rugby", "unit": "points", "player_unit": "points", "side": "Team", "threat": "Line breaks per carry", "draw": True},
}
for sport in SPORTS.values():
    sport["kind"] = "match"
SPORTS["f1"] = {"name": "Formula 1", "kind": "race"}
