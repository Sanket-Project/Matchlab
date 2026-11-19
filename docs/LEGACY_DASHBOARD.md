# MatchLab — offline sports intelligence

A local interactive dashboard for **football, cricket, tennis, badminton, baseball, and rugby**. Includes match outcome estimates, both sides' expected scores, individual expected scores, recent form charts, head-to-head results, and directional player-vs-player threat analysis.

## Run on this laptop

Requires Python 3.10 or later. **The dashboard and sample mode require no third-party packages, installation, internet connection, or API keys.**

```powershell
Set-Location 'D:\Sports Prediction'
python app.py --open
```

Open [MatchLab](http://127.0.0.1:8765). Stop with Ctrl+C. If that port is in use, run `python app.py --port 8766 --open`.

You can also double-click `start.cmd`.

## Current model/data status

The supplied workspace was empty. A filename search of `D:\` and `C:\Users\admin` found audio/speech, background-removal, editor-assistance models and package test fixtures, **no identifiable sports prediction artifacts**. Some directories may be inaccessible; this is not proof that no suitable model exists elsewhere. No discovered model was executed or altered. See [MODEL_DISCOVERY.md](MODEL_DISCOVERY.md).

The included six datasets are **fictional synthetic demonstrations**, not real results. No ML model is bundled, downloaded, trained, or fabricated. Default numeric outputs use explicitly labeled historical arithmetic to exercise the entire UI. They are **not validated ML predictions**, and reference percentages are **not calibrated probabilities**. All six sports have 90 sample matches, player records, and interaction records.

Genuine ML inference requires an already trained, task-appropriate local model with its original feature/preprocessing contract and real local data. A general speech, image, or language model cannot be treated as a sports outcome predictor. NVIDIA and other providers' models are usable if they meet a supported numeric inference contract. Models must be evaluated for the intended sport, competition, and scoring format.

## Connect your files

1. Prepare one local folder per sport with `matches.csv` and optional `players.csv` and `interactions.csv` using the schemas below. Keep different formats (e.g. T20 vs Test cricket; singles vs doubles) in separate datasets. Choose the intended dataset using the configuration.
2. Copy `config.example.json` to `config.local.json`, change paths and feature lists to match your artifacts, remove task entries you do not have, and restart. Relative paths resolve against the project directory. Use forward slashes or escaped backslashes in JSON. `--config D:/path/to/config.json` selects another config.
3. Alternatively, edit JSON under **Data & models → Validate & apply**. This validates all CSVs and applies the configuration in memory. Model cards check file/runtime availability; actual inference validates the model contract. To persist, **Export config** and place `config.local.json` in the project folder. The app never overwrites configuration, data, or model files.
4. Add sport keys `football`, `cricket`, `tennis`, `badminton`, `baseball`, `rugby` under `sports` as needed. Only configured sports appear in the picker. **Reload local files** re-reads CSVs and clears model caches after you update your local files.

Minimal real-data configuration (produces charts; forecasts unavailable until you configure models):

```json
{
  "sports": {
    "cricket": {
      "data_dir": "D:/SportsData/cricket",
      "demo": false,
      "reference_mode": false,
      "models": {}
    }
  }
}
```

Set `reference_mode` to `true` only if you want historical arithmetic alongside real data. A configured model that fails **never silently falls back**. Its output is unavailable with an explanation. Models are optional per task and never shared automatically across sports. The same side-score model is called twice, swapping focal side/opponent and the venue flags.

## CSV contracts

UTF-8 or UTF-8 with BOM, comma-separated, headers required. One match row per match; unique match IDs within each sport. All scores must be finite nonnegative numbers. Dates are local calendar dates in `YYYY-MM-DD` format. Limit: 250,000 rows per file.

**matches.csv** (required):

```csv
match_id,date,team,opponent,team_score,opponent_score,outcome
m001,2026-10-01,Northbridge FC,Eastvale FC,2,1,team
m002,2026-10-04,Eastvale FC,Northbridge FC,1,1,draw
```

`team` and `opponent` are side identifiers, **not home/away indicators**. `outcome` is exactly `team`, `opponent`, or `draw`; recorded results determine form. Draws are rejected for tennis, badminton, and baseball. Keep extra-time/penalty and regulation outcomes consistent with the model's training target. The supplied sample excludes abandoned/no-result matches.

**players.csv** (optional):

```csv
match_id,player,team,score
m001,Aarav Mehta,Northbridge FC,1
m001,Leo Bennett,Eastvale FC,0
```

One appearance per player per match; include zero scores. Use stable, unique player identifiers/names across seasons (disambiguate namesakes). Transfers are filtered by the selected side. For singles sports use competitor names in `team`/`opponent` and the corresponding player name in `players.csv`.

**interactions.csv** (optional, requires corresponding player appearances):

```csv
match_id,player,opponent_player,opportunities,successes,score
m001,Aarav Mehta,Leo Bennett,5,2,0
```

Directional: numerator and `score` belong to `player`, facing `opponent_player`. Both must appear on opposing sides in that match. `opportunities` > 0; 0 <= `successes` <= `opportunities`. Multiple event rows per pair/match are aggregated over the last N **distinct meetings**. `score` is the actual score attributed to the selected player against that opposing player (e.g. runs off a bowler, goals involving a defender); it is **not** automatically equal to successes. It supplies `interaction_avg_score`, not the global player-score target. The threat denominator must match this table:

| Sport | Side score | Player score | Threat successes / opportunities |
|---|---|---|---|
| Football | Goals | Goals | Successful take-ons / duels |
| Cricket | Runs | Runs | Boundaries / balls faced |
| Tennis | Sets | Aces | Points won / points played |
| Badminton | Games | Points | Rallies won / rallies played |
| Baseball | Runs | Hits | Hits / plate appearances |
| Rugby | Points | Points | Line breaks / carries |

Do not mix scoring targets, missing appearances, or definitions within a dataset. Fractional forecast scores are expectations, not exact final scorelines. Pair threat is a defined action rate, not a universal measure of how dangerous a player is.

## Model adapters

All inputs are **one numeric row in the ordered `features` list**. Feature values are computed before the prediction date. The complete feature dictionary, exact values, sources and model hashes are available in the dashboard. **Do not guess feature meaning, order, scaling, class mapping, or missing-value conventions**. Include the existing preprocessing in the saved pipeline/graph or provide a compatible artifact; the app does not fit scalers, impute missing features, encode arbitrary categories, or train models.

| `format` | Artifact | Local runtime | Details |
|---|---|---|---|
| `onnx` | `.onnx` | numpy, onnxruntime | One numeric feature tensor. Dense numeric output selected with `output_index` (default 0). `dtype` defaults to float32. ZipMap and multiple inputs require a suitable existing export. |
| `joblib` | `.joblib` / compatible serialized pipeline | numpy, joblib, training framework; pandas for dataframe input | `input` is `array` (default) or `dataframe`. Winner requires `predict_proba`, `classes` matching `model.classes_` exactly, and corresponding semantic `labels`. |
| `torchscript` | scripted/traced `.pt` | numpy, torch | CPU, eval mode, `inference_mode`. One numeric tensor in, one numeric tensor out. Arbitrary state dictionaries and architecture-free `.pth` files are not supported. |
| `keras` | `.keras`, compatible full `.h5` | numpy, tensorflow | Full existing model with preprocessing, compile=False, safe_mode=True, training=False. Custom architecture/code dependencies may require an adapter extension. |
| `linear_json` | existing documented JSON numeric artifact | standard library only | Inference for pre-existing linear numeric artifacts. No fitting/export/training performed. Exact schema below. |

The app never installs packages. Use an environment containing the model's original dependencies, or install from **your own prepared local wheelhouse** (not the internet). Python-version compatibility matters; many ML packages may require Python 3.11/3.12 rather than this laptop's default 3.14. No `requirements.txt` installation is needed for the dashboard itself. `requirements-optional.txt` is a reference list of adapter runtimes, not a required bootstrap step.

Tasks and outputs:

- `winner`: exactly 2 (`team`, `opponent`) or 3 (including `draw`) probabilities in `labels` order, each in [0,1], summing to 1. Logits are rejected; export original softmax with the graph. A draw output is invalid for the three sports without draws.
- `team_score`: one nonnegative expected score for the focal side; called for both sides.
- `player_score`: one nonnegative expected player score in that sport's player unit.
- `player_threat`: one value in [0,1] matching the defined threat event.

Serialized joblib, TorchScript, and Keras models require `trusted: true`. Set this only for an artifact whose provenance you trust; some formats can execute code during loading. Unknown automatically discovered models are not deserialized. SHA-256 is recorded with each real model prediction. Supply `sha256` in the task config for checksum verification. Original model files are read only. Model caching is per task and invalidated when the path, size or modification timestamp changes or when local files are reloaded.

Existing linear JSON artifact schema (weights are output rows, bias is an output vector):

```json
{
  "features": ["team_recent_avg", "opponent_recent_conceded"],
  "weights": [[0.6, 0.4]],
  "bias": [0],
  "activation": "identity"
}
```

`activation`: `identity`, `sigmoid`, or `softmax`. This schema illustrates the interface; **these coefficients are not a trained or validated sports model**. Do not substitute them for one. The integration tests use temporary hand-authored artifacts only to verify adapters and never expose them as forecasts.

## Reference methods and leakage prevention

- Team scores: 55% own recent scoring mean + 30% opponent recent conceded mean + 15% own mean against that opponent. If no head-to-head data, use own recent mean for the last term.
- Winner shares: pool own wins with opponent losses, pool own losses with opponent wins, pool draws (if permitted); add one pseudocount per outcome and normalize. **These are not calibrated probabilities.** Equal maxima display “No clear edge.”
- Player score: 75% recent mean + 25% mean vs selected side (fallback: recent mean).
- Threat reference: direct successes / opportunities. No interactions yields unavailable, not zero or a made-up prior.
- Form uses the last N matches for each side; head-to-head and player pair interactions use the last N meetings. Player form uses last N appearances for the selected side. **Every match on or after the prediction date is excluded** from every historical feature and chart. Model training-data leakage cannot be detected from an arbitrary artifact; verify training cutoffs independently.
- No accuracy or confidence claims are displayed. Inference tests check correctness of integration, not predictive accuracy on real sports. Validation against held-out real outcomes remains necessary.

## Offline operation and privacy

The Python server binds exclusively to **127.0.0.1**. Frontend JavaScript, CSS, SVG charts, icons, and system fonts are local. No remote scripts, fonts, analytics, telemetry, API calls, model downloads, cloud services, accounts, or data uploads are used. Content Security Policy blocks external browser requests. The server checks Host and Origin headers and a session token on POST requests; no permissive CORS. CSV/config/model paths are never served as static files. URLs and UNC network shares are rejected as input paths.

Offline environment flags disable common ML hub/telemetry behaviors. An in-process socket guard rejects non-loopback Python TCP/UDP connections and external DNS. This guard is an additional precaution, not an OS sandbox for hostile native/model code; only load trusted model artifacts. All configuration and inference state stays in memory. Exports are explicit local browser downloads. No payloads or paths are logged by the HTTP server. The only generated files are project source, synthetic sample CSVs, local tests and test screenshots.

## Verify

```powershell
python -m unittest discover -s tests -v
node --check web/app.js
```

Tests cover all sports, time cutoffs, opponent queries, direct interactions, exact numerical inference from a temporary artifact, invalid outputs/feature contracts, no silent fallback, read-only model integrity, CSV validation, config rollback, local HTTP endpoints, and offline TCP/DNS rejection. Optional model adapters need their actual runtime and supplied models for end-to-end validation; those cannot be validated with absent artifacts.

Project: `app.py` local server; `matchlab/` validation, analytics and inference; `web/` offline frontend; `data/demo/` fictional CSVs; `tools/generate_demo.py` deterministic synthetic-data generator (no ML training); `tests/` integration tests.
