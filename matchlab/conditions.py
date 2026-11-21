"""Match-time weather from Open-Meteo, turned into plain notes. Pure local logic; no network access.

The forecast models do not use weather. These notes are context for the reader and the AI check only.
"""
import re
from datetime import datetime, timedelta, timezone

SOURCE = "Open-Meteo"
SOURCE_URL = "https://open-meteo.com/"
HOURLY = ("temperature_2m", "relative_humidity_2m", "dew_point_2m", "precipitation_probability",
          "precipitation", "wind_speed_10m", "cloud_cover")
FIELDS = {"temperature_2m": "temp", "relative_humidity_2m": "humidity", "dew_point_2m": "dew_point",
          "precipitation_probability": "rain_chance", "precipitation": "rain_mm", "wind_speed_10m": "wind",
          "cloud_cover": "cloud"}
WINDOW = (-1, 4)        # hours around the start that the notes look at


def place_candidates(venue):
    """Names worth geocoding for a published venue, most specific town first.

    "Inalpi Arena, Turin, Italy" -> ["Turin", "Italy", "Inalpi Arena"]; "Entebbe Cricket Oval, Entebbe" -> ["Entebbe", ...].
    """
    parts = [p.strip() for p in str(venue or "").split(",") if p.strip()]
    if len(parts) >= 3:
        ordered = parts[1:-1] + parts[:1] + parts[-1:]
    elif len(parts) == 2:
        ordered = [parts[1], parts[0]]
    else:
        ordered = parts
    # "Abbottabad Cricket Stadium" -> also try "Abbottabad"
    ground = re.compile(r"\b(international|cricket|tennis|sports?|complex|stadium|ground|oval|park|club|arena|centre|center|court|academy)\b.*$", re.I)
    ordered += [ground.sub("", name).strip() for name in ordered]
    seen, out = set(), []
    for name in ordered:
        if name.lower() not in seen and len(name) >= 2:
            seen.add(name.lower())
            out.append(name)
    return out[:5]


def country_hint(venue):
    parts = [p.strip() for p in str(venue or "").split(",") if p.strip()]
    return parts[-1] if len(parts) >= 3 else ""


def parse_start(value):
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def hours(raw, start):
    """Hourly rows from an Open-Meteo `hourly` block (UTC), limited to the window around the start."""
    block = (raw or {}).get("hourly") or {}
    times = block.get("time") or []
    first, last = start + timedelta(hours=WINDOW[0]), start + timedelta(hours=WINDOW[1])
    rows = []
    for index, stamp in enumerate(times):
        moment = datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
        if not first - timedelta(minutes=59) <= moment <= last:
            continue
        row = {"time": moment.isoformat().replace("+00:00", "Z")}
        for name, key in FIELDS.items():
            values = block.get(name) or []
            value = values[index] if index < len(values) else None
            row[key] = value if isinstance(value, (int, float)) else None
        rows.append(row)
    return rows


def _values(rows, key):
    return [row[key] for row in rows if isinstance(row.get(key), (int, float))]


def notes(rows, sport):
    """Plain-language notes. Only what the numbers show; nothing about how a match will go."""
    out = []
    rain = _values(rows, "rain_chance")
    if rain and max(rain) >= 50:
        out.append(f"Rain is likely around the start (up to {max(rain):.0f}% chance per hour)."
                   + (" A wet session or race is possible." if sport == "f1" else
                      " Play may be interrupted unless the venue is indoors." if sport == "tennis" else
                      " Overs could be lost."))
    elif rain and max(rain) >= 25:
        out.append(f"Some chance of rain around the start (up to {max(rain):.0f}% per hour).")
    spreads = [row["temp"] - row["dew_point"] for row in rows
               if isinstance(row.get("temp"), (int, float)) and isinstance(row.get("dew_point"), (int, float))]
    if sport == "cricket" and spreads and min(spreads) <= 3:
        out.append("The air is close to its dew point, so dew on the outfield is likely later in the match.")
    humid = _values(rows, "humidity")
    if sport == "cricket" and humid and max(humid) >= 80 and not out:
        out.append(f"Humid air (up to {max(humid):.0f}%), which bowlers often say helps swing.")
    wind = _values(rows, "wind")
    if wind and max(wind) >= 30:
        out.append(f"Strong wind, up to {max(wind):.0f} km/h.")
    temp = _values(rows, "temp")
    if temp and max(temp) >= 35:
        out.append(f"Hot: up to {max(temp):.0f}°C.")
    elif temp and min(temp) <= 8:
        out.append(f"Cold: down to {min(temp):.0f}°C." + (" Tyres take longer to warm up." if sport == "f1" else ""))
    if not out and rows:
        out.append("No rain, wind or heat of note is forecast around the start.")
    return out


def at_start(rows, start):
    if not rows:
        return None
    return min(rows, key=lambda row: abs(parse_start(row["time"]) - start))


def summarize(raw, place, start, sport):
    rows = hours(raw, start)
    if not rows:
        return {"ok": False, "error": "Open-Meteo has no forecast for this start time yet."}
    return {"ok": True, "source": SOURCE, "source_url": SOURCE_URL, "place": place, "start": start.isoformat().replace("+00:00", "Z"),
            "at_start": at_start(rows, start), "hours": rows, "notes": notes(rows, sport),
            "model_uses": False, "disclaimer": "Weather is shown for context. The forecast model does not use it."}
