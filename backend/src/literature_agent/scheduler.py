from __future__ import annotations

import logging
import os
from datetime import datetime, time, timezone
from threading import Event, Thread
from typing import Callable
from zoneinfo import ZoneInfo

from .config import Settings
from .daily import due_subscriptions
from .db import Database
from .worker import LocalRunWorker


logger = logging.getLogger(__name__)


class DailyScheduler:
    """Opt-in server scheduler using the existing bounded worker and daily DB guard."""

    def __init__(self, settings: Callable[[], Settings], database: Database, worker: LocalRunWorker, interval: float = 60) -> None:
        self.settings, self.database, self.worker = settings, database, worker
        self.interval = interval
        self.stop = Event()
        self.thread = Thread(target=self._loop, name="literature-daily", daemon=True)
        self.last_checked_at = ""
        self.last_error = ""

    def tick(self, now_utc: datetime | None = None) -> int:
        current = self.settings()
        self.last_checked_at = datetime.now(timezone.utc).isoformat()
        if os.getenv("LITERATURE_AGENT_SCHEDULER_PAUSED", "false").lower() in {"1", "true", "yes"}:
            return 0
        if not (current.live and current.llm_model and current.llm_api_key and current.smtp_host and current.smtp_from):
            return 0
        instant = now_utc or datetime.now(timezone.utc)
        count = 0
        for subscription in due_subscriptions(self.database, self.database.list_subscriptions(enabled_only=True), instant):
            task = self.database.get_task(subscription["task_id"])
            if not task:
                continue
            local = instant.astimezone(ZoneInfo(subscription["timezone"]))
            start = datetime.combine(local.date(), time.min, tzinfo=local.tzinfo).astimezone(timezone.utc).isoformat()
            run = self.database.create_run_if_idle(task["id"], 7 if task.get("evidence_review") else 6,
                trigger_kind="subscription", subscription_id=subscription["id"], not_before=start)
            if run:
                try:
                    self.worker.submit_subscription(run["id"], subscription)
                except Exception:
                    self.database.update_run(run["id"], status="failed", current_node="failed", error="Scheduler could not queue subscription")
                    raise
                count += 1
        return count

    def _loop(self) -> None:
        while not self.stop.is_set():
            try:
                self.tick()
                self.last_error = ""
            except Exception as exc:
                self.last_error = type(exc).__name__
                logger.error("Daily scheduler check failed: %s", self.last_error)
            self.stop.wait(self.interval)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.stop.set()
        self.thread.join()

    def status(self) -> dict:
        return {"supported": False, "mode": "internal", "running": self.thread.is_alive(),
            "interval_seconds": self.interval, "last_checked_at": self.last_checked_at,
            "error": self.last_error, "tasks": []}
