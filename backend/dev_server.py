"""Development launcher with a safe localhost fallback for stale Windows sockets."""

from __future__ import annotations

import json
import socket
import sys
import time
import urllib.request

import uvicorn


PORT = 8000


def _can_bind(host: str) -> bool:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    address = (host, PORT, 0, 0) if family == socket.AF_INET6 else (host, PORT)
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(address)
            return True
        except OSError:
            return False


def _is_current_backend(host: str) -> bool:
    url_host = f"[{host}]" if ":" in host else host
    try:
        with urllib.request.urlopen(f"http://{url_host}:{PORT}/api/system/ai-status", timeout=2) as response:
            payload = json.load(response)
        return payload.get("generation_model") in {"gpt-4.1", "llama-3.3-70b-versatile"}
    except Exception:
        return False


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if _is_current_backend("::1") or _is_current_backend("127.0.0.1"):
        print(f"Backend hiện tại đã chạy đúng tại http://localhost:{PORT}; theo dõi tiến trình đó.", flush=True)
        try:
            while _is_current_backend("::1") or _is_current_backend("127.0.0.1"):
                time.sleep(2)
        except KeyboardInterrupt:
            return
        return

    host = "0.0.0.0"
    if not _can_bind(host):
        if not _can_bind("::1"):
            raise SystemExit(f"Port {PORT} đang bị chiếm và không có địa chỉ fallback khả dụng.")
        host = "::1"
        print(
            f"IPv4 port {PORT} đang bị một socket cũ chiếm; backend dev fallback sang http://localhost:{PORT} qua IPv6.",
            flush=True,
        )
    # On Windows, a reload worker bound to the IPv6 fallback can emit a console
    # control event that also terminates the sibling Vite process in concurrently.
    uvicorn.run("api:app", host=host, port=PORT, reload=host == "0.0.0.0")


if __name__ == "__main__":
    main()
