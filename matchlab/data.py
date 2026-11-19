import csv
import math
import hashlib
import json
from datetime import date
from pathlib import Path


def local_path(value, root):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Provide a local file or folder path")
    if "://" in value or value.startswith(("\\\\", "//")):
        raise ValueError("Only local disk paths are accepted; URLs and network shares are disabled")
    path = Path(value).expanduser()
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if str(path).startswith(("\\\\", "//")):
        raise ValueError("Network shares are disabled")
    return path


def number(value, field):
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{field} must be numeric") from None
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{field} must be finite and nonnegative")
    return result


def read_csv(path, columns, optional=False):
    if optional and not path.exists():
        return []
    if not path.is_file():
        raise ValueError(f"Missing data file: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not columns.issubset(set(reader.fieldnames or [])):
            raise ValueError(f"{path.name} requires columns: {', '.join(sorted(columns))}")
        rows = []
        for line, row in enumerate(reader, 2):
            if None in row or any(row.get(c) is None or not row[c].strip() for c in columns):
                raise ValueError(f"{path.name}, line {line}: missing or extra values")
            rows.append({k: v.strip() if v is not None else "" for k, v in row.items()})
            if len(rows) > 250_000:
                raise ValueError(f"{path.name} exceeds the 250,000 row local dashboard limit")
        return rows


class Dataset:
    def __init__(self, folder, sport):
        self.folder = folder
        self.synthetic = False
        provenance_file = folder / "provenance.json"
        self.provenance = json.loads(provenance_file.read_text(encoding="utf-8")) if provenance_file.exists() else {}
        self.file_hashes = {}
        for path in folder.glob("*.csv"):
            self.file_hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        for filename, expected in self.provenance.get("files", {}).items():
            if self.file_hashes.get(filename) != expected:
                raise ValueError(f"Dataset checksum mismatch: {folder / filename}. Restore/re-import the retained source or update its provenance after verifying intentional changes.")
        self.matches = read_csv(folder / "matches.csv", {"match_id", "date", "team", "opponent", "team_score", "opponent_score", "outcome"})
        if not self.matches:
            raise ValueError("matches.csv must contain at least one match")
        self.by_id = {}
        for row in self.matches:
            if row["match_id"] in self.by_id:
                raise ValueError(f"Duplicate match_id: {row['match_id']}; use one row per match")
            try:
                row["date"] = date.fromisoformat(row["date"]).isoformat()
                if row.get("pre_match_date"):
                    row["pre_match_date"] = date.fromisoformat(row["pre_match_date"]).isoformat()
                    if row["pre_match_date"] > row["date"]:
                        raise ValueError("pre_match_date cannot follow result availability")
            except ValueError:
                raise ValueError("Match dates must use YYYY-MM-DD") from None
            if row["team"] == row["opponent"]:
                raise ValueError("A side cannot play itself")
            if row["outcome"] not in ("team", "opponent", "draw"):
                raise ValueError("outcome must be team, opponent, or draw")
            if row["outcome"] == "draw" and not sport["draw"]:
                raise ValueError(f"Draws are not supported for {sport['name']}")
            for key in ("team_score", "opponent_score"):
                row[key] = number(row[key], key)
            if row.get("venue", "neutral") not in ("home", "away", "neutral"):
                raise ValueError("Match venue must be home, away or neutral")
            if sport.get("strict_scores"):
                a, b = row["team_score"], row["opponent_score"]
                if a != int(a) or b != int(b):
                    raise ValueError("Historical sport scores must be whole numbers")
                ceiling = sport.get("max_score")
                if ceiling and (max(a, b) != ceiling or min(a, b) >= ceiling):
                    raise ValueError(f"Completed {sport['name']} scores require a winner with {ceiling} {sport['unit']}")
                if sport["name"] != "Cricket":
                    expected = "team" if a > b else "opponent" if b > a else "draw"
                    if row["outcome"] != expected:
                        raise ValueError("Recorded outcome is inconsistent with the configured final-score target")
            self.by_id[row["match_id"]] = row
        self.matches.sort(key=lambda r: (r["date"], r["match_id"]))
        self.teams = sorted({m[k] for m in self.matches for k in ("team", "opponent")})
        self.players = read_csv(folder / "players.csv", {"match_id", "player", "team", "score"}, optional=True)
        seen = set()
        participants_by_match = {}
        self.rosters = {t: set() for t in self.teams}
        for row in self.players:
            match = self._match(row)
            if row["team"] not in (match["team"], match["opponent"]):
                raise ValueError("Player team must be a participant in its match")
            identity = (row["match_id"], row["player"])
            if identity in seen:
                raise ValueError(f"Duplicate player/match: {identity}")
            seen.add(identity)
            row["score"] = number(row["score"], "player score")
            row["date"] = match["date"]
            row["opponent"] = match["opponent"] if row["team"] == match["team"] else match["team"]
            self.rosters[row["team"]].add(row["player"])
            participants_by_match.setdefault(row["match_id"], {})[row["player"]] = row["team"]
        self.interactions = read_csv(folder / "interactions.csv", {"match_id", "player", "opponent_player", "opportunities", "successes", "score"}, optional=True)
        for row in self.interactions:
            match = self._match(row)
            participants = participants_by_match.get(row["match_id"], {})
            if row["player"] not in participants or row["opponent_player"] not in participants:
                raise ValueError("Interaction players must appear in players.csv for that match")
            if participants[row["player"]] == participants[row["opponent_player"]]:
                raise ValueError("Interactions must involve opposing players")
            for key in ("opportunities", "successes", "score"):
                row[key] = number(row[key], key)
            if row["opportunities"] <= 0 or row["successes"] > row["opportunities"]:
                raise ValueError("Interaction opportunities must be positive and successes cannot exceed opportunities")
            row["date"] = match["date"]
        self.players.sort(key=lambda r: (r["date"], r["match_id"]))
        self.interactions.sort(key=lambda r: (r["date"], r["match_id"]))

    def _match(self, row):
        if row["match_id"] not in self.by_id:
            raise ValueError(f"Unknown match_id: {row['match_id']}")
        return self.by_id[row["match_id"]]

    def history(self, team, cutoff, opponent=None):
        rows = []
        for m in self.matches:
            if m["date"] >= cutoff or team not in (m["team"], m["opponent"]):
                continue
            home = m["team"] == team
            other = m["opponent"] if home else m["team"]
            if opponent and other != opponent:
                continue
            result = "D" if m["outcome"] == "draw" else "W" if m["outcome"] == ("team" if home else "opponent") else "L"
            rows.append({"match_id": m["match_id"], "date": m["date"], "opponent": other,
                         "score": m["team_score"] if home else m["opponent_score"],
                         "conceded": m["opponent_score"] if home else m["team_score"], "result": result})
        return rows
