"""Turn the owner's player portraits into small WebP variants for the dashboard.

Source: the PNG portraits in web/images/Formula 1 Drivers/ and web/images/Tennis Players/ (kept out of git and
of the deployment because each is about 2 MB). Output: web/images/players/<slug>-face-<px>.webp (square head and
shoulders, for avatars) and <slug>-<px>.webp (4:5 portrait, for cards and heroes), plus manifest.json mapping a
normalised player name to its slug, sport and the pixel sizes written.

The F1 portraits carry a printed caption strip at the bottom ("#1 – Lando Norris (McLaren)"). Its number and team
are a snapshot that goes stale, so the strip is cropped off; the page states the current position and team itself.

Run: python tools/process_player_photos.py   (needs Pillow with WebP support)
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {"f1": ROOT / "web/images/Formula 1 Drivers", "tennis": ROOT / "web/images/Tennis Players"}
OUT = ROOT / "web/images/players"
FACE_SIZES = (96, 192)          # avatars are drawn at 48 px or less, so 1x and 2x
CARD_SIZES = (320, 640)         # portraits are drawn up to 320 px wide
F1_CAPTION_TOP = 1196           # first row of the printed caption strip on the 1199 x 1312 F1 portraits
# File names describe the picture ("Charles Leclerc_ Sunset Pit Lane Portrait"); this one does not name the driver.
NAMED = {"Sunset Pit Lane Champion": "Lewis Hamilton"}
SUFFIX = re.compile(r"(?:’s|'s)?[_\s]*(?:Sunset|Golden Hour|in the Pit Lane|at Sunset|Pit Lane|Celebrates|Racing Bulls).*$", re.I)
PREFIX = re.compile(r"^(?:Sunset Tennis Champion|Sunset Triumph_)\s*", re.I)


def key(name):
    """Normalised lookup key: accents removed, lower case, single spaces."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", " ", plain.lower())).strip()


def person(stem):
    if stem in NAMED:
        return NAMED[stem]
    name = PREFIX.sub("", stem)
    name = re.sub(r"\s+at\s*$", "", SUFFIX.sub("", name)).strip(" _")
    return name


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for sport, folder in SOURCES.items():
        for path in sorted(folder.glob("*.png")):
            name = person(path.stem)
            slug = key(name).replace(" ", "-")
            image = Image.open(path).convert("RGB")
            if sport == "f1":
                image = image.crop((0, 0, image.width, min(image.height, F1_CAPTION_TOP)))
            w, h = image.size
            # 4:5 portrait, cut from the top so the face is always in frame. The artwork's own name plate, low in the
            # frame, stays: it is part of the illustration and names the player.
            card_h = min(h, round(w * 5 / 4))
            card = image.crop((0, 0, w, card_h))
            side = round(w * 0.42)                       # head and shoulders, centred
            left = (w - side) // 2
            face = image.crop((left, round(h * 0.01), left + side, round(h * 0.01) + side))
            for size in CARD_SIZES:
                card.resize((size, round(size * card.height / card.width)), Image.LANCZOS).save(OUT / f"{slug}-{size}.webp", "WEBP", quality=78, method=6)
            for size in FACE_SIZES:
                face.resize((size, size), Image.LANCZOS).save(OUT / f"{slug}-face-{size}.webp", "WEBP", quality=80, method=6)
            manifest[key(name)] = {"name": name, "slug": slug, "sport": sport, "card": list(CARD_SIZES), "face": list(FACE_SIZES),
                                   "ratio": round(card.height / card.width, 4)}
            print(f"{sport:6} {name:22} -> {slug}")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(manifest)} players written to {OUT.relative_to(ROOT)}")
    return 0 if manifest else 1


if __name__ == "__main__":
    sys.exit(main())
