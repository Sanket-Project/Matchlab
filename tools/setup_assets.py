"""One-time download ONLY. Never imported by the offline application.

GETs publisher weights/docs and licensed public data; sends no local content.
Raw downloads are retained. Run with --models or --data (or both).
"""
import argparse
import concurrent.futures
import hashlib
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("HF_HOME", str(ROOT / ".cache/huggingface"))
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def get(url, path):
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path
    partial = path.with_name(path.name + ".partial")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MatchLab-one-time-setup/1.0"})
            with urllib.request.urlopen(req, timeout=180) as response, partial.open("wb") as out:
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
            partial.replace(path)
            print(f"Downloaded {path.relative_to(ROOT)} ({path.stat().st_size:,} bytes)", flush=True)
            return path
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)


def models():
    manifest = {"files": [], "device": "cpu", "downloaded_on": "2026-11-10"}
    jobs = []
    for repo, folder, names in [
        ("jingang/TabICL", "models/tabicl", ["tabicl-classifier-v2-20260212.ckpt", "tabicl-regressor-v2-20260212.ckpt", "README.md"]),
        ("amazon/chronos-bolt-small", "models/chronos-bolt-small", ["model.safetensors", "config.json", "README.md"]),
    ]:
        metadata_path = get(f"https://huggingface.co/api/models/{repo}?blobs=true", f"{folder}/publisher-metadata.json")
        metadata = json.loads(metadata_path.read_text())
        files = {f["rfilename"]: f for f in metadata["siblings"]}
        for name in names:
            url = f"https://huggingface.co/{repo}/resolve/{metadata['sha']}/{name}?download=true"
            jobs.append((url, f"{folder}/{name}", files[name], repo, metadata["sha"]))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [(pool.submit(get, url, path), info, repo, rev, url) for url, path, info, repo, rev in jobs]
        for future, info, repo, rev, url in futures:
            path = future.result()
            digest = sha(path)
            expected = info.get("lfs", {}).get("sha256")
            if path.stat().st_size != info["size"] or (expected and digest != expected):
                raise RuntimeError(f"Publisher integrity check failed: {path}. Remove and re-download this file.")
            manifest["files"].append(dict(path=path.relative_to(ROOT).as_posix(), bytes=path.stat().st_size,
                                          sha256=digest, publisher_sha256=expected, repo=repo, revision=rev, url=url))
    (ROOT / "models/manifest.json").write_text(json.dumps(manifest, indent=2))
    for url, path in [
        ("https://raw.githubusercontent.com/soda-inria/tabicl/main/README.md", "docs/publishers/tabicl-README.md"),
        ("https://raw.githubusercontent.com/soda-inria/tabicl/main/LICENSE", "docs/publishers/tabicl-LICENSE"),
        ("https://raw.githubusercontent.com/amazon-science/chronos-forecasting/main/README.md", "docs/publishers/chronos-README.md"),
        ("https://raw.githubusercontent.com/amazon-science/chronos-forecasting/main/LICENSE", "docs/publishers/chronos-LICENSE"),
    ]:
        get(url, path)
    print("All original model weights verified against publisher SHA-256.", flush=True)


def data():
    jobs = []
    def add(url, path):
        jobs.append((url, "data/raw/" + path))
    for season in ("2021-22", "2022-23", "2023-24"):
        add(f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/en.1.json", f"football/{season}.json")
    add("https://raw.githubusercontent.com/openfootball/football.json/master/LICENSE.md", "football/LICENSE.md")
    add("https://cricsheet.org/downloads/ipl_json.zip", "cricket/ipl_json.zip")
    add("https://cricsheet.org/licensing/", "cricket/LICENSE.html")
    for year in (2023, 2024):
        add(f"https://raw.githubusercontent.com/Aneeshers/tennis-sackmann-archive/main/atp/atp_matches_{year}.csv", f"tennis/{year}.csv")
    add("https://raw.githubusercontent.com/Aneeshers/tennis-sackmann-archive/main/LICENSE", "tennis/LICENSE")
    add("https://raw.githubusercontent.com/Aneeshers/tennis-sackmann-archive/main/atp/UPSTREAM_README.md", "tennis/README.md")
    add("https://www.retrosheet.org/gamelogs/gl2023.zip", "baseball/gl2023.zip")
    add("https://www.retrosheet.org/gamelogs/glfields.txt", "baseball/glfields.txt")
    add("https://www.retrosheet.org/notice.txt", "baseball/NOTICE.txt")
    add("https://raw.githubusercontent.com/thmcmahon/superrugby/master/data-raw/superrugby_raw.csv", "rugby/results.csv")
    add("https://raw.githubusercontent.com/thmcmahon/superrugby/master/DESCRIPTION", "rugby/LICENSE-DESCRIPTION.txt")
    add("https://raw.githubusercontent.com/thmcmahon/superrugby/master/README.md", "rugby/README.md")
    tree_path = get("https://api.github.com/repos/wywyWang/CoachAI-Projects/git/trees/main?recursive=1", "data/raw/badminton/tree.json")
    tree = json.loads(tree_path.read_text())
    # Pin every annotation to one commit; no videos downloaded.
    for f in tree["tree"]:
        if f["path"].startswith("ShuttleSet/set/") and f["path"].endswith(".csv") and "homography" not in f["path"]:
            from urllib.parse import quote
            add(f"https://raw.githubusercontent.com/wywyWang/CoachAI-Projects/{tree['sha']}/{quote(f['path'])}", "badminton/" + f["path"].removeprefix("ShuttleSet/"))
        prefix = "CoachAI-Challenge-IJCAI2023/ShuttleSet22/"
        if f["path"].startswith(prefix + "set/") and f["path"].endswith(".csv") and "homography" not in f["path"]:
            from urllib.parse import quote
            add(f"https://raw.githubusercontent.com/wywyWang/CoachAI-Projects/{tree['sha']}/{quote(f['path'])}", "badminton22/" + f["path"].removeprefix(prefix))
    add("https://raw.githubusercontent.com/wywyWang/CoachAI-Projects/main/LICENSE", "badminton/LICENSE")
    add("https://raw.githubusercontent.com/wywyWang/CoachAI-Projects/main/ShuttleSet/README.md", "badminton/README.md")
    add("https://raw.githubusercontent.com/wywyWang/CoachAI-Projects/main/CoachAI-Challenge-IJCAI2023/ShuttleSet22/README.md", "badminton22/README.md")
    add("https://raw.githubusercontent.com/wywyWang/CoachAI-Projects/main/LICENSE", "badminton22/LICENSE")
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [(pool.submit(get, url, path), url) for url, path in jobs]
        for future, url in futures:
            try:
                future.result()
            except Exception as exc:
                failures.append(dict(url=url, error=str(exc)))
    files = [dict(path=p.relative_to(ROOT).as_posix(), bytes=p.stat().st_size, sha256=sha(p))
             for p in (ROOT / "data/raw").rglob("*") if p.is_file() and not p.name.endswith(".partial")]
    (ROOT / "data/raw/manifest.json").write_text(json.dumps(dict(files=files, failures=failures), indent=2))
    if failures:
        print(json.dumps(failures, indent=2), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", action="store_true")
    parser.add_argument("--data", action="store_true")
    args = parser.parse_args()
    if args.models:
        models()
    if args.data:
        data()
