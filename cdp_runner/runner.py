import base64
import json
import os
from pathlib import Path
import subprocess
import time
from datetime import datetime

import httpx
from websocket import create_connection


APP_BASE_URL = os.getenv("APP_BASE_URL", "http://app:8000").rstrip("/")
COMMAND_ENDPOINT = os.getenv("PLAYBACK_COMMAND_ENDPOINT", "/api/playback/command")
POLL_INTERVAL_SECONDS = float(os.getenv("POLL_INTERVAL_SECONDS", "1.5"))
CHROME_BIN = os.getenv("CHROME_BIN", "chromium")
CDP_PORT = int(os.getenv("CDP_PORT", "9222"))
WINDOW_SIZE = os.getenv("CHROME_WINDOW_SIZE", "1920,1080")
HEADLESS = os.getenv("CHROME_HEADLESS", "false").lower() == "true"
ALLOW_INSECURE = os.getenv("CHROME_ALLOW_INSECURE", "false").lower() == "true"
USER_DATA_DIR = os.getenv("CHROME_USER_DATA_DIR", "")
RUNNER_VERBOSE = os.getenv("RUNNER_VERBOSE", "true").lower() == "true"


def _log(message: str) -> None:
    if RUNNER_VERBOSE:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[cdp-runner] {stamp} {message}", flush=True)


class CdpSession:
    def __init__(self, ws_url: str) -> None:
        self.ws = create_connection(ws_url, timeout=10)
        self.next_id = 1

    def call(self, method: str, params: dict | None = None) -> dict:
        call_id = self.next_id
        self.next_id += 1
        payload = {"id": call_id, "method": method, "params": params or {}}
        self.ws.send(json.dumps(payload))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") != call_id:
                continue
            if "error" in message:
                raise RuntimeError(f"CDP error in {method}: {message['error']}")
            return message.get("result", {})

    def close(self) -> None:
        self.ws.close()


def _to_data_url(raw_html: str) -> str:
    encoded = base64.b64encode(raw_html.encode("utf-8")).decode("ascii")
    return f"data:text/html;base64,{encoded}"


def _browser_flags() -> list[str]:
    flags = [
        "--kiosk",
        "--start-fullscreen",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--disable-infobars",
        "--disable-translate",
        "--autoplay-policy=no-user-gesture-required",
        "--disable-features=Translate,TranslateUI",
        "--lang=de-DE",
        "--new-window",
        f"--window-size={WINDOW_SIZE}",
        f"--remote-debugging-port={CDP_PORT}",
        "--remote-debugging-address=0.0.0.0",
        "--remote-allow-origins=*",
        "about:blank",
    ]
    if USER_DATA_DIR:
        flags.insert(0, f"--user-data-dir={USER_DATA_DIR}")
    if HEADLESS:
        flags.append("--headless=new")
    if ALLOW_INSECURE:
        flags.extend(
            [
                "--ignore-certificate-errors",
                "--allow-running-insecure-content",
                "--disable-web-security",
            ]
        )
    return flags


def _merge_dict(base: dict, update: dict) -> dict:
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge_dict(base[key], value)
        else:
            base[key] = value
    return base


def _prepare_chrome_profile() -> None:
    if not USER_DATA_DIR:
        return
    root = Path(USER_DATA_DIR)
    default_dir = root / "Default"
    default_dir.mkdir(parents=True, exist_ok=True)

    # Suppress first-run flows and translation prompts.
    (root / "First Run").write_text("", encoding="utf-8")

    prefs_path = default_dir / "Preferences"
    prefs = {}
    if prefs_path.exists():
        try:
            prefs = json.loads(prefs_path.read_text(encoding="utf-8"))
        except Exception:
            prefs = {}

    desired = {
        "translate": {"enabled": False},
        "translate_site_blacklist": [],
        "translate_blocked_languages": ["*"],
        "browser": {"has_seen_welcome_page": True},
        "distribution": {
            "skip_first_run_ui": True,
            "suppress_first_run_default_browser_prompt": True,
        },
    }
    merged = _merge_dict(prefs if isinstance(prefs, dict) else {}, desired)
    prefs_path.write_text(json.dumps(merged, ensure_ascii=True), encoding="utf-8")


def _absolute_url(value: str) -> str:
    if value.startswith("http://") or value.startswith("https://") or value.startswith("data:"):
        return value
    if value.startswith("/"):
        return f"{APP_BASE_URL}{value}"
    return f"{APP_BASE_URL}/{value}"


def _payload_to_url(command: dict) -> str:
    content_type = str(command.get("content_type") or "").lower()
    if content_type == "webpage":
        return str(command.get("url") or "about:blank")
    if content_type == "html":
        return _to_data_url(str(command.get("html") or ""))
    if content_type == "image":
        src = _absolute_url(str(command.get("asset_path") or ""))
        markup = f"<html><body style='margin:0;background:#000;display:grid;place-items:center;height:100vh'><img src='{src}' style='max-width:100vw;max-height:100vh;object-fit:contain'></body></html>"
        return _to_data_url(markup)
    if content_type == "video":
        src = _absolute_url(str(command.get("asset_path") or ""))
        markup = f"<html><body style='margin:0;background:#000;display:grid;place-items:center;height:100vh'><video src='{src}' autoplay muted controls style='width:100vw;height:100vh;object-fit:contain'></video></body></html>"
        return _to_data_url(markup)
    return _to_data_url("<html><body style='margin:0;background:#000;color:#fff;font-family:sans-serif;display:grid;place-items:center;height:100vh'>Kein aktiver Inhalt</body></html>")


def _launch_browser() -> subprocess.Popen:
    _prepare_chrome_profile()
    cmd = [CHROME_BIN, *_browser_flags()]
    _log(f"Launching browser: {CHROME_BIN}")
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _wait_for_page_ws() -> str:
    with httpx.Client(timeout=5.0) as client:
        for _ in range(40):
            try:
                targets = client.get(f"http://127.0.0.1:{CDP_PORT}/json/list").json()
                for item in targets:
                    if item.get("type") == "page" and item.get("webSocketDebuggerUrl"):
                        return str(item["webSocketDebuggerUrl"])
            except Exception:
                pass
            time.sleep(0.25)
    raise RuntimeError("CDP page target not available")


def _try_get_page_ws() -> str | None:
    try:
        with httpx.Client(timeout=2.0) as client:
            targets = client.get(f"http://127.0.0.1:{CDP_PORT}/json/list").json()
        for item in targets:
            if item.get("type") == "page" and item.get("webSocketDebuggerUrl"):
                return str(item["webSocketDebuggerUrl"])
    except Exception:
        return None
    return None


def _fetch_command(since_revision: int | None, since_hash: str | None) -> dict:
    with httpx.Client(timeout=10.0) as client:
        params = {}
        if since_revision is not None:
            params["since_revision"] = since_revision
        if since_hash is not None:
            params["since_hash"] = since_hash
        res = client.get(f"{APP_BASE_URL}{COMMAND_ENDPOINT}", params=params)
        res.raise_for_status()
        return res.json()


def run() -> None:
    last_revision: int | None = None
    last_hash: str | None = None
    consecutive_failures = 0
    while True:
        browser = None
        cdp = None
        try:
            ws_url = _try_get_page_ws()
            if ws_url:
                _log("Reusing existing CDP browser target")
            else:
                browser = _launch_browser()
                ws_url = _wait_for_page_ws()
            cdp = CdpSession(ws_url)
            cdp.call("Page.enable")
            _log("Browser connected via CDP")
            consecutive_failures = 0

            while True:
                if browser is not None and browser.poll() is not None:
                    raise RuntimeError("Chrome process stopped")
                try:
                    payload = _fetch_command(last_revision, last_hash)
                except Exception as exc:
                    _log(f"Command fetch failed: {exc}")
                    time.sleep(POLL_INTERVAL_SECONDS)
                    continue
                if not payload.get("changed"):
                    time.sleep(POLL_INTERVAL_SECONDS)
                    continue
                target_url = _payload_to_url(payload)
                _log(f"Navigate -> {target_url[:180]}")
                cdp.call("Page.navigate", {"url": target_url})
                next_revision = payload.get("revision")
                if isinstance(next_revision, int):
                    last_revision = next_revision
                next_hash = payload.get("hash")
                if isinstance(next_hash, str) and next_hash:
                    last_hash = next_hash
                time.sleep(POLL_INTERVAL_SECONDS)
        except Exception as exc:
            consecutive_failures += 1
            _log(f"Runner cycle failed: {exc}")
            backoff = min(30, 2 * consecutive_failures)
            time.sleep(backoff)
        finally:
            if cdp is not None:
                try:
                    cdp.close()
                except Exception:
                    pass


if __name__ == "__main__":
    run()
