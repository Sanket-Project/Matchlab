"""Copy what the public mirror may show into data/public/, then commit and push to update the hosted site.

The hosted MatchLab (api/index.py on Vercel) cannot see this computer. It shows a snapshot: the saved schedule, the
prediction log (forecasts saved before each start, their grades and live timelines) and the last World briefing.
Nothing else under data/ is published: no keys, no API budget ledger, no caches.

Run: python tools/publish_snapshot.py
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "public"
# source -> published name. Each file is parsed and re-written, so a half-written source fails here, not on the site.
FILES = {"data/today_matches.json": "today_matches.json", "data/local/predictions.json": "predictions.json",
         "data/local/cache/world_brief.json": "world_brief.json"}
SECRET_HINTS = ("sk-or-v1-", "apikey", "api_key", "authorization")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    written = []
    for source, name in FILES.items():
        path = ROOT / source
        if not path.exists():
            print(f"skip   {source} (not found)")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        if any(hint in text.lower() for hint in SECRET_HINTS):
            sys.exit(f"Refusing to publish {source}: it looks like it contains a key.")
        (OUT / name).write_text(text, encoding="utf-8")
        written.append(name)
        print(f"wrote  data/public/{name} ({len(text) // 1024} KB)")
    meta = {"published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": written}
    (OUT / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print("Next: git add data/public && git commit -m \"data: publish snapshot\" && git push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
