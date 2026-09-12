#!/usr/bin/env python3
"""Proxima Agent Hub bar-widget helper: status | show. Stdlib only."""
import json
import os
import socket
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
# Proxima checkout, used only by the launch path. Set by the widget's
# `proximaDir` setting (passed as PROXIMA_DIR); falls back to ~/Work/Proxima.
PROXIMA_DIR = os.path.expanduser(os.environ.get("PROXIMA_DIR") or "~/Work/Proxima")
ELECTRON_BIN = os.path.join(PROXIMA_DIR, "node_modules", ".bin", "electron")
PROVIDERS = ["claude", "chatgpt", "gemini", "perplexity"]
DEFAULT_PORT = 19222
WS = "10"


def load_port():
    override = os.environ.get("PROXIMA_TEST_PORT")
    if override:
        try:
            return int(override)
        except ValueError:
            pass
    try:
        with open(os.path.join(HOME, ".config", "proxima", "ipc-port.json")) as f:
            return int(json.load(f).get("port", DEFAULT_PORT))
    except Exception:
        return DEFAULT_PORT


def load_token():
    try:
        with open(os.path.join(HOME, ".config", "proxima", "ipc-token.json")) as f:
            return json.load(f).get("token")
    except Exception:
        return None


def ipc_request(action, provider=None, timeout=2.0):
    """One IPC round-trip. Returns parsed response dict; raises on failure."""
    port = load_port()
    req = {"requestId": 1, "action": action, "provider": provider, "data": {}}
    token = load_token()
    if token:
        req["token"] = token
    payload = (json.dumps(req) + "\n").encode()
    s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    try:
        s.settimeout(timeout)
        s.sendall(payload)
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            if len(buf) > 1024 * 1024:
                break
        return json.loads(buf.decode().strip().splitlines()[-1])
    finally:
        try:
            s.close()
        except Exception:
            pass


def status_providers(deadline=None, errors=None):
    results = {}
    for p in PROVIDERS:
        # M1: global ~8s cap — short-circuit leftovers once the deadline passes.
        if deadline is not None and time.monotonic() >= deadline:
            results[p] = False
            continue
        remaining = None
        if deadline is not None:
            remaining = max(0.1, deadline - time.monotonic())
        try:
            resp = ipc_request("isLoggedIn", p, timeout=min(2.0, remaining) if remaining else 2.0)
            results[p] = resp.get("loggedIn") is True
        except Exception as e:
            # M2: retain first per-provider failure for the `error` field.
            if errors is not None and not errors:
                errors.append(str(e)[:300])
            results[p] = False
    return results


def cmd_status():
    alive = True
    try:
        s = socket.create_connection(("127.0.0.1", load_port()), timeout=2.0)
        s.close()
    except Exception as e:
        alive = False
    # M1: monotonic ~8s deadline across the 4 probes only.
    deadline = time.monotonic() + 8.0
    first_errors = []
    try:
        providers = status_providers(deadline=deadline, errors=first_errors)
    except Exception as e:
        print(json.dumps({"alive": False, "allLoggedIn": False, "count": 0, "providers": {p: False for p in PROVIDERS}, "error": str(e)[:300]}))
        return 0
    if not alive:
        providers = {p: False for p in PROVIDERS}
    count = sum(1 for v in providers.values() if v) if alive else 0
    print(json.dumps({
        "alive": alive,
        "allLoggedIn": bool(alive and all(providers.values())),
        "count": count,
        "providers": providers,
        "error": (first_errors[0] if first_errors else ""),
    }))
    return 0


# Window class observed live via `hyprctl clients` (lowercase; matching is
# case-sensitive — "Proxima" never matches). Placement uses the sanctioned
# lua-dispatcher forms from default/hypr (cf. keepass-widget, tiling.lua);
# raw `hyprctl dispatch <verb> <args>` is rejected by this shell wrapper.
WIN_CLASS = "proxima"


def hypr_lua(code):
    if os.environ.get("PROXIMA_DRY_RUN") == "1":
        return 0
    try:
        r = subprocess.run(["hyprctl", "dispatch", code], capture_output=True, text=True, timeout=10)
        return r.returncode
    except Exception:
        return 1


def wait_for_ipc(timeout_s=30.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            s = socket.create_connection(("127.0.0.1", load_port()), timeout=2.0)
            s.close()
            return True
        except Exception:
            time.sleep(1.0)
    return False


GUI_LOG = "/tmp/proxima-gui.log"
GUI_LOG_CAP = 1024 * 1024  # keep last ~1MB


def launch_gui():
    # Cap /tmp/proxima-gui.log: truncate to the last ~1MB at launch when larger.
    try:
        if os.path.exists(GUI_LOG) and os.path.getsize(GUI_LOG) > GUI_LOG_CAP:
            with open(GUI_LOG, "rb") as f:
                f.seek(-GUI_LOG_CAP, os.SEEK_END)
                tail = f.read()
            with open(GUI_LOG, "wb") as f:
                f.write(tail)
    except Exception:
        pass
    log = open(GUI_LOG, "ab", buffering=0)
    try:
        subprocess.Popen(
            [ELECTRON_BIN, "."],
            cwd=PROXIMA_DIR,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        # Child keeps its dup'd fd; close the parent copy to avoid leaking one fd per launch.
        try:
            log.close()
        except Exception:
            pass
    return wait_for_ipc(30.0)


def hypr_clients():
    """Parse `hyprctl clients -j`; return client list or None on any failure."""
    if os.environ.get("PROXIMA_DRY_RUN") == "1":
        return None
    try:
        r = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return None
        data = json.loads(r.stdout or "null")
        return data if isinstance(data, list) else None
    except Exception:
        return None


def place_class_window(cls=WIN_CLASS):
    # Transient placement only; no persistent rule file.
    # Float-toggle auto-centers (observed live); no separate center verb exists
    # (hl.dsp.window.center() is a silent no-op), so float + focus + top is
    # the whole "middle, on top" recipe.
    hypr_lua('hl.dsp.focus({ window = "class:%s" })' % cls)
    # Idempotent float: skip the toggle when the window already floats.
    # Fallback: if the client query fails (or Hyprland is absent), skip the
    # toggle too — focus + bring_to_top alone never untile a window.
    try:
        clients = hypr_clients()
        already_floating = False
        if clients:
            for c in clients:
                if isinstance(c, dict) and c.get("class") == cls and c.get("floating") is True:
                    already_floating = True
                    break
        if not already_floating and clients is not None:
            hypr_lua('hl.dsp.window.float({ action = "toggle" })')
    except Exception:
        pass
    hypr_lua('hl.dsp.window.bring_to_top()')


def cmd_show():
    # Running path: honor the showWindow response body. Explicit
    # success:false means the hub refused — report failure WITHOUT launching
    # a duplicate GUI (which would conflict on the IPC port). Empty or
    # unparseable responses are retried once; only connection-level failures
    # or a persistent empty response fall through to the launch path.
    first_err = ""
    try:
        try:
            resp = ipc_request("showWindow", None, timeout=3.0)
        except Exception:
            resp = ipc_request("showWindow", None, timeout=3.0)  # one retry
        if isinstance(resp, dict) and resp.get("success", True) is False:
            hub_err = resp.get("error") or resp.get("message") or "hub reported success:false"
            print(json.dumps({"ok": False, "launched": False, "error": str(hub_err)[:300]}))
            return 0
        if os.environ.get("PROXIMA_DRY_RUN") != "1":
            place_class_window()
        print(json.dumps({"ok": True, "launched": False, "error": ""}))
        return 0
    except Exception as e:
        first_err = str(e)[:200]
    # Down path: launch GUI, wait, show, pin to workspace 10.
    try:
        if not launch_gui():
            print(json.dumps({"ok": False, "launched": True, "error": "IPC never ready after launch"}))
            return 0
        ipc_request("showWindow", None, timeout=5.0)
        if os.environ.get("PROXIMA_DRY_RUN") != "1":
            hypr_lua('hl.dsp.focus({ window = "class:%s" })' % WIN_CLASS)
            hypr_lua('hl.dsp.window.move({ workspace = "%s" })' % WS)
            hypr_lua('hl.dsp.focus({ workspace = "%s" })' % WS)
            place_class_window()
        print(json.dumps({"ok": True, "launched": True, "error": ""}))
        return 0
    except Exception as e:
        try:
            subprocess.run(["notify-send", "Proxima", "Launch failed: %s" % str(e)[:200]], timeout=5)
        except Exception:
            pass
        print(json.dumps({"ok": False, "launched": True, "error": (first_err + " / " + str(e))[:300]}))
        return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "status":
        return cmd_status()
    if cmd == "show":
        return cmd_show()
    print(json.dumps({"ok": False, "error": "unknown command: %s" % cmd}))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
