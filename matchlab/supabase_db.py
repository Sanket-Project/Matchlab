"""Supabase REST API storage adapter for MatchLab.

Provides cloud persistence for track records, predictions, settings, and caches
so MatchLab works seamlessly on serverless platforms (e.g. Vercel) across requests.
"""
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://pvwtuxzromyhyhqcharn.supabase.co").rstrip("/")
SUPABASE_KEY = os.environ.get(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB2d3R1eHpyb215aHlocWNoYXJuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTUwODQzMDYsImV4cCI6MjExMDY2MDMwNn0.ioEcasUpvCIpjeKDFiYky2y3rFKXhOb6omBcc9O_AoA"
)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def _request(endpoint, method="GET", body=None, extra_headers=None):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    headers = {**HEADERS, **(extra_headers or {})}
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            content = response.read().decode("utf-8")
            return json.loads(content) if content else None
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


def get_state(key, default=None):
    """Retrieve arbitrary JSON state by key from matchlab_state table."""
    res = _request(f"matchlab_state?key=eq.{urllib.parse.quote(key)}&select=value")
    if res and isinstance(res, list) and len(res) > 0:
        return res[0].get("value", default)
    return default


def set_state(key, value):
    """Upsert arbitrary JSON state by key into matchlab_state table."""
    body = {
        "key": key,
        "value": value,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    return _request("matchlab_state", method="POST", body=body, extra_headers={"Prefer": "resolution=merge-duplicates"})


def get_all_predictions():
    """Retrieve all predictions from Supabase as a dictionary keyed by match id."""
    res = _request("predictions?select=id,sport,data,created_at,updated_at&order=updated_at.desc&limit=200")
    if not res or not isinstance(res, list):
        return {}
    out = {}
    for row in res:
        mid = row.get("id")
        if mid and isinstance(row.get("data"), dict):
            out[mid] = row["data"]
    return out


def get_prediction(match_id):
    """Retrieve a single prediction by match id."""
    res = _request(f"predictions?id=eq.{urllib.parse.quote(str(match_id))}&select=data")
    if res and isinstance(res, list) and len(res) > 0:
        return res[0].get("data")
    return None


def save_prediction(match_id, sport, data):
    """Upsert a prediction record."""
    body = {
        "id": str(match_id),
        "sport": sport,
        "data": data,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    return _request("predictions", method="POST", body=body, extra_headers={"Prefer": "resolution=merge-duplicates"})
