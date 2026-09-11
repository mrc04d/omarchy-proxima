#!/usr/bin/env python3
"""Contract tests for the helper's `status` path.

Spawns a fake Proxima IPC server on a test port, points the helper at it with
PROXIMA_TEST_PORT, and asserts the emitted JSON. Stdlib only:

    python3 -m unittest discover -s tests -v
    python3 tests/test_status.py
"""
import json
import os
import socket
import subprocess
import sys
import threading
import unittest

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


class StatusContract(unittest.TestCase):
    def test_three_of_four_logged_in(self):
        threading.Thread(target=serve, daemon=True).start()
        env = dict(os.environ, PROXIMA_TEST_PORT=str(PORT))
        out = subprocess.run(
            [sys.executable, HELPER, "status"],
            capture_output=True,
            text=True,
            timeout=20,
            env=env,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertTrue(data["alive"], data)
        self.assertEqual(data["count"], 3, data)
        self.assertFalse(data["allLoggedIn"], data)
        self.assertFalse(data["providers"]["gemini"], data)
        self.assertTrue(data["providers"]["claude"], data)

    def test_dead_port_reports_not_running(self):
        env = dict(os.environ, PROXIMA_TEST_PORT="19999")
        out = subprocess.run(
            [sys.executable, HELPER, "status"],
            capture_output=True,
            text=True,
            timeout=20,
            env=env,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertFalse(data["alive"], data)
        self.assertEqual(data["count"], 0, data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
