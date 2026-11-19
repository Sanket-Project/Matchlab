"""Turn a cricket fixture plus the latest match intel into the match-page forecast.

Everything on the page (scores, wickets, player picks, win chance, reasons) is read
from the same simulated matches. Reasons are built from the model's own inputs; no
text is invented. Pure local computation.
"""
import json
import re
import zlib
from datetime import date, datetime

import numpy as np

from . import cricket_ratings, cricket_sim as sim
from .live import name_key

SIMS = 3000
BAT_MARK, WICKET_MARK = (20, 30, 50), (2, 2, 3)   # "big innings" / "wicket haul" thresholds by format
UNSUPPORTED = "The simulator covers T10, T20 and one-day cricket. Tests and first-class matches are not modelled yet."


def classify(fixture, intel):
    """-> (format code or None, female)."""
    text = name_key(" ".join(str(x or "") for x in (fixture.get("detail"), fixture.get("espn_class"),
                                                     (intel or {}).get("class"), fixture.get("tournament"))))
    female = bool(re.search(r"\bwomen(?:s| s)?\b", name_key(" ".join(str(fixture.get(k) or "") for k in ("tournament", "team", "opponent", "detail", "espn_class")))))
    short = name_key(" ".join(str(x or "") for x in (fixture.get("detail"), fixture.get("espn_class"), (intel or {}).get("class"))))
    if re.search(r"\btest\b|first class|\bfc\b|multi day", short):
        return None, female
    if re.search(r"\bt10\b", text):
        return 0, female
    if re.search(r"t20|twenty20|\bit20\b", text):
        return 1, female
    if re.search(r"\bodi\b|list a|one day|\bodm\b", text):
        return 2, female
    return None, female


def _balls(overs):
    whole = int(float(overs or 0))
    return whole * 6 + min(6, int(round((float(overs or 0) - whole) * 10)))


def _overs(balls):
    return f"{balls // 6}.{balls % 6}"


def _estimate(innings):
    low, high = np.quantile(innings["runs"], (0.1, 0.9))
    return {"mean": round(float(innings["runs"].mean())), "low": round(float(low)), "high": round(float(high)),
            "wickets": round(float(innings["wickets"].mean()), 1)}


def _percent(ratio):
    return round((ratio - 1) * 100)


def _phrase(value, up, down):
    return f"{abs(value)}% {up if value > 0 else down}" if value else f"neither {up} nor {down}"


def _own(name):
    return f"{name}'" if name.endswith("s") else f"{name}'s"


class Builder:
    def __init__(self, root, fixture, intel):
        self.root, self.fixture, self.intel = root, fixture, intel or {}
        self.names = [fixture["team"], fixture["opponent"]]
        self.fmt, self.female = classify(fixture, intel)
        self.today = sim.today_ordinal()
        try:
            self.today = min(self.today, date.fromisoformat(str(fixture.get("start"))[:10]).toordinal())
        except ValueError:
            pass

    def scoreboard(self):
        state = self.intel.get("state") or self.fixture.get("state")
        status = self.intel.get("status_text") or self.fixture.get("status")
        timestamp = self.intel.get("fetched_at") or self.fixture.get("score_checked_at")
        scores = []
        for index, field in enumerate(("team_score", "opponent_score")):
            side = self.intel_team(index)
            score = side.get("score") if side is not None else self.fixture.get(field)
            if not score and side:
                score = " & ".join(f"{row['runs']}/{row['wickets']}" for row in side.get("innings", []) if row.get("runs") is not None)
            scores.append({"name": self.names[index], "score": score, "winner": bool(state == "post" and side and side.get("winner"))})
        if self.intel.get("ok") and state == "in" and any(team["score"] for team in scores):
            for team in scores:
                if not team["score"]:
                    team["score"] = "Yet to bat"
        return {"teams": scores, "state": state, "status": status, "source": "ESPN" if self.intel.get("ok") else "Fixture scoreboard",
                "checked_at": timestamp, "stale": bool(self.intel.get("stale"))}

    def intel_team(self, index):
        teams = self.intel.get("teams") or []
        keys = [sim.team_key(t["name"]) for t in teams]
        mine, other = sim.team_key(self.names[index]), sim.team_key(self.names[1 - index])
        if mine in keys:
            return teams[keys.index(mine)]
        if len(teams) == 2 and other in keys:
            return teams[1 - keys.index(other)]
        return teams[index] if len(teams) == 2 else None

    def lineups(self, data):
        lineups, labels, sources, confirmed = [], [], [], []
        for index, name in enumerate(self.names):
            team = self.intel_team(index)
            xi = (team or {}).get("xi") or []
            last, last_date = data.last_xi(name, self.fmt, self.female, self.today)
            if len(xi) == 11:
                pool = data.recent_players(name, self.female, self.today)
                lineups.append([data.resolve(p["id"], p["name"], pool) for p in xi])
                labels.append([p["name"] for p in xi])
                sources.append("Confirmed playing XI")
                confirmed.append(True)
            elif last:
                lineups.append(last)
                labels.append([data.names[p] for p in last])
                sources.append(f"Provisional: last recorded XI ({last_date}). Updates when the XI is announced.")
                confirmed.append(False)
            else:
                lineups.append([-1] * 11)
                labels.append([f"Player {i + 1}" for i in range(11)])
                sources.append("No recorded XI for this team: format-average players assumed.")
                confirmed.append(False)
        return lineups, labels, sources, confirmed

    def toss(self):
        toss = self.intel.get("toss")
        if not toss:
            return None
        key = sim.team_key(toss["winner"])
        winner = next((i for i, n in enumerate(self.names) if sim.team_key(n) == key), None)
        if winner is None:
            return None
        first = winner if toss["decision"] == "bat" else 1 - winner
        return {"winner": self.names[winner], "decision": toss["decision"], "bats_first": first, "text": toss["text"]}

    def live_state(self):
        """Current position from ESPN innings lines, or the CricketData list as a fallback."""
        lines = []
        for index in (0, 1):
            team = self.intel_team(index)
            for line in (team or {}).get("innings") or []:
                if all(line.get(k) is not None for k in ("runs", "wickets", "overs")):
                    lines.append({"team": index, "runs": int(line["runs"]), "wickets": int(line.get("wickets") or 0),
                                  "balls": _balls(line.get("overs")), "target": int(line.get("target") or 0), "period": line.get("period") or 0})
        lines.sort(key=lambda row: row["period"])
        if not lines:
            for line in self.fixture.get("innings") or []:
                key = sim.team_key(line.get("team"))
                index = next((i for i, n in enumerate(self.names) if sim.team_key(n) == key), None)
                if index is not None and all(line.get(k) is not None for k in ("runs", "wickets", "overs")):
                    lines.append({"team": index, "runs": int(line["runs"]), "wickets": int(line.get("wickets") or 0),
                                  "balls": _balls(line.get("overs")), "target": 0, "period": None})
        if not lines or len(lines) > 2:
            return None
        limit = int(sim.OVERS[self.fmt]) * 6
        first = lines[0]
        if self.intel.get("reduced_overs") or any(line["balls"] > limit for line in lines):
            return None
        if len(lines) == 1:
            if first["balls"] >= limit or first["wickets"] >= 10:    # innings break
                return {"innings": 2, "order": first["team"], "runs": 0, "wickets": 0, "balls": 0,
                        "target": first["runs"] + 1, "first_runs": first["runs"], "first_wickets": first["wickets"],
                        "first_period": first["period"]}
            return self.crease({"innings": 1, "order": first["team"], "runs": first["runs"], "wickets": first["wickets"],
                                "balls": first["balls"]}, first["team"], first["period"])
        chase = lines[1]
        if chase["team"] == first["team"]:
            return None
        return self.crease({"innings": 2, "order": first["team"], "runs": chase["runs"], "wickets": chase["wickets"],
                            "balls": chase["balls"], "target": chase["target"] or first["runs"] + 1,
                            "first_runs": first["runs"], "first_wickets": first["wickets"], "first_period": first["period"]},
                           chase["team"], chase["period"])

    def crease(self, state, batting, period):
        """Add who has batted, who is in, and overs each bowler has used, from the live scorecard.
        Only when both XIs are confirmed and the scorecard agrees with the score."""
        teams = [self.intel_team(batting), self.intel_team(1 - batting)]
        if period is None or any(len((t or {}).get("xi") or []) != 11 for t in teams):
            return state
        rows = [p.get("stats", {}).get(str(period), {}) for p in teams[0]["xi"]]
        batted = sorted((i for i, s in enumerate(rows) if s.get("batted")), key=lambda i: rows[i].get("battingPosition") or 99)
        out, at = [i for i in batted if rows[i].get("outs")], [i for i in batted if not rows[i].get("outs")]
        figures = [p.get("stats", {}).get(str(period), {}) for p in teams[1]["xi"]]
        state["figures"] = {
            "batting": [{"name": teams[0]["xi"][i]["name"], "runs": int(rows[i].get("runs") or 0), "balls": int(rows[i].get("ballsFaced") or 0)} for i in at],
            "bowling": [{"name": p["name"], "overs": s.get("overs"), "wickets": int(s.get("wickets") or 0), "runs": int(s.get("conceded") or 0)}
                        for p, s in zip(teams[1]["xi"], figures) if s.get("bowled")]}
        bowled = [_balls(s.get("overs")) for s in figures]
        partial = [i for i, balls in enumerate(bowled) if balls % 6]
        if (len(out) == state["wickets"] and len(at) <= 2 and (at or state["balls"] == 0 or state["wickets"] == 10)
                and sum(bowled) == state["balls"] and len(partial) <= 1 and sum(int(s.get("runs") or 0) for s in rows) <= state["runs"]):
            state["lead"] = out + at
            state["overs_bowled"] = [balls // 6 for balls in bowled]
            state["partial_bowler"] = partial[0] if partial else None
            state["player_figures_ready"] = True
        return state

    # ---- reasons ------------------------------------------------------------------------
    def bat_rates(self, mdl, effect):
        q = mdl.mix * effect
        q = q / q.sum()
        base = mdl.mix
        return ((q * mdl.bat_value).sum() / (base * mdl.bat_value).sum(), (q[6] + q[7]) / (base[6] + base[7]))

    def bowl_rates(self, mdl, effect):
        q = mdl.mix * effect
        q = q / q.sum()
        return ((q * mdl.team_value).sum() / (mdl.mix * mdl.team_value).sum(), q[6] / mdl.mix[6])

    def record(self, mdl, table, player, keys):
        at = np.flatnonzero(table["player"] == player) if player >= 0 else np.array([], dtype=int)
        days = mdl.data.day[table["match"][at]]
        recent = at[days >= self.today - 3 * 365]
        return {key: float(table[key][recent].sum()) for key in keys} | {"n": int(len(recent)), "last": [int(v) for v in table[keys[0]][at[-5:]]]}

    def batter(self, mdl, side, slot, name, values):
        player = side["players"][slot]
        rec = self.record(mdl, mdl.bat_inn, player, ("runs", "balls", "outs"))
        speed, out = self.bat_rates(mdl, side["bat"][slot])
        reasons = [f"Bats around No. {slot + 1}."]
        if rec["n"]:
            average = rec["runs"] / max(rec["outs"], 1)
            reasons.append(f"Last three years in this format: {rec['n']} innings, {int(rec['runs'])} runs, average {average:.0f}, strike rate {100 * rec['runs'] / max(rec['balls'], 1):.0f}.")
            reasons.append("Most recent scores: " + ", ".join(str(v) for v in rec["last"]) + ".")
        if player < 0 or rec["balls"] < 60:
            reasons.append(f"Very little ball-by-ball history, so this leans on a typical No. {slot + 1} batter.")
        else:
            reasons.append(f"After adjusting for the bowlers and grounds faced: scores {_phrase(_percent(speed), 'faster', 'slower')} than the average batter and is dismissed {_phrase(_percent(out), 'more', 'less')} often.")
        return {"name": name, "slot": slot + 1, "reasons": reasons, "history_balls": int(rec["balls"]), **values}

    def bowler(self, mdl, side, slot, name, values):
        player = side["players"][slot]
        rec = self.record(mdl, mdl.bowl_inn, player, ("wickets", "balls", "runs"))
        cost, strike = self.bowl_rates(mdl, side["bowl"][slot])
        reasons = [f"Expected to bowl about {values['overs']:.1f} overs."]
        if rec["n"]:
            reasons.append(f"Last three years in this format: {rec['n']} matches bowled, {int(rec['wickets'])} wickets, economy {6 * rec['runs'] / max(rec['balls'], 1):.1f}.")
            reasons.append("Wickets in the most recent matches: " + ", ".join(str(v) for v in rec["last"]) + ".")
        if player < 0 or rec["balls"] < 60:
            reasons.append("Very little bowling history, so this assumes an average bowler.")
        else:
            reasons.append(f"After adjusting for the batters and grounds faced: takes wickets {_phrase(_percent(strike), 'more', 'less')} often than average and concedes {_phrase(_percent(cost), 'more', 'fewer')} runs.")
        return {"name": name, "reasons": reasons, "history_balls": int(rec["balls"]), **values}

    def venue(self, mdl, data, key):
        fmt = self.fmt
        everywhere = [t for (f, _), rows in mdl.first_totals.items() if f == fmt for t in rows]
        norm = float(np.mean([t[0] for t in everywhere])) if everywhere else None
        name = (self.intel.get("venue") or {}).get("name") or self.fixture.get("venue") or ""
        block = {"name": name or "Venue not announced", "matched": key is not None, "format_average": round(norm) if norm else None, "notes": [],
                 "source": "Derived from past matches at this ground. It is not today's pitch report: no free feed publishes the curator's report."}
        if key is None:
            block["notes"].append("No ball-by-ball history at this ground, so neutral conditions are assumed.")
            return block
        rows = mdl.first_totals.get((fmt, data.venue_index[key]), [])
        effect = mdl.ven_r[data.venue_index[key]]
        runs, wickets = self.bowl_rates(mdl, effect)
        q = mdl.mix * effect
        boundary = (q[4] + q[5]) / q.sum() / (mdl.mix[4] + mdl.mix[5])
        block.update(name=data.venue_names[key], matches=len(rows), scoring=_percent(runs), wickets=_percent(wickets), boundaries=_percent(boundary))
        if rows:
            average, won = float(np.mean([t[0] for t in rows])), float(np.mean([t[1] for t in rows]))
            block.update(average_first_innings=round(average), bat_first_win_pct=round(100 * won), last=str(date.fromordinal(max(t[3] for t in rows))))
            block["notes"].append(f"{len(rows)} {sim.FORMAT_NAMES[fmt]} matches on record here: average first-innings score {average:.0f} (format norm {norm:.0f}); the side batting first won {100 * won:.0f}%.")
        if len(rows) < 5:
            block["notes"].append("Fewer than five matches on record, so the ground's effect is mostly shrunk toward neutral.")
        pace = "a high-scoring surface" if runs > 1.04 else "a low-scoring surface" if runs < 0.96 else "a surface close to the format norm"
        block["notes"].append(f"Behaves like {pace}: run scoring {_phrase(_percent(runs), 'above', 'below')} normal, boundaries {_phrase(_percent(boundary), 'more', 'less')} frequent, wickets {_phrase(_percent(wickets), 'more', 'less')} frequent (after adjusting for who played here).")
        return block

    # ---- assembly -----------------------------------------------------------------------
    def build(self):
        board = self.scoreboard()
        if self.fmt is None:
            return {"supported": False, "reason": UNSUPPORTED, "scoreboard": board}
        data = sim.load(self.root)
        mdl = sim.model(self.root, self.today, sim.family_of(self.fmt), self.female)
        lineups, labels, sources, confirmed = self.lineups(data)
        venue_info = self.intel.get("venue") or {}
        key = data.find_venue(venue_info.get("name") or self.fixture.get("venue"), venue_info.get("city") or "")
        toss = self.toss()
        seed = zlib.crc32(str(self.fixture.get("id")).encode())
        sides, results = mdl.run(self.fmt, lineups, key, sims=SIMS, seed=seed)
        weights = {toss["bats_first"]: 1.0} if toss else {0: 0.5, 1: 0.5}
        fmt, teams = self.fmt, []
        simulated0 = float(sum(w * (results[k]["first_wins"].mean() if k == 0 else 1 - results[k]["first_wins"].mean()) for k, w in weights.items()))
        family = sim.family_of(fmt)
        table, played = cricket_ratings.table(self.root, family, self.female, self.today)
        keys = [sim.team_key(name) for name in self.names]
        rating = [table.get(k, cricket_ratings.START) for k in keys]
        counted = [played.get(k, 0) for k in keys]
        self.edge, self.blend_weights = cricket_ratings.log_odds(*rating), cricket_ratings.blend_weights(self.root, family)
        rated0 = 1 / (1 + np.exp(-self.edge))
        win0 = cricket_ratings.blend(simulated0, self.edge, self.blend_weights)
        for t in (0, 1):
            side, other = sides[t], sides[1 - t]
            names = [labels[t][i] for i in side["index"]]
            first = _estimate(results[t]["first"])
            chase = _estimate(results[1 - t]["second"])
            exp_runs, p_top, p_big = np.zeros(11), np.zeros(11), np.zeros(11)
            exp_wk, wk_top, wk_haul, overs = np.zeros(11), np.zeros(11), np.zeros(11), np.zeros(11)
            taken = 0.0
            for k, w in weights.items():
                batting = results[k]["first"] if k == t else results[k]["second"]
                bowling = results[k]["second"] if k == t else results[k]["first"]
                exp_runs += w * batting["bat_runs"].mean(0)
                p_top += w * np.bincount(batting["bat_runs"].argmax(1), minlength=11) / SIMS
                p_big += w * (batting["bat_runs"] >= BAT_MARK[fmt]).mean(0)
                exp_wk += w * bowling["bowl_wk"].mean(0)
                jitter = bowling["bowl_wk"] + np.random.default_rng(seed).random(bowling["bowl_wk"].shape) * 0.01
                wk_top += w * np.bincount(jitter.argmax(1), minlength=11) / SIMS
                wk_haul += w * (bowling["bowl_wk"] >= WICKET_MARK[fmt]).mean(0)
                overs += w * bowling["bowl_balls"].mean(0) / 6
                taken += w * bowling["wickets"].mean()
            batters = [self.batter(mdl, side, j, names[j], {"runs": round(float(exp_runs[j]), 1), "top": round(float(p_top[j]), 3), "big": round(float(p_big[j]), 3)}) for j in range(11)]
            bowlers = [self.bowler(mdl, side, j, names[j], {"wickets": round(float(exp_wk[j]), 2), "top": round(float(wk_top[j]), 3), "haul": round(float(wk_haul[j]), 3), "overs": round(float(overs[j]), 1)})
                       for j in range(11)]
            speed = float(np.mean([self.bat_rates(mdl, side["bat"][j])[0] for j in range(7)]))
            share = other["use"].sum(1) / max(other["use"].sum(), 1e-9)
            attack = [self.bowl_rates(mdl, other["bowl"][j]) for j in range(11)]
            cost, strike = (float(sum(share[j] * attack[j][i] for j in range(11))) for i in (0, 1))
            reasons = [f"{_own(self.names[t])} top seven score {_phrase(_percent(speed), 'faster', 'slower')} than the format average.",
                       f"{_own(self.names[1 - t])} attack concedes {_phrase(_percent(cost), 'more', 'fewer')} runs than average and takes wickets {_phrase(_percent(strike), 'more', 'less')} often."]
            if counted[t]:
                gap = round(rating[t] - rating[1 - t])
                reasons.append(f"Team rating from {counted[t]} past results: {rating[t]:.0f} ({'level with' if not gap else f'{abs(gap)} points ' + ('above' if gap > 0 else 'below')} {self.names[1 - t]}). "
                               f"On results alone that is a {100 * (rated0 if t == 0 else 1 - rated0):.0f}% win chance; the player-by-player simulation says {100 * (simulated0 if t == 0 else 1 - simulated0):.0f}%.")
            else:
                reasons.append("No past results on record for this side, so its team rating starts at the average.")
            if key is not None:
                reasons.append(f"The ground moves scoring {_phrase(_percent(self.bowl_rates(mdl, mdl.ven_r[data.venue_index[key]])[0]), 'up', 'down')}.")
            if not confirmed[t]:
                reasons.append("The XI is provisional, so player numbers can change once the team is announced.")
            unknown = sum(p < 0 for p in side["players"])
            if unknown:
                reasons.append(f"{unknown} player(s) could not be matched to the archive and are treated as average for their position.")
            teams.append({
                "name": self.names[t], "lineup_source": sources[t], "lineup_confirmed": confirmed[t],
                "win": round(float(win0 if t == 0 else 1 - win0), 3),
                "win_parts": {"simulation": round(simulated0 if t == 0 else 1 - simulated0, 3), "rating": round(float(rated0 if t == 0 else 1 - rated0), 3),
                              "team_rating": round(rating[t]), "results_counted": counted[t]},
                "first_innings": {"mean": first["mean"], "low": first["low"], "high": first["high"], "wickets_lost": first["wickets"]},
                "chase": chase,
                "wickets_taken": round(float(taken), 1), "reasons": reasons,
                "batters": sorted(batters, key=lambda row: -row["runs"]), "bowlers": sorted(bowlers, key=lambda row: -row["wickets"]),
            })
        latest = max((int(data.day[i]) for i in mdl.match_ids), default=None)
        payload = {
            "supported": True, "format": sim.FORMAT_NAMES[fmt], "category": "Women" if self.female else "Men",
            "stage": "post_toss" if toss else "pre_toss", "toss": toss, "teams": teams, "venue": self.venue(mdl, data, key),
            "weather": self.intel.get("weather"), "marks": {"bat": BAT_MARK[fmt], "wickets": WICKET_MARK[fmt]},
            "scoreboard": board,
            "intel": {"available": bool(self.intel.get("ok")), "fetched_at": self.intel.get("fetched_at"),
                      "state": self.intel.get("state") or self.fixture.get("state"), "status": self.intel.get("status_text") or self.fixture.get("status")},
            "analysis": {
                "data": f"{mdl.n_matches:,} matches and {mdl.n_balls:,} deliveries of {'women' if self.female else 'men'}'s {'T10/T20' if fmt < 2 else 'one-day'} cricket"
                        + (f", through {date.fromordinal(latest)}." if latest else "."),
                "machine_learning": {"used": True, "name": "Ball-by-ball outcome model + match simulation + team ratings",
                                     "detail": f"Batter, bowler and ground effects are learned from the deliveries above, then the match is played {SIMS:,} times. "
                                               "The win chance also uses a team rating built from past results, because that picked winners better than the simulation alone in testing."},
                "deep_learning": {"used": False, "detail": "Not used for this page. No deep model has beaten the simulator in a held-out test here, so none is shown."},
                "backtest": backtest(self.root, fmt),
            },
        }
        state = self.live_state() if (self.intel.get("state") or self.fixture.get("state")) == "in" else None
        if state:
            payload["live"] = self.live(mdl, lineups, labels, key, state, seed)
        elif payload["intel"]["state"] == "in" and self.intel.get("reduced_overs"):
            payload["live_unavailable"] = "This match has reduced overs. Live projections require the standard innings length."
        return payload

    def live(self, mdl, lineups, labels, key, state, seed):
        order = state["order"]
        chasing = state["innings"] == 2
        batting = 1 - order if chasing else order
        limit = int(sim.OVERS[self.fmt]) * 6
        balls_left = limit - state["balls"]
        need = max(0, state["target"] - state["runs"]) if chasing else None
        innings_open = balls_left > 0 and state["wickets"] < 10 and (not chasing or need > 0)
        # One set of simulations drives both the live forecast and its conditional scenarios.
        if innings_open:
            state["checkpoint_balls"] = min(limit, state["balls"] + (12 if self.fmt < 2 else 24))
        sides, results = mdl.run(self.fmt, lineups, key, sims=SIMS, seed=seed, orders=(order,), state=state)
        result = results[order]
        inn = result["second"] if chasing else result["first"]
        share = (balls_left if chasing else limit + balls_left) / (2 * limit)
        edge = self.edge if order == 0 else -self.edge

        def chances(outcomes):
            raw = float(outcomes.mean())
            first_win = raw if not innings_open else cricket_ratings.blend(raw, edge, self.blend_weights, share=share)
            return [round(first_win if t == order else 1 - first_win, 3) for t in (0, 1)]

        live = {"innings": state["innings"], "batting": self.names[batting], "batting_index": batting, "figures": state.get("figures"),
                "uses_scorecard": bool(state.get("player_figures_ready")),
                "runs": state["runs"], "wickets": state["wickets"], "balls": state["balls"],
                "score": f"{state['runs']}/{state['wickets']} after {_overs(state['balls'])} overs", "target": state.get("target"),
                "win": chances(result["first_wins"]), "projected": _estimate(inn), "scenarios": [], "players": []}
        if chasing:
            live["first_innings"] = {"mean": state["first_runs"], "wickets": state["first_wickets"]}
            reached = float((inn["runs"] >= state["target"]).mean())
            changes = [f"{self.names[batting]} need {need} runs from {balls_left} balls with {10 - state['wickets']} wickets in hand. "
                       f"They reach the target in {reached:.0%} of simulations."]
            if balls_left and need:
                changes.append(f"Required rate is {6 * need / balls_left:.2f} per over" +
                               (f", compared with {6 * state['runs'] / state['balls']:.2f} per over so far." if state["balls"] else "."))
        else:
            live["chase"] = _estimate(result["second"])
            changes = [f"{self.names[batting]} have {balls_left} balls and {10 - state['wickets']} wickets in hand. "
                       f"The current position gives an average finish of {live['projected']['mean']} runs.",
                       f"Given those totals and the two lineups, {self.names[order]} defend their score in "
                       f"{float((result['second']['runs'] < inn['runs']).mean()):.0%} of simulations."]
        if innings_open and abs(self.edge) >= 0.15:
            stronger = self.names[0 if self.edge > 0 else 1]
            changes.append(f"Past results give {stronger} the stronger team rating. Its influence falls as the match progresses.")
        at = (state.get("figures") or {}).get("batting") or []
        if state.get("player_figures_ready") and at:
            changes.append("At the crease: " + " and ".join(f"{b['name']} ({b['runs']} off {b['balls']})" for b in at)
                           + ". The projection uses these batters and the overs each bowler has left.")
        live["changes"] = changes
        if innings_open:
            threshold = int(np.median(inn["checkpoint_runs"]))
            next_wicket = inn["checkpoint_wickets"] > state["wickets"]
            live["scenario_over"] = _overs(state["checkpoint_balls"])
            for label, mask, otherwise in ((f"{threshold} runs or more", inn["checkpoint_runs"] >= threshold, f"Fewer than {threshold} runs"),
                                            ("Lose at least one more wicket", next_wicket, "Keep all remaining wickets")):
                if min(mask.sum(), (~mask).sum()) >= SIMS // 20:
                    live["scenarios"].extend([{"label": label, "win": chances(result["first_wins"][mask])},
                                              {"label": otherwise, "win": chances(result["first_wins"][~mask])}])
        if state.get("player_figures_ready") or (not any(state[k] for k in ("balls", "runs", "wickets"))):
            live["players"] = self.live_players(sides, labels, result, order, state.get("first_period"))
        return live

    def live_players(self, sides, labels, result, order, first_period):
        players = []
        for team in (0, 1):
            xi = (self.intel_team(team) or {}).get("xi") or []
            batting_line = result["first"] if team == order else result["second"]
            bowling_line = result["second"] if team == order else result["first"]
            first_card_ready = first_period is not None and any(
                p.get("stats", {}).get(str(first_period), {}).get("batted" if team == order else "bowled") for p in xi)
            for slot, index in enumerate(sides[team]["index"]):
                stats = xi[index].get("stats", {}) if len(xi) == 11 else {}
                runs = sum(s.get("runs", 0) for s in stats.values() if s.get("batted")) if batting_line is not None or first_card_ready else None
                wickets = sum(s.get("wickets", 0) for s in stats.values() if s.get("bowled")) if bowling_line is not None or first_card_ready else None
                players.append({"team": self.names[team], "name": labels[team][index], "runs": runs, "wickets": wickets,
                                "final_runs": round(runs + float(batting_line["bat_runs"][:, slot].mean()), 1) if batting_line is not None else None,
                                "final_wickets": round(wickets + float(bowling_line["bowl_wk"][:, slot].mean()), 2) if bowling_line is not None else None})
        return players


def backtest(root, fmt):
    name = "oneday" if fmt == 2 else "t20"
    try:
        report = json.loads((root / f"artifacts/cricket-sim-backtest-{name}.json").read_text(encoding="utf-8"))["report"]
    except (OSError, ValueError, KeyError):
        return None
    return report


def build(root, fixture, intel):
    return Builder(root, fixture, intel).build()
