#!/usr/bin/env python3
import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


PROJECT_DIR = Path(os.getenv("PROJECT_DIR", "/opt/SignalKiosk"))
HOST = os.getenv("HOST_CONTROL_BIND", "127.0.0.1")
PORT = int(os.getenv("HOST_CONTROL_PORT", "9510"))
TOKEN = os.getenv("HOST_CONTROL_TOKEN", "")
RUNNER_SERVICE = os.getenv("RUNNER_SERVICE_NAME", "signalkiosk-cdp-runner.service")
LOCAL_CDP_WRAPPER = os.getenv("LOCAL_CDP_WRAPPER", "")


def _run(command: list[str]) -> tuple[int, str, str]:
    completed = subprocess.run(command, cwd=str(PROJECT_DIR), capture_output=True, text=True)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def _json(handler: BaseHTTPRequestHandler, code: int, payload: dict) -> None:
    raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


class Handler(BaseHTTPRequestHandler):
    server_version = "SignalKioskHostControl/1.0"

    def log_message(self, fmt: str, *args) -> None:
        return

    def _auth_ok(self) -> bool:
        expected = TOKEN.strip()
        if not expected:
            return False
        provided = self.headers.get("X-SignalKiosk-Control-Token", "").strip()
        return provided == expected

    def _restart_runner(self) -> tuple[int, dict]:
        if platform.system().lower().startswith("win"):
            wrapper = LOCAL_CDP_WRAPPER.strip() or str(PROJECT_DIR / "scripts" / "local-cdp.ps1")
            code, out, err = _run([
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                wrapper,
                "restart",
            ])
            if code != 0:
                return 500, {"ok": False, "error": err or out or "local-cdp restart failed"}
            return 200, {"ok": True, "action": "runner/restart"}

        code, out, err = _run(["systemctl", "restart", RUNNER_SERVICE])
        if code != 0:
            return 500, {"ok": False, "error": err or out or "systemctl restart failed"}
        return 200, {"ok": True, "action": "runner/restart"}

    def _docker_restart(self, service: str) -> tuple[int, dict]:
        code, out, err = _run(["docker", "compose", "restart", service])
        if code != 0:
            return 500, {"ok": False, "error": err or out or f"docker compose restart {service} failed"}
        return 200, {"ok": True, "action": f"docker/restart-{service}"}

    def _docker_restart_all(self) -> tuple[int, dict]:
        code, out, err = _run(["docker", "compose", "restart", "app", "frontend"])
        if code != 0:
            return 500, {"ok": False, "error": err or out or "docker compose restart app frontend failed"}
        return 200, {"ok": True, "action": "docker/restart-all"}

    def _status(self) -> tuple[int, dict]:
        code_runner, out_runner, err_runner = _run(["systemctl", "is-active", RUNNER_SERVICE])
        code_app, out_app, _ = _run(["docker", "compose", "ps", "--status", "running", "--services"])
        running_services = out_app.splitlines() if code_app == 0 and out_app else []
        return 200, {
            "ok": True,
            "time": datetime.now(timezone.utc).isoformat(),
            "runner_service": RUNNER_SERVICE,
            "runner_active": code_runner == 0 and out_runner.strip() == "active",
            "runner_detail": out_runner or err_runner,
            "docker_running_services": running_services,
        }

    def do_GET(self) -> None:
        if self.path != "/control/status":
            _json(self, 404, {"ok": False, "error": "not found"})
            return
        if not self._auth_ok():
            _json(self, 401, {"ok": False, "error": "unauthorized"})
            return
        code, payload = self._status()
        _json(self, code, payload)

    def do_POST(self) -> None:
        if not self._auth_ok():
            _json(self, 401, {"ok": False, "error": "unauthorized"})
            return

        route = self.path
        if route == "/control/runner/restart":
            code, payload = self._restart_runner()
            _json(self, code, payload)
            return
        if route == "/control/docker/restart-app":
            code, payload = self._docker_restart("app")
            _json(self, code, payload)
            return
        if route == "/control/docker/restart-frontend":
            code, payload = self._docker_restart("frontend")
            _json(self, code, payload)
            return
        if route == "/control/docker/restart-all":
            code, payload = self._docker_restart_all()
            _json(self, code, payload)
            return

        _json(self, 404, {"ok": False, "error": "not found"})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
