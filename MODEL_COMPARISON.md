# Model comparison on held-out events — 11 November 2026

The chronological split is at the date of the 80% boundary for each sport. Model fitting stops before that boundary. Earlier completed results can update the features of subsequent events. The match evaluation uses up to 400 evenly spaced eligible matches per sport.

Lower log loss means better probability estimates. The no-skill match baseline uses the training outcome frequencies. A model beats a baseline when the 95% paired-bootstrap interval for its log-loss gap is entirely below zero. Models selected by their performance on this holdout may have optimistic estimates.

## Match outcomes

| Sport | Matches | Model | Accuracy ± 95% margin | Log loss | Beats baseline | Dashboard |
| --- | ---: | --- | ---: | ---: | --- | --- |
| football | 230 | No-skill baseline | 45.65% ± 6.4 points | 1.073 | — |  |
| football | 230 | Elo rating model | 55.65% ± 6.4 points | 0.943 | Yes | Yes |
| football | 230 | Trained logistic | 56.96% ± 6.4 points | 0.948 | Yes |  |
| football | 230 | Gradient boosting | 53.91% ± 6.4 points | 1.044 | No |  |
| football | 230 | TabICL (pretrained) | 50.87% ± 6.5 points | 1.121 | No |  |
| cricket | 239 | No-skill baseline | 45.19% ± 6.3 points | 0.693 | — |  |
| cricket | 239 | Elo rating model | 51.05% ± 6.3 points | 0.701 | No |  |
| cricket | 239 | Trained logistic | 47.28% ± 6.3 points | 0.708 | No |  |
| cricket | 239 | Gradient boosting | 53.14% ± 6.3 points | 0.720 | No |  |
| cricket | 239 | TabICL (pretrained) | 51.88% ± 6.3 points | 0.694 | No | Yes |
| cricket, post-toss | 239 | Trained logistic | 48.54% ± 6.3 points | 0.706 | No | Yes |
| tennis | 400 | No-skill baseline | 53.75% ± 4.9 points | 0.693 | — |  |
| tennis | 400 | Elo rating model | 58.25% ± 4.8 points | 0.652 | Yes | Yes |
| tennis | 400 | Trained logistic | 60.25% ± 4.8 points | 0.660 | No |  |
| tennis | 400 | Gradient boosting | 61.00% ± 4.8 points | 0.649 | Yes |  |
| tennis | 400 | TabICL (pretrained) | 54.25% ± 4.9 points | 0.691 | No |  |
| badminton | 400 | No-skill baseline | 48.50% ± 4.9 points | 0.693 | — |  |
| badminton | 400 | Elo rating model | 66.25% ± 4.6 points | 0.605 | Yes |  |
| badminton | 400 | Trained logistic | 67.50% ± 4.6 points | 0.595 | Yes | Yes |
| badminton | 400 | Gradient boosting | 65.00% ± 4.7 points | 0.613 | Yes |  |
| badminton | 400 | TabICL (pretrained) | 58.25% ± 4.8 points | 0.673 | No |  |
| baseball | 400 | No-skill baseline | 50.00% ± 4.9 points | 0.693 | — |  |
| baseball | 400 | Elo rating model | 52.50% ± 4.9 points | 0.692 | No | Yes |
| baseball | 400 | Trained logistic | 52.75% ± 4.9 points | 0.696 | No |  |
| baseball | 400 | Gradient boosting | 51.75% ± 4.9 points | 0.708 | No |  |
| baseball | 400 | TabICL (pretrained) | 48.25% ± 4.9 points | 0.763 | No |  |
| rugby | 125 | No-skill baseline | 56.00% ± 8.7 points | 0.738 | — |  |
| rugby | 125 | Elo rating model | 63.20% ± 8.5 points | 0.712 | No | Yes |
| rugby | 125 | Trained logistic | 56.80% ± 8.7 points | 0.732 | No |  |
| rugby | 125 | Gradient boosting | 63.20% ± 8.5 points | 0.762 | No |  |
| rugby | 125 | TabICL (pretrained) | 56.00% ± 8.7 points | 0.800 | No |  |

## Side scores

Mean absolute error per side in the sport’s scoring units.

| Sport | Unit | Last-5 average | Trained ridge | TabICL | Dashboard |
| --- | --- | ---: | ---: | ---: | --- |
| football | goals | 1.106 | 1.003 | 1.049 | trained_ridge |
| cricket | runs | 31.090 | 30.597 | 31.347 | trained_ridge |
| cricket, post-toss | runs | 31.090 | 30.390 | — | trained_ridge |
| tennis | sets | 0.813 | 0.757 | 0.819 | trained_ridge |
| badminton | games | 0.790 | 0.698 | 0.817 | trained_ridge |
| baseball | runs | 2.787 | 2.571 | 2.750 | trained_ridge |
| rugby | points | 8.959 | 8.534 | 8.790 | trained_ridge |

## Formula 1

Both stages score the same 54 Grands Prix, beginning 21 July 2024. Fitting stops before the first held-out race weekend. The post-qualifying stage uses the recorded starting grid, which may include penalties assigned after qualifying.

| Stage | Correct winner picks | Winner log loss | Podium Brier | Finish-position MAE | Spearman rank correlation |
| --- | ---: | ---: | ---: | ---: | ---: |
| Pre-weekend | 12 / 54 (22.2%) | 2.141 | 0.091 | 3.73 | 0.584 |
| Post-qualifying | 34 / 54 (63.0%) | 1.376 | 0.067 | 3.34 | 0.686 |

| Stage | Baseline | Baseline winner accuracy | Baseline winner log loss | Model gap with 95% interval |
| --- | --- | ---: | ---: | --- |
| Pre-weekend | Uniform | 4.9% | 3.027 | -0.885 (-0.965 to -0.802) |
| Pre-weekend | Championship standings | 26.1% | 1.991 | +0.150 (+0.010 to +0.291) |
| Post-qualifying | Uniform | 4.9% | 3.027 | -1.650 (-1.819 to -1.457) |
| Post-qualifying | Starting grid | 63.0% | 1.365 | +0.011 (-0.283 to +0.245) |

## Interpretation

- **IPL.** Both stages missed the no-skill threshold. TabICL has the lowest pre-match log loss among the dashboard models. The trained logistic pre-match comparison uses season-aware Elo, ground history and prior-XI features. Its post-toss variant uses the current toss and announced XIs.
- **Badminton.** Both trained outcome models beat the no-skill baseline. Trained logistic was selected by holdout log loss. Results end in October 2022.
- **Formula 1.** Both stages beat the uniform baseline. Championship standings had lower pre-weekend log loss. The grid baseline matched post-qualifying top-pick accuracy and had slightly lower log loss.
- **Side scores.** The trained ridge model had the lowest mean absolute error for all six match sports.
- **Probability ensemble.** A chronological Elo + logistic blend improved football log loss from 0.943 to 0.941 and was effectively tied with Elo on tennis (0.652). It was not selected for badminton, baseball or rugby because their specialist models were at least as good on the same holdout.

Reproduce the comparison with `.\.venv\Scripts\python.exe tools\evaluate_models.py`. For the project stages only, add `--sports cricket badminton f1`. See [the machine-readable results](artifacts/model-comparison.json).
