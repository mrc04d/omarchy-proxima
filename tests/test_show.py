#!/usr/bin/env python3
"""Contract tests for the helper's `show` running path.

Spawns a fake hub that answers one showWindow call, runs the helper with
PROXIMA_DRY_RUN=1 (so no real hyprctl is invoked), and asserts the request.
Stdlib only:

    python3 -m unittest discover -s tests -v
    python3 tests/test_show.py
"""
import json
import os
import socket
import subprocess
import sys
import threading
import unittest

PORT = 19298
HELPER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "helpers",
    "proxima-helper.py",
)


class ShowContract(unittest.TestCase):
    def test_show_window_running_path(self):
        seen = []

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
                (
                    json.dumps(
                        {"requestId": req.get("requestId", 1), "success": True, "visible": True}
                    )
                    + "\n"
                ).encode()
            )
            conn.close()
            srv.close()

        threading.Thread(target=serve, daemon=True).start()
        env = dict(os.environ, PROXIMA_TEST_PORT=str(PORT), PROXIMA_DRY_RUN="1")
        out = subprocess.run(
            [sys.executable, HELPER, "show"],
            capture_output=True,
            text=True,
            timeout=20,
            env=env,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertTrue(data["ok"], data)
        self.assertFalse(data["launched"], data)
        self.assertEqual(seen, ["showWindow"], seen)


if __name__ == "__main__":
    unittest.main(verbosity=2)
