"""Local API credentials (OpenRouter, AcesAPI). Windows saves are protected by user DPAPI.

A key can also sit in a `.env` file in the project folder (git-ignored), one `NAME=value` per line:
    ACESAPI_KEY=...
    OPENROUTER_API_KEY=sk-or-v1-...
Order of use: key saved in Settings, then the process environment, then `.env`.
"""
import ctypes
import os
import re
import tempfile
from ctypes import wintypes
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def get_api_key(name, default=""):
    """Fetch an API key from process environment, .env file, or fallback to default."""
    val = os.environ.get(name, "").strip()
    if val:
        return val
    val = env_file_value(name)
    return val if val else default


def env_file_value(name, path=None):
    """Value of `name` in the project's .env file, or "" (quotes and comments allowed; nothing is exported)."""
    try:
        lines = (path or ENV_FILE).read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return ""
    for line in lines:
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        if sep and key.strip() == name:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            else:
                value = value.split(" #", 1)[0].strip()
            return value
    return ""


class _Blob(ctypes.Structure):
    _fields_ = [("length", wintypes.DWORD), ("data", ctypes.c_void_p)]


def _dpapi(data, encrypt):
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    call = crypt.CryptProtectData if encrypt else crypt.CryptUnprotectData
    call.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                     ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    call.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = ctypes.create_string_buffer(data)
    source, result = _Blob(len(data), ctypes.addressof(buffer)), _Blob()
    if not call(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise OSError("Windows could not access the saved key. Save the key again.")
    try:
        return ctypes.string_at(result.data, result.length)
    finally:
        kernel.LocalFree(result.data)


class OpenRouterKey:
    label, env, pattern, hint = "OpenRouter", "OPENROUTER_API_KEY", r"sk-or-v1-[A-Za-z0-9_-]{20,200}", "beginning with sk-or-v1-"

    def __init__(self, path, env_path=None):
        self.path = path
        self.env_path = env_path
        self.session_key = None

    def status(self):
        if os.name == "nt" and self.path.is_file():
            return "saved"
        if self.session_key:
            return "session"
        if os.environ.get(self.env, "").strip():
            return "environment"
        return "file" if env_file_value(self.env, self.env_path) else "missing"

    def get(self):
        if self.status() == "saved":
            try:
                return _dpapi(self.path.read_bytes(), False).decode("ascii")
            except (OSError, UnicodeError):
                raise OSError(f"The saved {self.label} key could not be opened. Save it again in Settings.") from None
        return self.session_key or os.environ.get(self.env, "").strip() or env_file_value(self.env, self.env_path)

    def save(self, key):
        if not isinstance(key, str) or not re.fullmatch(self.pattern, key.strip()):
            raise ValueError(f"Paste {self.label} API key {self.hint}.".replace("Paste O", "Paste an O").replace("Paste A", "Paste an A"))
        key = key.strip()
        if os.name != "nt":
            self.session_key = key
            return
        protected = _dpapi(key.encode("ascii"), True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as handle:
            temporary = self.path.with_name(os.path.basename(handle.name))
        try:
            temporary.write_bytes(protected)
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def clear(self):
        self.session_key = None
        if os.name == "nt":
            self.path.unlink(missing_ok=True)


class AcesApiKey(OpenRouterKey):
    """AcesAPI tennis key (acesapi.com). Free keys carry 500 credits a month."""
    label, env, pattern, hint = "AcesAPI", "ACESAPI_KEY", r"[A-Za-z0-9_.-]{16,200}", "(letters, digits, dashes, at least 16 characters)"


class GeminiKey(OpenRouterKey):
    """Google Gemini API key (aistudio.google.com). Used for match commentary and AI checks."""
    label, env, pattern, hint = "Gemini", "GEMINI_API_KEY", r"[A-Za-z0-9_.-]{20,200}", "(API key from Google AI Studio)"


class CricketDataKey(OpenRouterKey):
    """CricketData.org / CricAPI key for live fixtures and scorecards."""
    label, env, pattern, hint = "CricketData", "CRICKETDATA_API_KEY", r"[A-Za-z0-9_.-]{16,200}", "(API key from cricketdata.org)"


class FootballDataKey(OpenRouterKey):
    """Football-Data.org key for live European football fixtures, scores and standings."""
    label, env, pattern, hint = "FootballData", "FOOTBALL_DATA_API_KEY", r"[A-Za-z0-9_.-]{16,200}", "(API key from football-data.org)"


class TheOddsApiKey(OpenRouterKey):
    """The Odds API key for live betting odds and market implied probabilities."""
    label, env, pattern, hint = "TheOddsAPI", "THE_ODDS_API_KEY", r"[A-Za-z0-9_.-]{16,200}", "(API key from the-odds-api.com)"


class LiveTennisKey(OpenRouterKey):
    """Live Tennis API key (livetennisapi.com) for live match scores and tournament schedules."""
    label, env, pattern, hint = "LiveTennisAPI", "LIVE_TENNIS_API_KEY", r"[A-Za-z0-9_.-]{16,200}", "(API key from livetennisapi.com)"


class MatchstatKey(OpenRouterKey):
    """Matchstat / RapidAPI tennis key for deep H2H, point-by-point stats and surface records."""
    label, env, pattern, hint = "Matchstat", "MATCHSTAT_API_KEY", r"[A-Za-z0-9_.-]{16,200}", "(API key from matchstat.com or RapidAPI)"


class ApiTennisKey(OpenRouterKey):
    """API-Tennis key (api-tennis.com) for tennis fixtures and live scores."""
    label, env, pattern, hint = "ApiTennis", "API_TENNIS_KEY", r"[A-Za-z0-9_.-]{16,200}", "(API key from api-tennis.com)"


class OpenF1Key(OpenRouterKey):
    """OpenF1 key/token for live session telemetry and lap timing."""
    label, env, pattern, hint = "OpenF1", "OPENF1_API_KEY", r"[A-Za-z0-9_.-]{16,200}", "(API key from openf1.org)"


KEY_CLASSES = {
    "openrouter": OpenRouterKey,
    "acesapi": AcesApiKey,
    "gemini": GeminiKey,
    "cricketdata": CricketDataKey,
    "football_data": FootballDataKey,
    "the_odds_api": TheOddsApiKey,
    "live_tennis": LiveTennisKey,
    "matchstat": MatchstatKey,
    "api_tennis": ApiTennisKey,
    "openf1": OpenF1Key,
}
