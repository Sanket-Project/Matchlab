# Match dashboard (cricket, tennis, Formula 1) — design

Date: 11 November 2026. Status: direction approved in conversation; step 1 and 2 built, steps 3 and 4 open.

## Goal

Open the dashboard about 30 minutes before a match, see what is live and coming up, click a match and get a full forecast with reasons. Three sports only: cricket, tennis, Formula 1. Build order: (1) cricket pre-match page, (2) cricket live re-forecast, (3) tennis page, (4) F1 page.

## Decisions

- **Fixture-first page** at `/` (`web/dash.*`). The older analysis view stays at `/lab`.
- **One simulator produces every cricket number** (`matchlab/cricket_sim.py`). A ball-outcome model (base rates by format, innings, over, wickets; chase pressure; shrunken batter, bowler and ground effects, each estimated against the others) is fitted to Cricsheet deliveries before the cutoff date, then the match is played 3,000 times. Scores, wickets, top batters and bowlers and win chance all come from the same simulated matches, so they agree. A live score restarts the simulation from the real position.
- **No deep learning unless it wins a held-out test.** The page states which model produced the numbers and its measured record.
- **Reasons come from model inputs** (`matchlab/cricket_forecast.py`): player record, opposition-adjusted effects, ground effect, lineup status. An LLM may only reword them.
- **Pitch** is ground history, labelled as such. No free feed has the curator's report.
- **Request budgets** (`matchlab/budget.py`): CricketData.org 100/day and OpenRouter 50/day by default, counted per UTC day in `data/local/api_budget.json`, with a reserve held back. CricketData is used only for the fixture list (cached 15–60 minutes depending on what is left). Toss, playing XIs, live scores and final scorecards come from ESPN's free match summary (`tools/fetch_match_intel.py`). OpenRouter is used only on request, once per match and stage.
- **Track record** (`matchlab/tracker.py`): forecasts opened before the start are saved and graded from the final scorecard. Forecasts first opened after the start are listed but not counted.
- Network calls stay in short-lived worker processes; the server process remains offline-guarded.

## Evaluation (held out, last 12 months, fitted only on earlier matches)

`tools/backtest_cricket_sim.py`; results in `artifacts/cricket-sim-backtest-*.json`.

| Set | Matches | Winner accuracy | Winner log loss (coin flip 0.693) | First-innings MAE (venue average) | 80% range coverage | Top-scorer pick (career-average pick) | Top wicket-taker pick (career-average pick) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Men's T10/T20, all levels | 500 | 60.0% | 0.648 | 33.2 (36.0) | 77% | 21.3% (24.1%) | 28.5% (29.5%) |
| Men's T20 internationals | 300 | 65.3% | 0.622 | 37.2 (40.2) | 69% | 22.0% (23.2%) | 29.8% (26.8%) |
| Men's one-day | 273 | 53.5% | 0.683 | 55.4 (58.5) | 82% | 20.9% (20.3%) | 29.6% (25.4%) |

The conditions spread (`SIGMA`) and player shrinkage were chosen on the year before the held-out window.

## Known gaps

- Top-scorer picks do not beat a career-average pick; T20I ranges are too narrow; one-day winner forecasts are barely better than a coin flip.
- Tests and first-class matches are not modelled. Bowling style (pace or spin) is not in the data.
- Live mode re-forecasts team totals, wickets and win chance; player lines stay at their pre-match values.
- Fixtures without an ESPN match feed have no automatic toss or XI.
- Tennis and F1 fixtures are listed, but their forecast pages are not built yet.
