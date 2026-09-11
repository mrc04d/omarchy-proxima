#!/usr/bin/env python3
"""Contract test for the helper's `show` running path.

Spawns a fake hub that answers one showWindow call, runs the helper with
PROXIMA_DRY_RUN=1 (so no real hyprctl is invoked), and asserts the request.
Stdlib only; run directly:

    python3 tests/test_show.py
"""
import json
import os
import socket
import subprocess
import sys
import threading

PORT = 19298
seen = []
HELPER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "helpers",
    "proxima-helper.py",
)


def serve():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", PORT))
    srv.listen(4)
    conn, _ = srv.accept()
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = conn.recv(4096)
        if not chunk:
            break
        buf += chunk
    req = json.loads(buf.decode())
    seen.append(req.get("action"))
    conn.sendall(
        (json.dumps({"requestId": req.get("requestId", 1), "success": True, "visible": True}) + "\n").encode()
    )
    conn.close()
    srv.close()


def run():
    threading.Thread(target=serve, daemon=True).start()
    env = dict(os.environ, PROXIMA_TEST_PORT=str(PORT), PROXIMA_DRY_RUN="1")
    out = subprocess.run(
        [sys.executable, HELPER, "show"],
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
    )
    if out.returncode != 0:
        print("helper exited", out.returncode, out.stderr, file=sys.stderr)
        return 1
    data = json.loads(out.stdout.strip().splitlines()[-1])
    assert data["ok"] is True and data["launched"] is False, data
    assert seen == ["showWindow"], seen
    print("test_show: CONTRACT OK")
    return 0


if __name__ == "__main__":
    sys.exit(run())
