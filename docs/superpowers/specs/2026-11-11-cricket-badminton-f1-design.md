# Cricket and badminton accuracy, and Formula 1 — design

Date: 11 November 2026. Status: approved in conversation; awaiting spec review.

## Goal and success criteria

- **Cricket:** beat the no-skill baseline on held-out IPL matches. Success means the 95% paired-bootstrap interval of the log-loss gap to the baseline lies entirely below zero, for at least one of the two stages below. If neither stage achieves this, the dashboard keeps saying cricket is close to a coin flip; no unsupported figure is shown.
- **Badminton:** have enough held-out matches (several hundred, up from 6) for a meaningful evaluation, and run the existing Elo and trained-logistic models.
- **Formula 1:** add F1 as a new sport. Show a full race forecast per Grand Prix: each driver's chance to win, reach the podium and score points, and expected finishing position. Evaluate it against simple baselines with the same rigour as the other sports.

Build order: cricket, then badminton, then F1. Each step ends with its evaluation numbers before the next begins.

## Shared principles (unchanged from the existing project)

- Every input is causal: only results available strictly before the prediction cutoff.
- Held-out evaluation: the date at 80% of each sport's matches (or races) is the boundary; nothing is tuned on held-out results. Any constant that is chosen from data is chosen by time-series cross-validation inside the training period only.
- Probabilities are judged by log loss; "beats baseline" uses the 95% paired bootstrap already in `tools/evaluate_models.py`.
- Sources, licenses and limitations are recorded in `DATA_SOURCES.md` and shown in the dashboard.

## 1. Cricket (IPL, existing Cricsheet data)

Two forecast stages, evaluated separately.

**Stage 1 — pre-match (available days ahead).**
- *Season-aware Elo:* at the first match of each IPL season, each team's rating moves a fraction of the way back toward 1500 (squads are rebuilt in the auction). The fraction and K are chosen by time-series cross-validation inside the training period.
- *Derived home ground:* every match is currently `neutral`. A team's home ground is the ground it played at most in earlier seasons, derived from past data only. The match `venue` becomes home, away or neutral accordingly.
- *Ground character:* from earlier matches at the ground: mean first-innings score and the batting-first win rate (with a minimum-matches threshold; otherwise missing).
- *Squad strength:* batting form of the team's most recent XI, from `players.csv` runs, plus batting and bowling boundary rates from `interactions.csv`.

**Stage 2 — post-toss (about 30 minutes before the start).**
- Adds: toss winner (focal side or not), toss decision (bat/field), toss decision × ground batting-first win rate.
- Squad strength is recomputed from the announced XIs instead of the last XI.
- Dashboard: a "toss and XIs" section in the cricket panel, with XIs pre-filled from each team's last match and editable. The forecast is labelled pre-toss until it is filled in.

**Fix:** cricket outcome classes come from the data (no draws in this IPL data) rather than the `draw: True` flag.

**Evaluation:** both stages are added to `tools/evaluate_models.py` with the existing protocol and baselines. Stage 2 uses toss and XI data only for the match being predicted; stage 1 never sees them.

## 2. Badminton

**Data.**
- The user downloads Kaggle `sanderp/badminton-bwf-world-tour` (CC BY-SA 4.0, BWF World Tour April 2018–2021) into `data/raw/badminton_bwf/`. Kaggle needs a signed-in account; Claude does not download it.
- `tools/import_public_data.py` gains a step that reads the men's singles file. It converts names to ShuttleSet's "SURNAME Given" form, removes fixtures present in both sources (same date and player pair), and orders each pair alphabetically so the winner is never an input. ShuttleSet stays as an extra source.
- If the file has per-game scores, games won are derived and the score model is available. If not, only win/loss is modelled and the badminton score model is reported as unavailable rather than estimated.
- The CC BY-SA attribution is added to `DATA_SOURCES.md`, provenance and the dashboard.

**Models.** No new model type. Add tournament tier and round as inputs only if the file has them.

**Evaluation and limits.** Same 80/20 protocol. The combined data ends in 2022, so the dashboard shows a staleness note beside badminton predictions: forecasts for current matches rest on strength measured up to 2022.

## 3. Formula 1 — data and model

**Data (`data/real/f1/`).**
- Source: the Jolpica F1 CSV database dump (Ergast successor), CC BY-NC-SA 4.0, so noncommercial use only, like the tennis data. The free dump is available 14 days after upload. Claude asks before downloading, giving the file name and size.
- Seasons: 2014 (start of the hybrid era) to the latest race in the dump.
- `races.csv`: race_id, season, round, name, circuit, date, qualifying date, regulation era.
- `entries.csv`: one row per driver per race: race_id, driver, constructor, grid, qualifying position, finishing position, classified (yes/no), status, DNF type (mechanical or incident, mapped from status), points.
- `sprints.csv`: sprint results, used only as extra form evidence.
- `provenance.json`: source, license, checksums, as for the other sports.
- Only Grands Prix are predicted.

**Model (`matchlab/f1.py`, separate from the two-sided code).**
- Inputs per driver, built from races strictly before the cutoff:
  - driver form and constructor form: recency-weighted finishing results, with the half-life fixed in advance
  - gap to teammate
  - the driver's record at this circuit (missing if under a threshold)
  - DNF rates, split into mechanical and incident
  - first season of a new regulation set flag (2022, 2026)
  - stage 2 only: grid position (as log grid) and a pit-lane start flag
- Part 1: a logistic model for each driver's chance of not finishing.
- Part 2: a conditional logit (Plackett–Luce) over the finishing order of classified drivers, fitted by maximum likelihood with SciPy.
- Output: 10,000 seeded simulated races. In each, drivers retire with their DNF chance; the rest are ordered by Plackett–Luce; retirements go to the back. The result per driver is P(win), P(podium), P(points, top 10) and expected position.
- Fitted locally on races before the cutoff and cached in memory, like `trained.py`. Nothing is saved to disk.

**Evaluation (F1 path in `tools/evaluate_models.py`).**
- Hold out the last 20% of races by date. Score stage 1 (pre-weekend) and stage 2 (post-qualifying) separately.
- Metrics:
  - winner log loss across the field
  - top-pick win rate
  - podium Brier score
  - expected-position MAE
  - Spearman rank correlation between predicted and actual order
- Baselines:
  - every driver equally likely
  - each grid slot's historical win and podium rates (stage 2)
  - championship standings before the race (stage 1)
- "Beats baseline": paired bootstrap of the winner log-loss gap across races.

## 4. Formula 1 — engine, API and dashboard

**Engine.**
- `matchlab/sports.py`: add `f1` with `kind: "race"`; the existing sports are `kind: "match"`.
- `Engine` loads race sports through a new `RaceEngine` (in `f1.py`) and leaves `engine.py`'s two-sided path, `trained.py` and `ratings.py` unchanged.
- The catalog entry for F1 lists seasons, races and drivers instead of teams.

**API.** `POST /api/race` in `app.py`. It takes season, round, stage and an optional grid, and returns the field with each driver's probabilities, expected position and model provenance. For past races it also returns the actual result.

**Dashboard (`web/app.js`, `web/index.html`, `web/style.css`).**
- When F1 is selected, the team, opponent and player inputs are replaced by:
  - a race picker (season, then Grand Prix; defaults to the next race)
  - a pre-weekend / post-qualifying switch
- Post-qualifying uses the official grid. For an upcoming race the grid is fetched from the Jolpica API when the user presses "Check updates": one cached request with a generic user-agent. It stays editable for grid penalties, and can be typed in by hand if the fetch fails.
- Results table: driver, constructor, grid, win %, podium %, points %, expected position. It also shows the existing low-confidence badge (from the measured comparison) and the data-provenance card. Past races show the actual result beside the forecast.
- Today's matches: an F1 tab from the ESPN racing scoreboard (same feed family as the other sports). Selecting a race opens it in the race view.

## Error handling

- Missing data never becomes an invented value. Missing inputs are imputed with training medians, as in `trained.py`, and the provenance says so.
- A driver with no prior races in the window still gets a forecast from constructor form, flagged as low history.
- If the live grid fetch fails, the post-qualifying stage asks for a manual grid and stays unavailable until one is given.
- If the badminton Kaggle file is absent, the importer keeps the ShuttleSet-only data and reports the missing source.

## Testing

- `tests/test_f1.py`:
  - causality: no input uses a result at or after its cutoff
  - win probabilities add up to 1
  - each driver's podium chance ≥ win chance, and points chance ≥ podium chance
  - seeded simulations are deterministic
  - importer checked on a small fixture
- Cricket:
  - the season pull-back is applied at the season boundary
  - stage 1 inputs exclude toss and XI data
  - home grounds are derived only from earlier seasons
- Badminton: name conversion; removal of fixtures present in both sources; score parsing or the score model reporting unavailable.
- The existing suite (`tests/test_models.py`, `test_system.py`, `test_pretrained.py`, `test_live.py`) keeps passing.

## Documentation

- `DATA_SOURCES.md`: add the Jolpica and Kaggle sources, licenses and limitations.
- `MODEL_COMPARISON.md` and `EVALUATION.md`: regenerated from the new evaluation.
- `README.md`: an F1 section.

## Out of scope

- Sprint race forecasts; F1 qualifying forecasts; weather.
- Recent badminton results after 2022 (no licensed source found).
- Commercial use of F1 or tennis data (both noncommercial licenses).
