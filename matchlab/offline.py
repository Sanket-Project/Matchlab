"""Best-effort in-process network guard; no model downloads or remote loaders."""
import ipaddress
import os
import socket
from pathlib import Path


def enable_offline():
    if os.environ.get("VERCEL") or os.environ.get("MATCHLAB_ALLOW_NETWORK"):
        return
    cache = Path(__file__).resolve().parents[1] / ".cache"
    os.environ["HF_HOME"] = str(cache / "huggingface")
    os.environ["TORCH_HOME"] = str(cache / "torch")
    os.environ["XDG_CACHE_HOME"] = str(cache)
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["WANDB_DISABLED"] = "true"
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY", "DO_NOT_TRACK"):
        os.environ[key] = "1"
    os.environ["WANDB_MODE"] = "disabled"
    if getattr(socket, "_matchlab_offline", False):
        return
    original_connect, original_connect_ex = socket.socket.connect, socket.socket.connect_ex
    original_resolve = socket.getaddrinfo
    original_sendto = socket.socket.sendto

    def local(host):
        if host in (None, "", "localhost"):
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def check(address):
        if isinstance(address, tuple) and not local(address[0]):
            raise OSError("Offline mode: outbound connections are disabled")

    def connect(self, address):
        check(address)
        return original_connect(self, address)

    def connect_ex(self, address):
        check(address)
        return original_connect_ex(self, address)

    def resolve(host, *args, **kwargs):
        if not local(host):
            raise OSError("Offline mode: external DNS is disabled")
        return original_resolve(host, *args, **kwargs)

    def sendto(self, data, *args):
        check(args[-1])
        return original_sendto(self, data, *args)

    def wrap_dns(method):
        def guarded(host, *args, **kwargs):
            if not local(host):
                raise OSError("Offline mode: external DNS is disabled")
            return method(host, *args, **kwargs)
        return guarded

    socket.socket.connect, socket.socket.connect_ex = connect, connect_ex
    socket.getaddrinfo = resolve
    socket.socket.sendto = sendto
    socket.gethostbyname = wrap_dns(socket.gethostbyname)
    socket.gethostbyname_ex = wrap_dns(socket.gethostbyname_ex)
    socket.gethostbyaddr = wrap_dns(socket.gethostbyaddr)
    socket._matchlab_offline = True
