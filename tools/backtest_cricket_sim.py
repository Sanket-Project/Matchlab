"""Held-out backtest of the cricket simulator against simple baselines.

python tools/backtest_cricket_sim.py --family short --matches 400
Every model is fitted only on matches before the block being predicted. Inputs per
match are what is public after the toss: both XIs, the venue and who bats first.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from matchlab import cricket_ratings  # noqa: E402
from matchlab.cricket_sim import FAMILIES, Model, load, team_key  # noqa: E402


def _fit(X, y, l2=1.0):
    w = np.zeros(X.shape[1])
    for _ in range(100):
        p = 1 / (1 + np.exp(-X @ w))
        w -= np.linalg.solve((X * (p * (1 - p))[:, None]).T @ X + l2 * np.eye(len(w)), X.T @ (p - y) + l2 * w)
    return w


def blend_report(rows, data, family, female):
    """Add the team-rating edge to every row and fit the simulator + rating blend.
    Ratings before each match use only earlier results. Scores are 5-fold cross-validated."""
    edges = {m["id"]: cricket_ratings.log_odds(ra, rb) * (1 if team_key(m["innings"][0]["team"]) == team_key(m["teams"][0]) else -1)
             for m, ra, rb, _ in cricket_ratings.walk(data.matches, family, female) if m["innings"]}
    for row in rows:
        row["rating_edge"] = edges[row["id"]]
    y = np.array([r["first_won"] for r in rows], dtype=float)
    p = np.array([r["p_first_wins"] for r in rows])
    X = np.column_stack([np.log(p / (1 - p)), [r["rating_edge"] for r in rows]])
    held = np.zeros(len(y))
    for fold in range(5):
        test = np.arange(len(y)) % 5 == fold
        held[test] = 1 / (1 + np.exp(-X[test] @ _fit(X[~test], y[~test])))
    rating = 1 / (1 + np.exp(-X[:, 1]))

    def score(q):
        q = np.clip(q, 0.01, 0.99)
        return {"accuracy": float(((q > 0.5) == y).mean()), "log_loss": float(-(y * np.log(q) + (1 - y) * np.log(1 - q)).mean())}
    weights = _fit(X, y)
    for row, q in zip(rows, held):
        row["p_blend"] = float(q)
    return {"weights": {"simulator": float(weights[0]), "rating": float(weights[1])},
            "simulator_only": score(p), "rating_only": score(rating), "blend": score(held)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", default="short", choices=list(FAMILIES))
    parser.add_argument("--female", type=int, default=0)
    parser.add_argument("--matches", type=int, default=400)
    parser.add_argument("--sims", type=int, default=400)
    parser.add_argument("--sigma", type=float, default=None)
    parser.add_argument("--days", type=int, default=365, help="length of the held-out window")
    parser.add_argument("--offset", type=int, default=0, help="shift the window back (validation)")
    parser.add_argument("--intl", action="store_true", help="international matches only")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--rescore", type=Path, help="refit the win-chance blend on a saved backtest, without re-simulating")
    args = parser.parse_args()
    data = load(ROOT)
    if args.rescore:
        saved = json.loads(args.rescore.read_text(encoding="utf-8"))
        report = saved["report"]
        report["blend"] = blend_report(saved["rows"], data, report["family"], report["female"])
        print(json.dumps(report["blend"], indent=2))
        args.rescore.write_text(json.dumps(saved, indent=1), encoding="utf-8")
        return
    end = int(data.day.max()) + 1 - args.offset
    eligible = [i for i, m in enumerate(data.matches)
                if end - args.days <= m["day"] < end and m["fmt"] in FAMILIES[args.family]
                and (m["gender"] == "female") == bool(args.female) and not m["adjusted"] and m["winner"]
                and len(m["innings"]) == 2 and (m["intl"] or not args.intl)]
    picks = [eligible[i] for i in np.unique(np.linspace(0, len(eligible) - 1, min(args.matches, len(eligible))).astype(int))]
    match_col = data.b["match"]
    rows, current, block = [], None, None
    for index in picks:
        m = data.matches[index]
        this_block = (m["day"] - (end - args.days)) // 60
        if this_block != block:
            block = this_block
            current = Model(data, end - args.days + block * 60, args.family, bool(args.female))
            firsts = [t[0] for (f, _), v in current.first_totals.items() for t in v if f == m["fmt"]]
            wickets_mean = np.mean([t[2] for (f, _), v in current.first_totals.items() for t in v if f == m["fmt"]])
            print(f"fitted block {block}: {current.n_matches} matches, {current.n_balls} deliveries", flush=True)
        fmt = m["fmt"]
        order = [team_key(t) for t in m["teams"]].index(team_key(m["innings"][0]["team"]))
        kwargs = {"sigma": args.sigma} if args.sigma is not None else {}
        sides, result = current.run(fmt, [side[:11] for side in m["xi"]], next(k for k, v in data.venue_index.items() if v == data.venue[index]),
                                    sims=args.sims, seed=index, orders=(order,), **kwargs)
        sim = result[order]
        lo, hi = np.searchsorted(match_col, [index, index + 1])
        b = {k: v[lo:hi] for k, v in data.b.items()}
        row = {"id": m["id"], "date": m["date"], "fmt": fmt,
               "actual_first": m["innings"][0]["runs"], "pred_first": float(sim["first"]["runs"].mean()),
               "p10": float(np.quantile(sim["first"]["runs"], 0.1)), "p90": float(np.quantile(sim["first"]["runs"], 0.9)),
               "base_first": float(np.mean(firsts)),
               "actual_wk": m["innings"][0]["wickets"], "pred_wk": float(sim["first"]["wickets"].mean()), "base_wk": float(wickets_mean),
               "p_first_wins": float(np.clip(sim["first_wins"].mean(), 0.01, 0.99)),
               "first_won": m["winner"] == m["innings"][0]["team"]}
        venue_rows = current.first_totals.get((fmt, int(data.venue[index])), [])
        row["venue_first"] = float(np.mean([t[0] for t in venue_rows])) if len(venue_rows) >= 5 else row["base_first"]
        for number, (bat_side, bowl_side, inn) in enumerate(((sides[order], sides[1 - order], sim["first"]),
                                                             (sides[1 - order], sides[order], sim["second"])), 1):
            mask = b["inn"] == number
            actual_runs = {p: b["bat_runs"][mask & (b["bat"] == p)].sum() for p in bat_side["players"]}
            actual_wk = {p: ((b["out"] == 6) & mask & (b["bowl"] == p)).sum() for p in bowl_side["players"]}
            if not mask.any():
                continue
            top_runs, top_wk = max(actual_runs.values()), max(actual_wk.values())
            ranked = np.argsort(-inn["bat_runs"].mean(0))
            top_counts = np.bincount(inn["bat_runs"].argmax(1), minlength=11)
            pick = bat_side["players"][int(top_counts.argmax())]

            def average(p, table, key):
                at = table["player"] == p
                return table[key][at].sum() / max(at.sum(), 1) if at.sum() >= 5 else -1
            base_pick = max(bat_side["players"], key=lambda p: average(p, current.bat_inn, "runs"))
            wk_pick = bowl_side["players"][int(inn["bowl_wk"].mean(0).argmax())]
            base_wk_pick = max(bowl_side["players"], key=lambda p: average(p, current.bowl_inn, "wickets"))
            row[f"bat{number}"] = {"hit": bool(actual_runs[pick] == top_runs), "base": bool(actual_runs[base_pick] == top_runs),
                                   "top3": bool(any(actual_runs[bat_side["players"][int(j)]] == top_runs for j in ranked[:3])),
                                   "p_pick": float(top_counts.max() / args.sims)}
            if top_wk > 0:
                row[f"bowl{number}"] = {"hit": bool(actual_wk[wk_pick] == top_wk), "base": bool(actual_wk[base_wk_pick] == top_wk)}
        rows.append(row)

    def col(name):
        return np.array([r[name] for r in rows], dtype=float)
    p, won = col("p_first_wins"), col("first_won")
    bats = [r[k] for r in rows for k in ("bat1", "bat2") if k in r]
    bowls = [r[k] for r in rows for k in ("bowl1", "bowl2") if k in r]
    report = {
        "family": args.family, "female": bool(args.female), "international_only": args.intl, "matches": len(rows),
        "window": [rows[0]["date"], rows[-1]["date"]], "sims": args.sims, "sigma": args.sigma,
        "first_innings_mae": {"simulator": float(np.abs(col("pred_first") - col("actual_first")).mean()),
                              "format_average": float(np.abs(col("base_first") - col("actual_first")).mean()),
                              "venue_average": float(np.abs(col("venue_first") - col("actual_first")).mean())},
        "first_innings_bias": float((col("pred_first") - col("actual_first")).mean()),
        "interval_80_coverage": float(((col("actual_first") >= col("p10")) & (col("actual_first") <= col("p90"))).mean()),
        "wickets_mae": {"simulator": float(np.abs(col("pred_wk") - col("actual_wk")).mean()),
                        "format_average": float(np.abs(col("base_wk") - col("actual_wk")).mean())},
        "winner": {"accuracy": float(((p > 0.5) == won).mean()),
                   "log_loss": float(-(won * np.log(p) + (1 - won) * np.log(1 - p)).mean()), "coin_flip_log_loss": 0.6931},
        "top_scorer": {"innings": len(bats), "simulator_pick": float(np.mean([x["hit"] for x in bats])),
                       "career_average_pick": float(np.mean([x["base"] for x in bats])),
                       "in_simulator_top3": float(np.mean([x["top3"] for x in bats])),
                       "stated_probability_of_pick": float(np.mean([x["p_pick"] for x in bats]))},
        "top_wicket_taker": {"innings": len(bowls), "simulator_pick": float(np.mean([x["hit"] for x in bowls])),
                             "career_average_pick": float(np.mean([x["base"] for x in bowls]))},
    }
    report["blend"] = blend_report(rows, data, args.family, bool(args.female))
    print(json.dumps(report, indent=2))
    if args.out:
        args.out.write_text(json.dumps({"report": report, "rows": rows}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
