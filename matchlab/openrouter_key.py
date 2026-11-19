"""Local OpenRouter credentials. Windows saves are protected by user DPAPI."""
import ctypes
import os
import re
import tempfile
from ctypes import wintypes


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
        raise OSError("Windows could not access the OpenRouter key. Save the key again.")
    try:
        return ctypes.string_at(result.data, result.length)
    finally:
        kernel.LocalFree(result.data)


class OpenRouterKey:
    def __init__(self, path):
        self.path = path
        self.session_key = None

    def status(self):
        if os.name == "nt" and self.path.is_file():
            return "saved"
        if self.session_key:
            return "session"
        return "environment" if os.environ.get("OPENROUTER_API_KEY", "").strip() else "missing"

    def get(self):
        if self.status() == "saved":
            try:
                return _dpapi(self.path.read_bytes(), False).decode("ascii")
            except (OSError, UnicodeError):
                raise OSError("The saved OpenRouter key could not be opened. Save it again in Data & models.") from None
        return self.session_key or os.environ.get("OPENROUTER_API_KEY", "").strip()

    def save(self, key):
        if not isinstance(key, str) or not re.fullmatch(r"sk-or-v1-[A-Za-z0-9_-]{20,200}", key.strip()):
            raise ValueError("Paste an OpenRouter API key beginning with sk-or-v1-.")
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
