from __future__ import annotations

import argparse
import logging
from logging.handlers import TimedRotatingFileHandler
import socket
import sys
import threading
import time
import webbrowser

import httpx
import uvicorn

from .config import ConfigManager, Settings


def _configure_logging() -> None:
    current = ConfigManager(Settings.from_env()).get()
    log_dir = current.data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = TimedRotatingFileHandler(log_dir / "literature-agent.log", when="midnight", backupCount=14, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _healthy(url: str) -> bool:
    try:
        return httpx.get(f"{url}/api/health", timeout=2).status_code == 200
    except Exception:
        return False


def _open_when_ready(url: str) -> None:
    for _ in range(60):
        if _healthy(url):
            webbrowser.open(url)
            return
        time.sleep(0.25)


def main() -> int:
    _configure_logging()
    parser = argparse.ArgumentParser(description="Literature Agent for Windows")
    parser.add_argument("--run-due", action="store_true")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if args.run_due:
        from .daily import main as daily_main
        sys.argv = [sys.argv[0], "--run-due"]
        return daily_main()

    url = f"http://127.0.0.1:{args.port}"
    if _healthy(url):
        if not args.no_browser:
            webbrowser.open(url)
        return 0
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            raise SystemExit(f"Port {args.port} is already in use by another application")
    if not args.no_browser:
        threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()
    uvicorn.run("literature_agent.api:app", host="127.0.0.1", port=args.port, log_level="info", log_config=None, access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
