"""Exercise actual downloaded weights with outbound network unavailable."""
import json
import argparse
import socket
import sys
import time
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from matchlab.offline import enable_offline
enable_offline()
from matchlab.engine import Engine
from matchlab.pretrained import file_hash


def recommended_query(ds, sport):
    counts = Counter(t for m in ds.matches for t in (m["team"], m["opponent"]))
    team, opponent = [t for t, _ in counts.most_common(2)]
    if sport == "cricket":
        team, opponent = "Chennai Super Kings", "Mumbai Indians"
    if sport == "badminton":
        team, opponent = "Viktor AXELSEN", "CHOU Tien Chen"
    q = dict(sport=sport, team=team, opponent=opponent, cutoff="2026-11-10", window=5, venue="neutral")
    for field, side in (("player", team), ("opponent_player", opponent)):
        players = Counter(p["player"] for p in ds.players if p["team"] == side)
        if players:
            q[field] = players.most_common(1)[0][0]
    return q


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sports", nargs="*")
    args = parser.parse_args()
    engine = Engine(json.loads((ROOT / "config.pretrained.example.json").read_text()), ROOT)
    manifest = json.loads((ROOT / "models/manifest.json").read_text())
    before = {f["path"]: file_hash(ROOT / f["path"]) for f in manifest["files"]}
    report_path = ROOT / "artifacts/real-inference-report.json"
    report = json.loads(report_path.read_text()) if args.sports and report_path.exists() else dict(offline=True, network_blocks=[], sports={})
    for address in (("203.0.113.1", 443), ("huggingface.co", 443)):
        try:
            with socket.socket() as sock:
                sock.connect(address)
            raise AssertionError("Remote socket unexpectedly allowed")
        except OSError as exc:
            report["network_blocks"].append(str(exc))
    for sport, ds in engine.datasets.items():
        if args.sports and sport not in args.sports:
            continue
        start = time.monotonic()
        query = recommended_query(ds, sport)
        print("Inferring " + sport + " " + json.dumps(query), flush=True)
        a = engine.analyze(query)
        (ROOT / f"artifacts/real-{sport}.json").write_text(json.dumps(a, indent=2), encoding="utf-8")
        summary = dict(seconds=round(time.monotonic() - start, 3), query=query,
                       tasks={k: {name: p.get(name) for name in ("value", "error", "model", "sha256")} for k, p in (("winner", a["winner"]), ("team_score", a["scores"][0]), ("opponent_score", a["scores"][1]), ("player_score", a["player_score"]), ("player_threat", a["threat"]))},
                       chronos=a["scoring_form"])
        report["sports"][sport] = summary
        (ROOT / "artifacts/real-inference-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(sport + ": " + json.dumps({k: v.get("value", v.get("error")) for k, v in summary["tasks"].items()}), flush=True)
    after = {f["path"]: file_hash(ROOT / f["path"]) for f in manifest["files"]}
    assert before == after
    assert all(before[f["path"]] == f["sha256"] for f in manifest["files"])
    report["original_files_unchanged"] = True
    (ROOT / "artifacts/real-inference-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Original weights unchanged; real-model offline inference report saved.", flush=True)
