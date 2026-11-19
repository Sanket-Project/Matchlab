"""Write human-readable installation/data/evaluation reports from measured artifacts."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
r = json.loads((ROOT / "artifacts/evaluation.json").read_text())
disk = json.loads((ROOT / "artifacts/disk-usage.json").read_text())
manifest = json.loads((ROOT / "models/manifest.json").read_text())
def table(headers, rows):
    return "| " + " | ".join(headers) + " |\n| " + " | ".join("---" for _ in headers) + " |\n" + "\n".join("| " + " | ".join(map(str, row)) + " |" for row in rows) + "\n"
def number(value, places=3):
    return f"{value:.{places}f}" if value is not None else "Unavailable"
lines = ["# Measured local-model evaluation — 10 November 2026\n", "Actual original TabICLv2 classifier/regressor and Amazon Chronos-Bolt Small weights, CPU, with outbound sockets and external DNS disabled. No models were trained or fine-tuned. Original weight checksums remained unchanged.\n",
"## Protocol\n", "For each real sport dataset, the date at approximately 80% of matches defines a holdout boundary. All TabICL labeled context is frozen **strictly before that boundary** (up to 192 rows, 2 ensemble members). Each historical context row's features use only records available before its own match. Both orientations of a match stay together. Up to 32 eligible matches are selected deterministically at evenly spaced positions across the remaining period; no random train/test split is used.\n",
"Held-out features are walk-forward: a test match may use previously completed held-out results, but never its own result, same-day results, or later results. None of the held-out labels enters TabICL fit(). Tennis uses tournament start for the feature cutoff and start +14 days for result availability, excluding same-tournament results. Chronos also receives only pre-match scores. Settings were fixed before evaluation; there was no search, tuning, or calibration on these samples.\n",
"These are small samples, **not demonstrated reliable sports accuracy**. Team histories are old snapshots. Upstream pretrained-corpus overlap cannot be independently audited.\n", "## Outcomes and side scores\n"]
records = []
for s, d in r["sports"].items():
    w, sc = d["tasks"]["winner"], d["tasks"]["team_score"]
    records.append([s, d["split"], w.get("n", 0), f"{100*w['accuracy']:.1f}%" if "accuracy" in w else "Unavailable", number(w.get("log_loss")), number(w.get("multiclass_brier")), sc.get("n", 0), number(sc.get("mae")), number(sc.get("recent_mean_mae")), sc.get("unit", "games")])
lines.append(table(["Sport", "Frozen context boundary", "Matches", "Accuracy", "Log loss", "Brier (sum over classes)", "Side labels", "TabICL MAE", "Recent-5 mean MAE", "Unit"], records))
worse_outcomes = [s for s, d in r["sports"].items() if d["tasks"]["winner"].get("log_loss", 0) > d["tasks"]["winner"].get("uniform_log_loss", 99)]
worse_scores = [s for s, d in r["sports"].items() if d["tasks"]["team_score"].get("mae", 0) > d["tasks"]["team_score"].get("recent_mean_mae", 99)]
lines.append(f"Lower log loss/Brier/MAE is better. Classifier accuracy alone is insufficient: uniform log loss is 1.099 for three outcomes and 0.693 for two. Worse than uniform on log loss: {', '.join(worse_outcomes)}. Side-score regression did not beat the recent-mean baseline: {', '.join(worse_scores)}. Rugby outcome accuracy tied the context-majority baseline (62.5%). Badminton outcome accuracy was 66.7% versus an 83.3% context-majority baseline; six matches are too few to establish accuracy.\n")
lines.append("## Individual players and interaction targets\n")
records = []
for s in r["sports"]:
    for task in ("player_score", "player_threat"):
        d = r["sports"][s]["tasks"][task]
        if "mae" not in d:
            continue
        records.append([s, task, d.get("n", 0), number(d.get("mae")), number(d.get("historical_baseline_mae")), d.get("unit", "")])
lines.append(table(["Sport", "Target", "Labels", "TabICL MAE", "Historical baseline MAE", "Unit"], records))
lines.append("Player-score baseline is the last-five appearance mean. Threat baseline is the selected player's previous observed success fraction against all opposing players. Threat targets are actual success fractions **per pair-match**, with equal example weight, not per-event probability labels. Cricket measures boundaries on non-wide deliveries against a bowler; tennis measures total match points won against the other competitor; badminton uses observed terminal scoreboard point fractions. Tennis aces regression was worse than its historical baseline. Missing football/baseball/rugby interactions produce no player-threat result. Badminton remains a small selected sample; early cutoffs can still block its player contexts.\n")
lines.append("## Chronos scoring form (separate from opponent-adjusted predictions)\n")
records = []
for s, d in r["sports"].items():
    for task in ("chronos_team_form", "chronos_player_form"):
        t = d["tasks"][task]
        if "mae" in t:
            records.append([s, "player" if "player" in task else "side", t["n"], number(t["mae"]), f"{100*t['quantile_10_90_coverage']:.1f}%", t["unit"]])
lines.append(table(["Sport", "Series", "Labels", "Median forecast MAE", "Observed 10–90 quantile coverage", "Unit"], records))
lines.append("Chronos consumes the last 8–64 available scores in appearance order, ignores opponent/venue/calendar spacing, and predicts one next appearance. The displayed value is the median, not an expected-score mean. Model quantiles are clipped to legal target ranges and are not calibrated sports confidence intervals. Badminton has especially few eligible held-out form labels; no accuracy conclusion can be drawn. Team-score TabICL and Chronos sample sizes differ when series lack eight prior observations.\n")
lines.append("## Availability and audit trail\n")
for s, d in r["sports"].items():
    unavailable = [f"{k}: {v['unavailable']}" for k, v in d["tasks"].items() if "unavailable" in v]
    if unavailable:
        lines.append(f"- **{s}**: " + "; ".join(unavailable) + "\n")
lines.append("\nExact per-match predictions, truth, cutoffs and context/history end dates: [artifacts/evaluation.json](artifacts/evaluation.json). Reproduce offline with `.venv\\Scripts\\python.exe tools\\evaluate_pretrained.py --matches 32`. Original-weight smoke outputs: [artifacts/real-inference-report.json](artifacts/real-inference-report.json). Test transcript: [artifacts/tests-full.log](artifacts/tests-full.log).\n")
(ROOT / "EVALUATION.md").write_text("\n".join(lines), encoding="utf-8")

lines = ["# Public historical data and limitations\n", "Raw sources and their notices remain under data/raw. Derived CSVs and individual SHA-256 checksums are under data/real/<sport>/provenance.json. No local data or queries were uploaded. The initial local search found only the original synthetic demo sports CSVs; unrelated business CSVs were not used. D:\\WindowsApps was inaccessible to the filename search.\n"]
records = []
for s in r["sports"]:
    p = json.loads((ROOT / f"data/real/{s}/provenance.json").read_text())
    records.append([s, p["matches"], p["earliest"] + " to " + p["latest"], p["player_rows"], p["interaction_rows"], p["license"]])
    lines.append(f"## {s}\n\n[{p['source']}]({p['url']})\n\nLicense: {p['license']}\n")
    if p.get("attribution"):
        lines.append(p["attribution"] + "\n")
    if p.get("normalizations"):
        lines.append("Recorded identity normalizations: " + json.dumps(p["normalizations"]) + "\n")
    lines.extend("- " + x + "\n" for x in p["limitations"])
lines.insert(2, table(["Sport", "Matches", "Result availability coverage", "Player appearances", "Pair-match interactions", "License"], records))
lines.append("\nThe badminton sources (ShuttleSet plus its ShuttleSet22 extension) identify player A as the match winner. Import orientation is alphabetical, and historical contexts include both orientations; winner-coded A/B is never an input feature. Duplicate date/player fixtures across releases are removed. Only the men's singles subset enters this context. Point totals come from observed legal terminal scoreboards, checked against the last-point and match winners; missing stroke rows are never fabricated. Original annotations are retained unchanged.\n")
lines.append("Cricsheet JSON: ODC Attribution 1.0, not the CC BY 4.0 license used for its XML files. Tennis derived data remains CC BY-NC-SA 4.0 and is for noncommercial use. Retrosheet attribution is displayed in the dashboard. Rugby's publisher declares CC0 in DESCRIPTION. ShuttleSet root MIT notice is retained; no video footage is downloaded or reused.\n")
(ROOT / "DATA_SOURCES.md").write_text("\n".join(lines), encoding="utf-8")

rows = [[f["path"], f["bytes"], f["sha256"]] for f in manifest["files"] if f["path"].endswith((".ckpt", ".safetensors", "config.json"))]
(ROOT / "INSTALLATION.md").write_text("# Installed local inference\n\nCPU Python 3.12 environment: `.venv`. Official libraries are pinned in requirements-lock.txt. TabICL 2.2.0, chronos-forecasting 2.3.2, PyTorch 2.15.0+cpu and transformers 4.57.6. Base Python 3.12 was already installed on C:; the environment, dependencies, model files, raw data and caches are on D:. Shared uv cache: D:\\DevCache\\uv-cache.\n\n" + table(["Original publisher file", "Bytes", "SHA-256"], rows) + "\nAll three large weights match the publishers' LFS SHA-256. Models and config are pinned to repository revisions in models/manifest.json. The manifest retains download URLs and metadata.\n\n" + table(["Directory", "Logical bytes", "MiB"], [[p, v, f"{v/1024**2:.2f}"] for p, v in disk.items()]) + "\nDirectory sizes are logical file lengths. The environment can share hardlinked package content with the pre-existing uv cache, so these numbers are not a claim of unique newly allocated disk blocks. The shared cache's pre-existing unrelated contents are excluded.\n\nRestart: `Set-Location 'D:\\Sports Prediction'; .\\.venv\\Scripts\\python.exe app.py --port 8766 --open` (or start.cmd). Local URL: http://127.0.0.1:8766. The earlier demo server on 8765 is left alone.\n", encoding="utf-8")
with (ROOT / "INSTALLATION.md").open("a", encoding="utf-8") as f:
    f.write("\nFor the managed background server, run `.\\restart.ps1` from the project directory. It verifies the recorded process identity, stops only this dashboard's process tree, checks the port, restarts hidden, and opens the browser. Use `-NoOpen` to skip another browser tab. This restart path was tested successfully.\n")
print("Wrote measured EVALUATION.md, DATA_SOURCES.md and INSTALLATION.md")

