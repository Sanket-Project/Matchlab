# Held-out winner accuracy — 11 November 2026

**Overall winner accuracy for the IPL, badminton and Formula 1 stages was 60.6% (420 correct picks in 693 held-out events).** Each event contributes once. The total uses IPL post-toss, the selected badminton model and Formula 1 post-qualifying. Accuracy counts the events where the highest-probability pick won. Earlier stages appear below so the same IPL matches and Grands Prix are counted once in the total.

| Sport and stage | Winner model | Correct / evaluated | Accuracy | Winner log loss |
| --- | --- | ---: | ---: | ---: |
| IPL pre-match | TabICL | 124 / 239 | 51.9% | 0.694 |
| IPL pre-match | Trained logistic | 113 / 239 | 47.3% | 0.708 |
| IPL post-toss | Trained logistic | 116 / 239 | 48.5% | 0.706 |
| Badminton | Elo | 265 / 400 | 66.25% | 0.605 |
| Badminton | Trained logistic | 270 / 400 | 67.5% | 0.595 |
| Formula 1 pre-weekend | Logistic retirement + Plackett–Luce | 12 / 54 | 22.2% | 2.141 |
| Formula 1 post-qualifying | Logistic retirement + Plackett–Luce | 34 / 54 | 63.0% | 1.376 |

The backtests freeze training before the chronological 80/20 boundary. They score 239 IPL matches from 3 May 2023, 400 evenly spaced matches from 695 eligible badminton matches from 29 October 2019, and all 54 Grands Prix from 21 July 2024. Earlier completed results may enter subsequent features. The badminton model was chosen by log loss on the same holdout, which may make the estimate optimistic. Badminton results end in October 2022. The F1 post-qualifying backtest uses recorded starting grids, which can include later penalties.

Neither IPL stage beat the no-skill baseline on winner log loss. Both trained badminton outcome models beat it. Formula 1 beat a uniform field in both stages. The championship-standings baseline had lower pre-weekend log loss, and the starting-grid baseline matched the post-qualifying model's 34 correct winner picks and had slightly lower log loss. See [the full model comparison](MODEL_COMPARISON.md) and [machine-readable results](artifacts/model-comparison.json).

## Earlier pretrained-model evaluation — 10 November 2026

Actual original TabICLv2 classifier/regressor and Amazon Chronos-Bolt Small weights, CPU, with outbound sockets and external DNS disabled. No models were trained or fine-tuned. Original weight checksums remained unchanged.

## Protocol

For each real sport dataset, the date at approximately 80% of matches defines a holdout boundary. All TabICL labeled context is frozen **strictly before that boundary** (up to 192 rows, 2 ensemble members). Each historical context row's features use only records available before its own match. Both orientations of a match stay together. Up to 32 eligible matches are selected deterministically at evenly spaced positions across the remaining period; no random train/test split is used.

Held-out features are walk-forward: a test match may use previously completed held-out results, but never its own result, same-day results, or later results. None of the held-out labels enters TabICL fit(). Tennis uses tournament start for the feature cutoff and start +14 days for result availability, excluding same-tournament results. Chronos also receives only pre-match scores. Settings were fixed before evaluation; there was no search, tuning, or calibration on these samples.

These are small samples, **not demonstrated reliable sports accuracy**. Team histories are old snapshots. Upstream pretrained-corpus overlap cannot be independently audited.

## Outcomes and side scores

| Sport | Frozen context boundary | Matches | Accuracy | Log loss | Brier (sum over classes) | Side labels | TabICL MAE | Recent-5 mean MAE | Unit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| football | 2023-12-09 | 32 | 50.0% | 1.094 | 0.663 | 64 | 1.198 | 1.084 | goals |
| cricket | 2024-04-04 | 32 | 40.6% | 0.784 | 0.586 | 64 | 27.934 | 31.097 | runs |
| tennis | 2024-07-15 | 32 | 65.6% | 0.674 | 0.481 | 64 | 0.800 | 0.792 | sets |
| badminton | 2022-07-03 | 6 | 66.7% | 0.934 | 0.604 | 12 | 0.896 | 0.797 | games |
| baseball | 2023-08-26 | 32 | 46.9% | 0.759 | 0.560 | 64 | 2.684 | 2.312 | runs |
| rugby | 2015-02-13 | 32 | 62.5% | 0.700 | 0.477 | 64 | 7.957 | 8.634 | points |

Lower log loss/Brier/MAE is better. Classifier accuracy alone is insufficient: uniform log loss is 1.099 for three outcomes and 0.693 for two. Worse than uniform on log loss: cricket, badminton, baseball. Side-score regression did not beat the recent-mean baseline: football, tennis, badminton, baseball. Rugby outcome accuracy tied the context-majority baseline (62.5%). Badminton outcome accuracy was 66.7% versus an 83.3% context-majority baseline; six matches are too few to establish accuracy.

## Individual players and interaction targets

| Sport | Target | Labels | TabICL MAE | Historical baseline MAE | Unit |
| --- | --- | --- | --- | --- | --- |
| cricket | player_score | 32 | 12.240 | 13.209 | runs |
| cricket | player_threat | 32 | 0.227 | 0.213 | pair-match success fraction |
| tennis | player_score | 32 | 4.481 | 3.394 | aces |
| tennis | player_threat | 32 | 0.047 | 0.051 | pair-match success fraction |

Player-score baseline is the last-five appearance mean. Threat baseline is the selected player's previous observed success fraction against all opposing players. Threat targets are actual success fractions **per pair-match**, with equal example weight, not per-event probability labels. Cricket measures boundaries on non-wide deliveries against a bowler; tennis measures total match points won against the other competitor; badminton uses observed terminal scoreboard point fractions. Tennis aces regression was worse than its historical baseline. Missing football/baseball/rugby interactions produce no player-threat result. Badminton remains a small selected sample; early cutoffs can still block its player contexts.

## Chronos scoring form (separate from opponent-adjusted predictions)

| Sport | Series | Labels | Median forecast MAE | Observed 10–90 quantile coverage | Unit |
| --- | --- | --- | --- | --- | --- |
| football | side | 64 | 1.073 | 76.6% | goals |
| cricket | side | 64 | 30.884 | 76.6% | runs |
| cricket | player | 24 | 13.673 | 79.2% | runs |
| tennis | side | 57 | 0.807 | 77.2% | sets |
| tennis | player | 29 | 3.077 | 79.3% | aces |
| badminton | side | 6 | 0.453 | 83.3% | games |
| badminton | player | 5 | 4.058 | 100.0% | points |
| baseball | side | 64 | 2.251 | 81.2% | runs |
| rugby | side | 64 | 7.982 | 71.9% | points |

Chronos consumes the last 8–64 available scores in appearance order, ignores opponent/venue/calendar spacing, and predicts one next appearance. The displayed value is the median, not an expected-score mean. Model quantiles are clipped to legal target ranges and are not calibrated sports confidence intervals. Badminton has especially few eligible held-out form labels; no accuracy conclusion can be drawn. Team-score TabICL and Chronos sample sizes differ when series lack eight prior observations.

## Availability and audit trail

- **football**: player_score: No eligible held-out examples; player_threat: No eligible held-out examples; chronos_player_form: Insufficient chronological scoring history: Chronos needs at least 8 pre-cutoff appearances per selected team/player.

- **badminton**: player_score: Insufficient labeled context: 19 eligible player_score examples; need at least 24. Add real historical data or choose a later cutoff.; player_threat: Insufficient labeled context: 19 eligible player_threat examples; need at least 24. Add real historical data or choose a later cutoff.

- **baseball**: player_score: No eligible held-out examples; player_threat: No eligible held-out examples; chronos_player_form: Insufficient chronological scoring history: Chronos needs at least 8 pre-cutoff appearances per selected team/player.

- **rugby**: player_score: No eligible held-out examples; player_threat: No eligible held-out examples; chronos_player_form: Insufficient chronological scoring history: Chronos needs at least 8 pre-cutoff appearances per selected team/player.


Exact per-match predictions, truth, cutoffs and context/history end dates: [artifacts/evaluation.json](artifacts/evaluation.json). Reproduce offline with `.venv\Scripts\python.exe tools\evaluate_pretrained.py --matches 32`. Original-weight smoke outputs: [artifacts/real-inference-report.json](artifacts/real-inference-report.json). Test transcript: [artifacts/tests-full.log](artifacts/tests-full.log).
