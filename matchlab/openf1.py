"""Shape OpenF1 session data for the race weekend panel. Pure local logic; no network access.

OpenF1's free tier serves finished sessions only (live timing needs a paid account), so the panel lists
practice and qualifying once they are over, with the track weather each session ended in.
Data: https://openf1.org (CC BY-NC-SA 4.0, unofficial, not associated with Formula 1).
"""
from datetime import datetime, timedelta

SOURCE = "OpenF1"
SOURCE_URL = "https://openf1.org/"
# OpenF1 marks the window from 30 minutes before to 30 minutes after a session as live (paid access only).
LIVE_MARGIN = timedelta(minutes=30)


def stamp(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def weekend(sessions, race_start):
    """Sessions of the meeting whose race starts at `race_start` (within two hours), in running order."""
    races = [s for s in sessions if s.get("session_type") == "Race" and s.get("session_name") == "Race"
             and abs(stamp(s["date_start"]) - race_start) <= timedelta(hours=2)]
    if not races:
        return []
    meeting = races[0]["meeting_key"]
    return sorted((s for s in sessions if s.get("meeting_key") == meeting and not s.get("is_cancelled")),
                  key=lambda s: s["date_start"])


def finished(session, now):
    return stamp(session["date_end"]) + LIVE_MARGIN <= now


def best_time(duration):
    """A practice result carries one lap time; a qualifying result carries Q1, Q2, Q3 (later parts may be empty)."""
    if isinstance(duration, list):
        times = [t for t in duration if isinstance(t, (int, float))]
        return times[-1] if times else None
    return duration if isinstance(duration, (int, float)) else None


def lap_text(seconds):
    if not isinstance(seconds, (int, float)):
        return ""
    minutes, rest = divmod(seconds, 60)
    return f"{int(minutes)}:{rest:06.3f}"


def driver_names(drivers):
    names = {}
    for row in drivers or []:
        first, last = (row.get("first_name") or "").strip(), (row.get("last_name") or "").strip()
        names[row.get("driver_number")] = {"name": f"{first} {last}".strip() or row.get("full_name") or str(row.get("driver_number")),
                                           "team": row.get("team_name") or "", "code": row.get("name_acronym") or ""}
    return names


def classification(results, names, limit=10):
    rows = []
    for row in sorted((r for r in results or [] if isinstance(r.get("position"), int)), key=lambda r: r["position"])[:limit]:
        who = names.get(row.get("driver_number"), {"name": f"Car {row.get('driver_number')}", "team": "", "code": ""})
        rows.append({"position": row["position"], **who, "time": lap_text(best_time(row.get("duration"))),
                     "laps": row.get("number_of_laps"), "out": bool(row.get("dnf") or row.get("dns") or row.get("dsq"))})
    return rows


def last_weather(rows):
    rows = [r for r in rows or [] if r.get("date")]
    if not rows:
        return None
    row = max(rows, key=lambda r: r["date"])
    return {"air": row.get("air_temperature"), "track": row.get("track_temperature"), "humidity": row.get("humidity"),
            "rain": bool(row.get("rainfall")), "wind": row.get("wind_speed")}


def summary(sessions, details, drivers, now):
    """`details` maps session_key -> {"results": [...], "weather": [...]} for finished sessions."""
    names = driver_names(drivers)
    out = []
    for session in sessions:
        done = finished(session, now)
        item = {"name": session.get("session_name"), "start": session["date_start"], "end": session["date_end"],
                "state": "done" if done else "live" if stamp(session["date_start"]) - LIVE_MARGIN <= now else "pre"}
        extra = details.get(session["session_key"]) if done else None
        if extra:
            item["top"] = classification(extra.get("results"), names)
            item["weather"] = last_weather(extra.get("weather"))
        out.append(item)
    location = sessions[0].get("location") if sessions else ""
    return {"ok": bool(sessions), "source": SOURCE, "source_url": SOURCE_URL, "location": location, "sessions": out,
            "note": "Finished sessions only. OpenF1 serves live timing to paid accounts, so a running session shows once it ends."}
