#!/usr/bin/env python3
"""Contract test for the helper's `status` path.

Spawns a fake Proxima IPC server on a test port, points the helper at it with
PROXIMA_TEST_PORT, and asserts the emitted JSON. Stdlib only; run directly:

    python3 tests/test_status.py
"""
import json
import os
import socket
import subprocess
import sys
import threading

PORT = 19299
PROVIDERS = ["claude", "chatgpt", "gemini", "perplexity"]
STATE = {"claude": True, "chatgpt": True, "gemini": False, "perplexity": True}
HELPER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "helpers",
    "proxima-helper.py",
)


def serve():
    """Answer 4 isLoggedIn probes plus the helper's liveness connect."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", PORT))
    srv.listen(8)
    for _ in range(5):
        conn, _ = srv.accept()
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
        try:
            req = json.loads(buf.decode())
        except Exception:
            req = {}
        prov = req.get("provider", "")
        reply = {
            "requestId": req.get("requestId", 1),
            "success": True,
            "provider": prov,
            "loggedIn": STATE.get(prov, False),
        }
        try:
            conn.sendall((json.dumps(reply) + "\n").encode())
        except Exception:
            pass
        conn.close()
    srv.close()


def run():
    threading.Thread(target=serve, daemon=True).start()
    env = dict(os.environ, PROXIMA_TEST_PORT=str(PORT))
    out = subprocess.run(
        [sys.executable, HELPER, "status"],
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
    )
    if out.returncode != 0:
        print("helper exited", out.returncode, out.stderr, file=sys.stderr)
        return 1
    data = json.loads(out.stdout.strip().splitlines()[-1])
    assert data["alive"] is True, data
    assert data["count"] == 3, data
    assert data["allLoggedIn"] is False, data
    assert data["providers"]["gemini"] is False, data
    assert data["providers"]["claude"] is True, data
    print("test_status: CONTRACT OK")
    return 0


if __name__ == "__main__":
    sys.exit(run())
