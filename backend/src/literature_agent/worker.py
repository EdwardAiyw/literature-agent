from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Any, Callable

from .config import Settings
from .db import Database
from .runner import execute_run, run_subscription


class LocalRunWorker:
    """Bounded single-process worker that recovers queued/interrupted runs on startup."""

    def __init__(self, settings: Settings, database: Database, max_workers: int = 1) -> None:
        self.settings, self.database = settings, database
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="literature-run")
        self._futures: dict[str, Future[Any]] = {}; self._lock = Lock()

    def _submit(self, run_id: str, function: Callable[..., Any], *args: Any) -> None:
        with self._lock:
            existing = self._futures.get(run_id)
            if existing and not existing.done(): return
            future = self.executor.submit(function, *args); self._futures[run_id] = future
            future.add_done_callback(lambda _: self._forget(run_id))

    def _forget(self, run_id: str) -> None:
        with self._lock: self._futures.pop(run_id, None)

    def submit_task(self, run_id: str, task: dict) -> None:
        self._submit(run_id, execute_run, self.settings, self.database, run_id, task)

    def submit_subscription(self, run_id: str, subscription: dict) -> None:
        self._submit(run_id, run_subscription, self.settings, self.database, subscription, True, run_id)

    def recover(self) -> int:
        recovered = 0
        for run in self.database.list_recoverable_runs():
            task = self.database.get_task(run["task_id"])
            if not task:
                self.database.update_run(run["id"], status="failed", current_node="failed", error="Recovery failed: task not found")
                continue
            self.database.update_run(run["id"], status="queued", current_node="recovery", error="")
            if run.get("trigger_kind") == "subscription" and run.get("subscription_id"):
                subscription = self.database.get_subscription(run["subscription_id"])
                if not subscription:
                    self.database.update_run(run["id"], status="failed", current_node="failed", error="Recovery failed: subscription not found")
                    continue
                self.submit_subscription(run["id"], subscription)
            else: self.submit_task(run["id"], task)
            recovered += 1
        return recovered

    def close(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=False)
