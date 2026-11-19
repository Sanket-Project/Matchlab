"""Ball-by-ball cricket match simulator.

A multiplicative outcome model is fitted to Cricsheet deliveries available before a
cutoff date: a base distribution by format, innings, over and wickets down, adjusted
by chase pressure and by shrunken batter, bowler and venue effects (each estimated
against the others, so weak-opposition runs count for less). Matches are then played
out thousands of times. Team totals, wickets, player runs and wickets all come from
the same simulated matches. Pure local computation; no network access.
"""
import csv
import json
import pickle
import re
from datetime import date
from functools import lru_cache

import numpy as np

from .live import name_key

O = 11                      # outcome classes: 0,1,2,3,4,6, bowler wicket, other wicket, wide, no-ball, bye
OVERS = np.array([10, 20, 50])
QUOTA = (2, 4, 10)
FORMAT_NAMES = ("T10", "T20", "One-day")
FAMILIES = {"short": (0, 1), "long": (2,)}
HALF_LIFE = 2.5 * 365       # days for a delivery's weight to halve
import os
K_BASE, K_PRESSURE, K_VENUE = 300.0, 200.0, 150.0
K_BAT, K_BOWL = float(os.environ.get("MATCHLAB_K_BAT", 12)), float(os.environ.get("MATCHLAB_K_BOWL", 15))
SIGMA, RHO = 0.13, 0.5      # match-day conditions spread (log scale) and share common to both innings
DAY_VECTOR = np.array([-0.5, 0.2, 0.3, 0.3, 1.0, 1.0, -1.0, 0, 0, 0, 0])
GROUP_EDGES = [3.5, 5.5, 7.5, 9.5]


def venue_key(name):
    return name_key(str(name or "").split(",")[0])


def team_key(name):
    key = name_key(re.sub(r"\s+\([^)]*\)\s*$", "", str(name or "")))      # "Kathmandu Gorkhas (NPL)"
    for suffix in (" women", " w"):
        if key.endswith(suffix):
            key = key[: -len(suffix)]
    return {"royal challengers bangalore": "royal challengers bengaluru", "delhi daredevils": "delhi capitals",
            "kings xi punjab": "punjab kings", "usa": "united states of america", "uae": "united arab emirates",
            "u a e": "united arab emirates", "png": "papua new guinea"}.get(key, key)


class Data:
    def __init__(self, root):
        path = root / "data/real/cricket_sim"
        meta = json.loads((path / "matches.json").read_text(encoding="utf-8"))
        self.matches, self.pids, self.names = meta["matches"], meta["players"], meta["player_names"]
        self.pid_index = {pid: i for i, pid in enumerate(self.pids)}
        with np.load(path / "balls.npz") as stored:
            self.b = {name: stored[name] for name in stored.files}
        rows = self.matches
        self.day = np.array([m["day"] for m in rows])
        self.fmt = np.array([m["fmt"] for m in rows])
        self.female = np.array([m["gender"] == "female" for m in rows])
        self.adjusted = np.array([m["adjusted"] for m in rows])
        self.xi = np.array([m["xi"][0][:11] + m["xi"][1][:11] for m in rows])
        self.venue_index, self.venue_names = {}, {}
        self.venue = np.array([self.venue_index.setdefault(venue_key(m["venue"]), len(self.venue_index)) for m in rows])
        for m in rows:
            self.venue_names[venue_key(m["venue"])] = ", ".join(x for x in (m["venue"].split(",")[0], m["city"]) if x)
        self.team_keys = [[team_key(t) for t in m["teams"]] for m in rows]
        self.cricinfo = {}
        register = root / "data/raw/cricket/register/people.csv"
        if register.exists():
            with register.open(encoding="utf-8", newline="") as file:
                for row in csv.DictReader(file):
                    for column in ("key_cricinfo", "key_cricinfo_2", "key_cricinfo_3"):
                        if row.get(column) and row["identifier"] in self.pid_index:
                            self.cricinfo[row[column]] = self.pid_index[row["identifier"]]

    def find_venue(self, name, city=""):
        key = venue_key(name)
        if key in self.venue_index:
            return key
        tokens = set(key.split()) - {"stadium", "cricket", "ground", "international", "oval", "park"}
        best, score = None, 0
        for other in self.venue_index:
            shared = len(tokens & set(other.split()))
            if shared > score and (shared >= 2 or (shared and name_key(city) and name_key(city) in name_key(self.venue_names[other]))):
                best, score = other, shared
        return best

    def last_xi(self, team, fmt, female, before_day):
        """Most recent recorded XI for a team: same format family first, then any white-ball match."""
        key, family = team_key(team), next(f for f in FAMILIES.values() if fmt in f)
        fallback = None
        for index in range(len(self.matches) - 1, -1, -1):
            if self.day[index] >= before_day or self.female[index] != female or key not in self.team_keys[index]:
                continue
            side = self.team_keys[index].index(key)
            found = (list(self.matches[index]["xi"][side][:11]), self.matches[index]["date"])
            if self.fmt[index] in family:
                return found
            fallback = fallback or found
        return fallback or (None, None)

    def recent_players(self, team, female, before_day, matches=12):
        key, found, seen = team_key(team), set(), 0
        for index in range(len(self.matches) - 1, -1, -1):
            if seen >= matches:
                break
            if self.day[index] < before_day and self.female[index] == female and key in self.team_keys[index]:
                found.update(self.matches[index]["xi"][self.team_keys[index].index(key)])
                seen += 1
        return found

    def resolve(self, athlete_id, name, candidates=()):
        """ESPN athlete -> archive player index. Exact register id first, then initial + surname."""
        if str(athlete_id or "") in self.cricinfo:
            return self.cricinfo[str(athlete_id)]
        tokens = name_key(name).split()
        if not tokens:
            return -1
        hits = []
        for index in candidates:
            other = name_key(self.names[index]).split()
            if other and other[-1] == tokens[-1] and (other[0] == tokens[0] or other[0][0] == tokens[0][0]):
                hits.append(index)
        return hits[0] if len(hits) == 1 else -1


@lru_cache(maxsize=1)
def load(root):
    return Data(root)


class Model:
    def __init__(self, data, cutoff_day, family, female):
        self.data, self.cutoff, self.family, self.female = data, cutoff_day, family, female
        keep = ((data.day < cutoff_day) & (data.day >= cutoff_day - 9 * 365) & (data.female == female)
                & np.isin(data.fmt, FAMILIES[family]))
        self.match_ids = np.flatnonzero(keep)
        b = data.b
        sel = keep[b["match"]] & ~data.adjusted[b["match"]]
        mt = b["match"][sel]
        fmt, inn, over, wk, out = data.fmt[mt], b["inn"][sel] - 1, b["over"][sel].astype(np.int64), b["wk"][sel].astype(np.int64), b["out"][sel].astype(np.int64)
        bat, bowl, ven = b["bat"][sel], b["bowl"][sel], data.venue[mt]
        w = (0.5 ** ((cutoff_day - data.day[mt]) / HALF_LIFE)).astype(np.float32)
        self.n_balls, self.n_matches = int(sel.sum()), int(keep.sum())
        P, V = len(data.pids), len(data.venue_index)
        if not self.n_balls:
            raise ValueError("No ball-by-ball history before this date for this format.")

        # Base distribution, smoothed toward a coarser phase / wickets-in-hand table.
        flat = ((fmt * 2 + inn) * 50 + over) * 10 + wk
        counts = np.bincount(flat * O + out, weights=w, minlength=3000 * O).reshape(3, 2, 50, 10, O)
        phase5 = np.minimum(4, 5 * over // OVERS[fmt])
        coarse = np.bincount((((fmt * 2 + inn) * 5 + phase5) * 5 + wk // 2) * O + out, weights=w, minlength=150 * O).reshape(3, 2, 5, 5, O)
        coarse = (coarse + 1e-9) / (coarse + 1e-9).sum(-1, keepdims=True)
        phases = np.array([[min(4, 5 * o // n) for o in range(50)] for n in OVERS])
        back = coarse[np.arange(3)[:, None, None, None], np.arange(2)[None, :, None, None],
                      phases[:, None, :, None], (np.arange(10) // 2)[None, None, None, :]]
        self.base = (counts + K_BASE * back) / (counts.sum(-1, keepdims=True) + K_BASE)
        bp = self.base.reshape(-1, O)[flat].astype(np.float32)

        def tally(index, size):
            return np.bincount(index * O + out, weights=w, minlength=size * O).reshape(size, O)

        def expected(index, size, *factors):
            result = np.empty((size, O))
            for o in range(O):
                value = w * bp[:, o]
                for table, at in factors:
                    value = value * table[at, o]
                result[:, o] = np.bincount(index, weights=value, minlength=size)
            return result

        # Chase pressure: second-innings outcomes by required run rate.
        second = inn == 1
        left = (OVERS[fmt] - over) * 6 - 3
        rrr = np.clip((b["target"][sel].astype(np.float64) - b["runs_before"][sel]) * 6 / left, 0, 36)
        self.edges = np.zeros((3, 5))
        bins = np.zeros(len(out), dtype=np.int64)
        for code in FAMILIES[family]:
            mask = second & (fmt == code)
            if mask.sum() > 500:
                self.edges[code] = np.quantile(rrr[mask], [1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6])
                bins[mask] = np.searchsorted(self.edges[code], rrr[mask])
        slot = np.where(second, fmt * 6 + bins, 18)
        self.pressure = ((tally(slot, 19) + K_PRESSURE) / (expected(slot, 19) + K_PRESSURE))[:18].reshape(3, 6, O)
        bp[second] *= self.pressure[fmt[second], bins[second]].astype(np.float32)

        # Player and venue effects, each estimated against the others.
        group = np.digitize(b["pos"][sel], GROUP_EDGES)
        innings_key = mt.astype(np.int64) * P + bat
        _, first, inverse = np.unique(innings_key, return_index=True, return_inverse=True)
        weight_sum = np.bincount(bat[first], weights=w[first], minlength=P)
        self.pos_mean = np.bincount(bat[first], weights=w[first] * b["pos"][sel][first], minlength=P) / np.maximum(weight_sum, 1e-9)
        self.pos_mean[weight_sum == 0] = np.nan
        player_group = np.digitize(np.nan_to_num(self.pos_mean, nan=6.5), GROUP_EDGES)
        a_bat, a_bowl, a_ven, a_group = tally(bat, P), tally(bowl, P), tally(ven, V), tally(group, 5)
        bat_r, bowl_r, ven_r = np.ones((P, O)), np.ones((P, O)), np.ones((V, O))
        for _ in range(2):
            self.group_r = (a_group + 1) / (expected(group, 5, (bowl_r, bowl), (ven_r, ven)) + 1)
            e_bat = expected(bat, P, (bowl_r, bowl), (ven_r, ven))
            bat_r = (a_bat + K_BAT * self.group_r[player_group]) / (e_bat + K_BAT)
            e_bowl = expected(bowl, P, (bat_r, bat), (ven_r, ven))
            bowl_r = (a_bowl + K_BOWL) / (e_bowl + K_BOWL)
            ven_r = (a_ven + K_VENUE) / (expected(ven, V, (bat_r, bat), (bowl_r, bowl)) + K_VENUE)
        self.a_bat, self.e_bat, self.bowl_r, self.ven_r = a_bat, e_bat, bowl_r, ven_r
        self.bowl_events = e_bowl[:, 6]

        # Run values, bowling usage, and per-innings records for form and reasons.
        total, bat_runs = b["total"][sel].astype(np.float64), b["bat_runs"][sel].astype(np.float64)
        seen = np.maximum(np.bincount(out, weights=w, minlength=O), 1e-9)
        self.team_value = np.bincount(out, weights=w * total, minlength=O) / seen
        self.bat_value = np.bincount(out, weights=w * bat_runs, minlength=O) / seen
        self.mix = np.bincount(out, weights=w, minlength=O) / w.sum()
        legal = ~np.isin(out, (8, 9))
        phase4 = np.minimum(3, 4 * over // OVERS[fmt])
        match_w = 0.5 ** ((cutoff_day - data.day[self.match_ids]) / HALF_LIFE)
        appearances = np.zeros(P)
        np.add.at(appearances, data.xi[self.match_ids].ravel(), np.repeat(match_w, 22))
        self.appearances = appearances
        self.use = np.bincount(bowl * 4 + phase4, weights=w * legal, minlength=P * 4).reshape(P, 4) / 6 / np.maximum(appearances, 0.5)[:, None]
        faced = out != 8
        self.bat_inn = {"player": bat[first], "match": mt[first],
                        "runs": np.bincount(inverse, weights=bat_runs), "balls": np.bincount(inverse, weights=faced),
                        "outs": np.bincount(inverse, weights=np.isin(out, (6, 7)))}
        _, first_b, inverse_b = np.unique(mt.astype(np.int64) * P + bowl, return_index=True, return_inverse=True)
        self.bowl_inn = {"player": bowl[first_b], "match": mt[first_b],
                         "wickets": np.bincount(inverse_b, weights=out == 6), "balls": np.bincount(inverse_b, weights=legal),
                         "runs": np.bincount(inverse_b, weights=total * (out != 10))}
        # Venue first-innings record.
        self.first_totals = {}
        for index in self.match_ids:
            m = data.matches[index]
            if not m["adjusted"] and len(m["innings"]) == 2 and m["winner"]:
                self.first_totals.setdefault((int(data.fmt[index]), int(data.venue[index])), []).append(
                    (m["innings"][0]["runs"], m["winner"] == m["innings"][0]["team"], m["innings"][0]["wickets"], int(data.day[index])))

    def __getstate__(self):
        return {k: v for k, v in self.__dict__.items() if k != "data"}

    # ---- simulation -------------------------------------------------------------------
    def side(self, lineup, lead=()):
        """Order an XI by usual batting position and collect its effects.
        lead: lineup positions that have already batted today, in order (live matches)."""
        known = [p for p in lineup if p >= 0]
        order = sorted(range(len(lineup)), key=lambda i: (np.nan_to_num(self.pos_mean[lineup[i]], nan=7.5) if lineup[i] >= 0 else 7.5, i))
        order = list(lead) + [i for i in order if i not in lead]
        players = [lineup[i] for i in order][:11]
        players += [-1] * (11 - len(players))
        bat = np.ones((12, O))
        bowl = np.ones((11, O))
        use = np.zeros((11, 4))
        for slot, p in enumerate(players):
            prior = self.group_r[int(np.digitize(slot + 1, GROUP_EDGES))]
            if p >= 0:
                bat[slot] = (self.a_bat[p] + K_BAT * prior) / (self.e_bat[p] + K_BAT)
                bowl[slot], use[slot] = self.bowl_r[p], self.use[p]
            else:
                bat[slot] = prior
        if (use.sum(1) > 0.5).sum() < 5:      # too few known bowlers: give everyone a small share
            use = use + 0.15
        return {"players": players, "index": order[:11], "bat": bat, "bowl": bowl, "use": use, "known": len(known)}

    def _innings(self, fmt, inn, batting, bowling, ven, g, rng, target=None, start=None):
        S, n_overs, quota = len(g), int(OVERS[fmt]), QUOTA[fmt]
        base, idx = self.base[fmt, inn], np.arange(S)
        day = np.exp(g[:, None] * DAY_VECTOR[None, :])
        runs, wk = np.zeros(S), np.zeros(S, dtype=np.int64)
        legal_total = np.zeros(S, dtype=np.int64)
        start_over = start_ball = 0
        if start:
            runs += start["runs"]
            wk += start["wickets"]
            start_over, start_ball = divmod(start["balls"], 6)
            legal_total += start["balls"]
        striker, non, nxt = wk.copy(), wk + 1, wk + 2
        done = wk >= 10
        if target is not None:
            done |= runs >= target
        bat_runs, bowl_wk, bowl_balls = np.zeros((S, 12)), np.zeros((S, 11)), np.zeros((S, 11))
        overs_bowled, prev = np.zeros((S, 11), dtype=np.int64), np.full(S, -1)
        if start and start.get("overs_bowled"):      # overs already used today, by lineup position
            overs_bowled += np.array([start["overs_bowled"][i] for i in bowling["index"]], dtype=np.int64)
        partial = start.get("partial_bowler") if start else None
        partial_slot = bowling["index"].index(partial) if partial is not None else None
        checkpoint = start.get("checkpoint_balls") if start else None
        at_checkpoint = legal_total.copy() >= checkpoint if checkpoint is not None else None
        checkpoint_runs, checkpoint_wickets = runs.copy(), wk.copy()
        team_floor, team_frac = np.floor(self.team_value), self.team_value - np.floor(self.team_value)
        bat_floor, bat_frac = np.floor(self.bat_value), self.bat_value - np.floor(self.bat_value)
        for over in range(start_over, n_overs):
            weights = np.tile(bowling["use"][:, min(3, 4 * over // n_overs)] + 1e-4, (S, 1)) * (overs_bowled < quota)
            has_prev = prev >= 0
            weights[idx[has_prev], prev[has_prev]] = 0
            stuck = weights.sum(1) <= 0
            if stuck.any():
                weights[stuck] = 1.0
                weights[idx[stuck & has_prev], prev[stuck & has_prev]] = 0
            bowler = (weights.cumsum(1) > (rng.random(S) * weights.sum(1))[:, None]).argmax(1)
            if over == start_over and start_ball and partial_slot is not None:
                bowler.fill(partial_slot)
            overs_bowled[idx, bowler] += 1
            prev = bowler
            legal = np.full(S, start_ball if over == start_over else 0)
            for _ in range(12):
                act = ~done & (legal < 6)
                if not act.any():
                    break
                p = base[over, np.minimum(wk, 9)] * batting["bat"][np.minimum(striker, 11)] * bowling["bowl"][bowler] * ven * day
                if target is not None:
                    rrr = np.clip((target - runs) * 6 / ((n_overs - over) * 6 - 3), 0, 36)
                    p = p * self.pressure[fmt, np.searchsorted(self.edges[fmt], rrr)]
                cumulative = p.cumsum(1)
                o = (cumulative > (rng.random(S) * cumulative[:, -1])[:, None]).argmax(1)
                gain = (team_floor[o] + (rng.random(S) < team_frac[o])) * act
                runs += gain
                bat_runs[idx, np.minimum(striker, 11)] += (bat_floor[o] + (rng.random(S) < bat_frac[o])) * act
                is_legal = act & (o != 8) & (o != 9)
                legal += is_legal
                legal_total += is_legal
                bowl_balls[idx, bowler] += is_legal
                wicket = act & ((o == 6) | (o == 7))
                bowl_wk[idx, bowler] += act & (o == 6)
                wk += wicket
                striker = np.where(wicket, nxt, striker)
                nxt = nxt + wicket
                swap = act & ~wicket & ((o == 1) | (o == 3) | (o == 10))
                striker, non = np.where(swap, non, striker), np.where(swap, striker, non)
                done |= wk >= 10
                if target is not None:
                    done |= runs >= target
                if checkpoint is not None:
                    reached = ~at_checkpoint & ((legal_total >= checkpoint) | done)
                    checkpoint_runs[reached], checkpoint_wickets[reached] = runs[reached], wk[reached]
                    at_checkpoint |= reached
            striker, non = np.where(done, striker, non), np.where(done, non, striker)
        result = {"runs": runs, "wickets": wk, "bat_runs": bat_runs[:, :11], "bowl_wk": bowl_wk, "bowl_balls": bowl_balls, "balls": legal_total}
        if checkpoint is not None:
            result["checkpoint_runs"] = np.where(at_checkpoint, checkpoint_runs, runs)
            result["checkpoint_wickets"] = np.where(at_checkpoint, checkpoint_wickets, wk)
        return result

    def run(self, fmt, lineups, venue=None, sims=3000, seed=0, orders=(0, 1), state=None, sigma=SIGMA):
        """Simulate. orders: which team bats first (0, 1 or both). state: live position."""
        rng = np.random.default_rng(seed)
        sides = [self.side(lineup) for lineup in lineups]
        if state and state.get("lead"):
            at_bat = orders[0] if state["innings"] == 1 else 1 - orders[0]
            sides[at_bat] = self.side(lineups[at_bat], state["lead"])
        ven = self.ven_r[self.data.venue_index[venue]] if venue in self.data.venue_index else np.ones(O)
        results = {}
        for order in orders:
            first, second = sides[order], sides[1 - order]
            common = rng.normal(0, sigma, sims) * np.sqrt(RHO)
            g1, g2 = (common + rng.normal(0, sigma, sims) * np.sqrt(1 - RHO) for _ in range(2))
            if state and state["innings"] == 2:
                one = None
                target = np.full(sims, float(state["target"]))
                two = self._innings(fmt, 1, second, first, ven, g2, rng, target, state)
                first_runs = target - 1
            else:
                one = self._innings(fmt, 0, first, second, ven, g1, rng, None, state)
                two = self._innings(fmt, 1, second, first, ven, g2, rng, one["runs"] + 1)
                first_runs = one["runs"]
            results[order] = {"first": one, "second": two,
                              "first_wins": (two["runs"] < first_runs) + 0.5 * (two["runs"] == first_runs)}
        return sides, results


_MODELS = {}


def model(root, cutoff_day, family, female):
    """Fitted model for today. Fitting takes a while, so it is kept in memory and on disk
    until the archive changes or the fit is a week old."""
    stamp = (root / "data/real/cricket_sim/matches.json").stat().st_mtime_ns
    key = (str(root), family, female)
    held = _MODELS.get(key)
    if held and held[0] == stamp and 0 <= cutoff_day - held[1].cutoff <= 7:
        return held[1]
    path = root / "data/local/cache" / f"cricket_model_{family}_{'women' if female else 'men'}.pkl"
    fitted = None
    try:
        with path.open("rb") as file:
            saved_stamp, fitted = pickle.load(file)
        if saved_stamp != stamp or not 0 <= cutoff_day - fitted.cutoff <= 7:
            fitted = None
        else:
            fitted.data = load(root)
    except (OSError, ValueError, EOFError, pickle.PickleError, AttributeError):
        fitted = None
    if fitted is None:
        fitted = Model(load(root), cutoff_day, family, female)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as file:
            pickle.dump((stamp, fitted), file, protocol=pickle.HIGHEST_PROTOCOL)
    _MODELS[key] = (stamp, fitted)
    return fitted


def family_of(fmt):
    return next(name for name, codes in FAMILIES.items() if fmt in codes)


def today_ordinal():
    return date.today().toordinal()
