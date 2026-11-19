"""Causal, task-specific labeled examples for frozen in-context models.

Both orientations of a match enter together. No team/player name is encoded as
a number. Each historical feature is queried strictly before that match's
pre_match_date; dates of result availability can be later (tennis tournaments).
"""
from bisect import bisect_left
from collections import defaultdict
from statistics import mean

SIDE_FEATURES = ["team_recent_avg", "team_recent_conceded", "team_recent_win_rate", "team_recent_draw_rate", "team_matches",
                 "opponent_recent_avg", "opponent_recent_conceded", "opponent_recent_win_rate", "opponent_recent_draw_rate", "opponent_matches",
                 "h2h_avg", "h2h_win_rate", "h2h_matches", "is_home", "is_neutral", "team_rest_days", "opponent_rest_days"]
PLAYER_FEATURES = SIDE_FEATURES + ["player_recent_avg", "player_recent_std", "player_opponent_avg", "player_appearances"]
THREAT_FEATURES = PLAYER_FEATURES + ["opponent_player_recent_avg", "interaction_rate", "interaction_opportunities", "interaction_meetings",
                                      "player_action_rate", "player_action_opportunities", "opponent_action_conceded_rate"]
FEATURE_DESCRIPTIONS = {
    "team_rest_days": "Calendar days since focal side's most recent available result (capped at 60)",
    "opponent_rest_days": "Calendar days since opponent's most recent available result (capped at 60)",
    "player_recent_std": "Population standard deviation of previous player scores",
    "interaction_meetings": "Previous distinct meetings of selected player pair",
    "player_action_rate": "Selected player's previous successes / opportunities against all opponents",
    "player_action_opportunities": "Selected player's previous action opportunities against all opponents",
    "opponent_action_conceded_rate": "Previous successes conceded to other players / opportunities by opposing player",
}


class HistoryIndex:
    def __init__(self, ds):
        self.ds = ds
        self.sides, self.pairs, self.players, self.actions, self.defending, self.interactions = (defaultdict(list) for _ in range(6))
        for m in ds.matches:
            for focal in (m["team"], m["opponent"]):
                first = focal == m["team"]
                other = m["opponent"] if first else m["team"]
                row = dict(date=m["date"], match_id=m["match_id"], score=m["team_score"] if first else m["opponent_score"],
                           conceded=m["opponent_score"] if first else m["team_score"],
                           win=int(m["outcome"] == ("team" if first else "opponent")), draw=int(m["outcome"] == "draw"))
                self.sides[focal].append(row)
                self.pairs[(focal, other)].append(row)
        for p in ds.players:
            self.players[(p["player"], p["team"])].append(p)
        # Aggregate events to one pair-match label; never weight a match several
        # times because the source happens to use multiple event rows.
        grouped = {}
        participants = {(p["match_id"], p["player"]): p["team"] for p in ds.players}
        for p in ds.interactions:
            key = (p["match_id"], p["player"], p["opponent_player"])
            q = grouped.setdefault(key, {**p, "opportunities": 0, "successes": 0, "score": 0,
                                         "team": participants[(p["match_id"], p["player"])],
                                         "opponent_team": participants[(p["match_id"], p["opponent_player"])]})
            for k in ("opportunities", "successes", "score"):
                q[k] += p[k]
        self.grouped_interactions = sorted(grouped.values(), key=lambda r: (r["date"], r["match_id"]))
        for p in self.grouped_interactions:
            self.actions[p["player"]].append(p)
            self.defending[p["opponent_player"]].append(p)
            self.interactions[(p["player"], p["opponent_player"])].append(p)
        self.dates = {}
        for mapping in (self.sides, self.pairs, self.players, self.actions, self.defending, self.interactions):
            for records in mapping.values():
                records.sort(key=lambda r: (r["date"], r["match_id"]))
                self.dates[id(records)] = [r["date"] for r in records]

    def before(self, mapping, key, cutoff, window):
        records = mapping.get(key, [])
        end = bisect_left(self.dates.get(id(records), []), cutoff)
        return records[max(0, end - window):end]

    def features(self, team, opponent, cutoff, window, venue="neutral", player=None, other=None):
        from datetime import date
        f = {}
        for side, prefix in ((team, "team"), (opponent, "opponent")):
            h = self.before(self.sides, side, cutoff, window)
            f.update({f"{prefix}_recent_avg": mean(r["score"] for r in h) if h else None,
                      f"{prefix}_recent_conceded": mean(r["conceded"] for r in h) if h else None,
                      f"{prefix}_recent_win_rate": mean(r["win"] for r in h) if h else None,
                      f"{prefix}_recent_draw_rate": mean(r["draw"] for r in h) if h else None,
                      f"{prefix}_matches": len(h),
                      f"{prefix}_rest_days": min(60, (date.fromisoformat(cutoff) - date.fromisoformat(h[-1]["date"])).days) if h else None})
        h = self.before(self.pairs, (team, opponent), cutoff, window)
        f.update(h2h_avg=mean(r["score"] for r in h) if h else None,
                 h2h_win_rate=mean(r["win"] for r in h) if h else None, h2h_matches=len(h),
                 is_home=int(venue == "home"), is_neutral=int(venue == "neutral"))
        h = self.before(self.players, (player, team), cutoff, window)
        versus = [r for r in self.before(self.players, (player, team), cutoff, 250000) if r["opponent"] == opponent][-window:]
        avg = mean(r["score"] for r in h) if h else None
        f.update(player_recent_avg=avg, player_recent_std=(mean((r["score"] - avg)**2 for r in h)**.5) if h else None,
                 player_opponent_avg=mean(r["score"] for r in versus) if versus else None, player_appearances=len(h))
        h = self.before(self.players, (other, opponent), cutoff, window)
        f["opponent_player_recent_avg"] = mean(r["score"] for r in h) if h else None
        for mapping, key, name in ((self.interactions, (player, other), "pair"), (self.actions, player, "player"), (self.defending, other, "opponent")):
            # Window is distinct matches, not arbitrary event count.
            eligible = self.before(mapping, key, cutoff, 250000)
            mids = set(list(dict.fromkeys(r["match_id"] for r in eligible))[-window:])
            h = [r for r in eligible if r["match_id"] in mids]
            opps = sum(r["opportunities"] for r in h)
            rate = sum(r["successes"] for r in h) / opps if opps else None
            if name == "pair":
                f.update(interaction_rate=rate, interaction_opportunities=opps, interaction_meetings=len(mids))
            elif name == "player":
                f.update(player_action_rate=rate, player_action_opportunities=opps)
            else:
                f["opponent_action_conceded_rate"] = rate
        return f

    def examples(self, task, cutoff, window, max_rows=192, min_history=2):
        """Return only completed pre-cutoff labels and their pre-match features."""
        ds = self.ds
        examples = []
        if task in ("winner", "team_score"):
            # Bound work as well as transformer memory. Both orientations stay
            # together; use most recent complete matches, never random splits.
            candidates = [m for m in ds.matches if m["date"] < cutoff][-2048:]
            for m in reversed(candidates):
                when = m.get("pre_match_date") or m["date"]
                pair = []
                for reverse in (False, True):
                    a, b = (m["team"], m["opponent"]) if not reverse else (m["opponent"], m["team"])
                    venue = m.get("venue") or "neutral"
                    if reverse and venue != "neutral":
                        venue = "away" if venue == "home" else "home"
                    f = self.features(a, b, when, window, venue)
                    if min(f["team_matches"], f["opponent_matches"]) < min_history:
                        continue
                    label = m["outcome"]
                    if reverse and label != "draw":
                        label = "opponent" if label == "team" else "team"
                    if task == "team_score":
                        label = m["opponent_score"] if reverse else m["team_score"]
                    pair.append(dict(features=f, target=label, date=m["date"], feature_cutoff=when, match_id=m["match_id"]))
                if len(pair) == 2:
                    examples.extend(pair)
                if len(examples) >= max_rows:
                    break
        else:
            candidates = ds.players if task == "player_score" else self.grouped_interactions
            for p in reversed(candidates):
                if p["date"] >= cutoff:
                    continue
                m = ds.by_id[p["match_id"]]
                when = m.get("pre_match_date") or m["date"]
                team = p["team"]
                opponent = m["opponent"] if team == m["team"] else m["team"]
                venue = m.get("venue") or "neutral"
                if team != m["team"] and venue != "neutral":
                    venue = "away" if venue == "home" else "home"
                f = self.features(team, opponent, when, window, venue, p["player"], p.get("opponent_player"))
                if min(f["team_matches"], f["opponent_matches"], f["player_appearances"]) < min_history:
                    continue
                if task == "player_threat" and (f["player_action_rate"] is None or f["opponent_action_conceded_rate"] is None):
                    continue
                target = p["score"] if task == "player_score" else p["successes"] / p["opportunities"]
                examples.append(dict(features=f, target=target, date=p["date"], feature_cutoff=when, match_id=p["match_id"]))
                if len(examples) >= max_rows:
                    break
        return sorted(examples, key=lambda r: (r["date"], r["match_id"]))
