"""Daily request budgets for metered services (CricketData.org, OpenRouter).

One small ledger file, shared by the server and the short-lived network workers.
A call is allowed only if it keeps a reserve for the half hour before a match.
Days are counted in UTC, which is when both providers reset.
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULTS = {
    "cricketdata": {"limit": 100, "reserve": 5, "label": "CricketData.org"},
    "openrouter": {"limit": 50, "reserve": 2, "label": "OpenRouter free models"},
}
LEDGER = "data/local/api_budget.json"


def _today():
    return datetime.now(timezone.utc).date().isoformat()


def _read(root):
    # The ledger is a local file on purpose. A copy on a shared database that anyone holding its public key can
    # rewrite would let them reset the count and spend the day's quota.
    try:
        data = json.loads((Path(root) / LEDGER).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(root, data):
    try:
        path = Path(root) / LEDGER
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temporary.replace(path)
    except Exception:
        pass


def _entry(data, service):
    entry = data.get(service) if isinstance(data.get(service), dict) else {}
    limit = entry.get("limit") if isinstance(entry.get("limit"), int) and entry["limit"] > 0 else DEFAULTS[service]["limit"]
    if entry.get("day") != _today():
        entry = {"day": _today(), "used": 0, "calls": []}
    entry["limit"] = limit
    entry.setdefault("used", 0)
    entry.setdefault("calls", [])
    data[service] = entry
    return entry


def status(root):
    data = _read(root)
    report = {}
    for service, defaults in DEFAULTS.items():
        entry = _entry(data, service)
        report[service] = {"label": defaults["label"], "day": entry["day"], "used": entry["used"], "limit": entry["limit"],
                           "remaining": max(0, entry["limit"] - entry["used"]), "reserve": defaults["reserve"],
                           "last_call": entry["calls"][-1] if entry["calls"] else None}
    return report


def remaining(root, service):
    return status(root)[service]["remaining"]


def spend(root, service, purpose, priority=False):
    """Record one request. Returns False (and records nothing) when the budget is spent.

    Ordinary calls stop at the reserve; priority calls (the pre-match window) may use it.
    """
    data = _read(root)
    entry = _entry(data, service)
    floor = 0 if priority else DEFAULTS[service]["reserve"]
    if entry["limit"] - entry["used"] <= floor:
        return False
    entry["used"] += 1
    entry["calls"] = (entry["calls"] + [{"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "purpose": purpose}])[-40:]
    _write(root, data)
    return True


def sync(root, service, used, limit=None):
    """Adopt the provider's own count when it reports one (it also sees other apps using the key)."""
    if not isinstance(used, int) or used < 0:
        return
    data = _read(root)
    entry = _entry(data, service)
    entry["used"] = used
    if isinstance(limit, int) and limit > 0:
        entry["limit"] = limit
    _write(root, data)


def refresh_interval(root, service="cricketdata"):
    """Seconds to wait between routine list refreshes: slower as the budget runs down."""
    left = remaining(root, service)
    return 900 if left > 40 else 1800 if left > 15 else 3600


class Cache:
    """Tiny JSON file cache for metered responses."""

    def __init__(self, root, name):
        self.path = Path(root) / "data/local/cache" / f"{name}.json"

    def get(self, max_age):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data["value"] if time.time() - data.get("saved", 0) <= max_age else None

    def put(self, value):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps({"saved": time.time(), "value": value}), encoding="utf-8")
        temporary.replace(self.path)
