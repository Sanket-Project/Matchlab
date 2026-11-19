"""Write a reviewable local configuration from the verified model manifest."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from matchlab.engine import default_config

manifest = json.loads((ROOT / "models/manifest.json").read_text())
files = {Path(f["path"]).name: f for f in manifest["files"]}
config = dict(pretrained=dict(chronos_path="models/chronos-bolt-small", manifest="models/manifest.json", max_context_rows=192, n_estimators=2), sports={})
for sport in ("football", "cricket", "tennis", "badminton", "baseball", "rugby"):
    models = {}
    for task in ("winner", "team_score", "player_score", "player_threat"):
        kind = "classifier" if task == "winner" else "regressor"
        f = files[f"tabicl-{kind}-v2-20260212.ckpt"]
        models[task] = dict(format=f"tabicl_{kind}", path=f["path"], sha256=f["sha256"])
    scoring = dict(strict_scores=True)
    if sport == "cricket":
        scoring.update(draw=False, format="Standard IPL T20; completed games; no super-overs/DLS")
    if sport in ("tennis", "badminton"):
        scoring.update(max_score=2, format="Completed best-of-three singles")
    config["sports"][sport] = dict(data_dir=f"data/real/{sport}", demo=False, reference_mode=False, models=models, scoring=scoring)
path = ROOT / "config.local.json"
if path.exists():
    previous = path.read_text(encoding="utf-8")
    backup = ROOT / "artifacts/config.before-pretrained.json"
    if not backup.exists():
        backup.write_text(previous, encoding="utf-8")
(ROOT / "config.pretrained.example.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
if (ROOT / "data/real/f1/provenance.json").is_file():
    config["sports"]["f1"] = {"data_dir": "data/real/f1"}
path.write_text(json.dumps(config, indent=2), encoding="utf-8")
(ROOT / "config.demo.json").write_text(json.dumps(default_config(), indent=2), encoding="utf-8")
print(f"Configured {len(config['sports'])} real sports. The demo configuration is separate.")
