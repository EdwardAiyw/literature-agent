from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from threading import RLock
from typing import TypeVar
from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


def upgrade_database(path: Path) -> None:
    backend_root = Path(getattr(sys, "_MEIPASS")) / "backend" if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.resolve().as_posix()}")
    if path.is_file():
        current = ""
        connection = sqlite3.connect(path)
        try:
            table = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'").fetchone()
            if table:
                row = connection.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
                current = row[0] if row else ""
            head = ScriptDirectory.from_config(config).get_current_head() or ""
            if current != head:
                backup_dir = path.parent / "backups"
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup_path = backup_dir / f"pre-migration-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
                backup = sqlite3.connect(backup_path)
                try:
                    connection.backup(backup)
                finally:
                    backup.close()
        finally:
            connection.close()
    command.upgrade(config, "head")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


DatabaseType = TypeVar("DatabaseType", bound=type)


def serialize_connection_access(cls: DatabaseType) -> DatabaseType:
    """Serialize every instance method that can reach the shared SQLite connection."""
    for name, member in tuple(vars(cls).items()):
        if name == "__init__" or isinstance(member, staticmethod) or not callable(member):
            continue

        @wraps(member)
        def locked(self, *args, __method=member, **kwargs):
            with self._lock:
                return __method(self, *args, **kwargs)

        setattr(cls, name, locked)
    return cls


@serialize_connection_access
class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        upgrade_database(path)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = RLock()
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("PRAGMA busy_timeout=5000")

    def create_task(self, payload: dict) -> dict:
        task_id = str(uuid4())
        timestamp = now()
        self.connection.execute("INSERT INTO tasks VALUES (?, ?, ?, ?)", (task_id, json.dumps(payload, ensure_ascii=False), timestamp, timestamp))
        self.connection.commit()
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> dict | None:
        row = self.connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return None
        return {**json.loads(row["payload"]), "id": row["id"], "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def list_tasks(self) -> list[dict]:
        rows = self.connection.execute("SELECT id FROM tasks ORDER BY created_at DESC").fetchall()
        return [self.get_task(row["id"]) for row in rows]

    def update_task(self, task_id: str, payload: dict) -> dict | None:
        timestamp = now()
        result = self.connection.execute("UPDATE tasks SET payload = ?, updated_at = ? WHERE id = ?", (json.dumps(payload, ensure_ascii=False), timestamp, task_id))
        self.connection.commit()
        return self.get_task(task_id) if result.rowcount else None

    def create_subscription(self, task_id: str, payload: dict) -> dict:
        subscription_id = str(uuid4())
        timestamp = now()
        self.connection.execute(
            "INSERT INTO subscriptions(id, task_id, payload, enabled, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (subscription_id, task_id, json.dumps(payload, ensure_ascii=False), int(bool(payload.get("enabled", True))), timestamp, timestamp),
        )
        self.connection.commit()
        return self.get_subscription(subscription_id)

    def get_subscription(self, subscription_id: str) -> dict | None:
        row = self.connection.execute("SELECT * FROM subscriptions WHERE id = ?", (subscription_id,)).fetchone()
        if not row:
            return None
        return {**json.loads(row["payload"]), "id": row["id"], "task_id": row["task_id"], "enabled": bool(row["enabled"]), "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def list_subscriptions(self, enabled_only: bool = False) -> list[dict]:
        query = "SELECT id FROM subscriptions"
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY created_at DESC"
        return [self.get_subscription(row["id"]) for row in self.connection.execute(query).fetchall()]

    def update_subscription(self, subscription_id: str, payload: dict) -> dict | None:
        timestamp = now()
        result = self.connection.execute(
            "UPDATE subscriptions SET payload = ?, enabled = ?, updated_at = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=False), int(bool(payload.get("enabled", True))), timestamp, subscription_id),
        )
        self.connection.commit()
        return self.get_subscription(subscription_id) if result.rowcount else None

    def delete_subscription(self, subscription_id: str) -> bool:
        """Delete a subscription and all data owned by its task in one transaction."""
        subscription = self.connection.execute(
            "SELECT task_id FROM subscriptions WHERE id = ?", (subscription_id,)
        ).fetchone()
        if not subscription:
            return False

        task_id = subscription["task_id"]
        shared_task = self.connection.execute(
            "SELECT 1 FROM subscriptions WHERE task_id = ? AND id != ? LIMIT 1",
            (task_id, subscription_id),
        ).fetchone()
        run_rows = self.connection.execute(
            "SELECT id FROM runs WHERE task_id = ?", (task_id,)
        ).fetchall()
        run_ids = [row["id"] for row in run_rows]

        try:
            self.connection.execute("BEGIN")
            self.connection.execute("DELETE FROM deliveries WHERE subscription_id = ?", (subscription_id,))
            if run_ids and not shared_task:
                placeholders = ",".join("?" for _ in run_ids)
                self.connection.execute(f"DELETE FROM papers WHERE run_id IN ({placeholders})", run_ids)
                self.connection.execute(f"DELETE FROM run_events WHERE run_id IN ({placeholders})", run_ids)
                self.connection.execute(f"DELETE FROM run_artifacts WHERE run_id IN ({placeholders})", run_ids)
                self.connection.execute(f"DELETE FROM runs WHERE id IN ({placeholders})", run_ids)
            self.connection.execute("DELETE FROM subscriptions WHERE id = ?", (subscription_id,))
            if not shared_task:
                self.connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return True

    def create_delivery(self, subscription_id: str, run_id: str | None, kind: str, recipient: str, subject: str, status: str = "pending") -> dict:
        delivery_id = str(uuid4())
        timestamp = now()
        self.connection.execute(
            "INSERT INTO deliveries(id, subscription_id, run_id, kind, status, recipient, subject, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (delivery_id, subscription_id, run_id, kind, status, recipient, subject, timestamp),
        )
        self.connection.commit()
        return self.get_delivery(delivery_id)

    def get_delivery(self, delivery_id: str) -> dict | None:
        row = self.connection.execute("SELECT * FROM deliveries WHERE id = ?", (delivery_id,)).fetchone()
        return dict(row) if row else None

    def update_delivery(self, delivery_id: str, **values) -> dict | None:
        if not values:
            return self.get_delivery(delivery_id)
        assignments = ", ".join(f"{key} = ?" for key in values)
        self.connection.execute(f"UPDATE deliveries SET {assignments} WHERE id = ?", (*values.values(), delivery_id))
        self.connection.commit()
        return self.get_delivery(delivery_id)

    def list_deliveries(self, subscription_id: str | None = None, limit: int = 50) -> list[dict]:
        if subscription_id:
            rows = self.connection.execute("SELECT * FROM deliveries WHERE subscription_id = ? ORDER BY created_at DESC LIMIT ?", (subscription_id, limit)).fetchall()
        else:
            rows = self.connection.execute("SELECT * FROM deliveries ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def create_run(self, task_id: str, total_steps: int, trigger_kind: str = "manual", subscription_id: str | None = None) -> dict:
        run_id = str(uuid4())
        self.connection.execute(
            "INSERT INTO runs(id, task_id, status, total_steps, trigger_kind, subscription_id, started_at) VALUES (?, ?, 'queued', ?, ?, ?, ?)",
            (run_id, task_id, total_steps, trigger_kind, subscription_id, now()),
        )
        self.connection.commit()
        return self.get_run(run_id)

    def create_run_if_idle(self, task_id: str, total_steps: int, trigger_kind: str = "manual", subscription_id: str | None = None, not_before: str | None = None) -> dict | None:
        """Atomically enqueue a run across API and scheduler processes."""
        with self._lock:
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                active = self.connection.execute(
                    "SELECT id FROM runs WHERE task_id = ? AND status IN ('queued', 'running', 'paused') LIMIT 1",
                    (task_id,),
                ).fetchone()
                already_ran = None
                if not_before:
                    already_ran = self.connection.execute(
                        "SELECT id FROM runs WHERE task_id = ? AND trigger_kind = 'subscription' AND started_at >= ? LIMIT 1",
                        (task_id, not_before),
                    ).fetchone()
                if active or already_ran:
                    self.connection.rollback()
                    return None
                run_id = str(uuid4())
                self.connection.execute(
                    "INSERT INTO runs(id, task_id, status, total_steps, trigger_kind, subscription_id, started_at) VALUES (?, ?, 'queued', ?, ?, ?, ?)",
                    (run_id, task_id, total_steps, trigger_kind, subscription_id, now()),
                )
                self.connection.commit()
                return self.get_run(run_id)
            except Exception:
                self.connection.rollback()
                raise

    def get_run(self, run_id: str) -> dict | None:
        row = self.connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        return dict(row)

    def list_runs(self, task_id: str, limit: int = 50) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT * FROM runs
            WHERE task_id = ?
            ORDER BY COALESCE(started_at, '') DESC, rowid DESC
            LIMIT ?
            """,
            (task_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_recoverable_runs(self) -> list[dict]:
        rows = self.connection.execute(
            "SELECT * FROM runs WHERE status IN ('queued', 'running') ORDER BY started_at"
        ).fetchall()
        return [dict(row) for row in rows]

    def has_run_since(self, task_id: str, started_at: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM runs WHERE task_id = ? AND started_at >= ? LIMIT 1",
            (task_id, started_at),
        ).fetchone()
        return row is not None

    def update_run(self, run_id: str, **values) -> None:
        if not values:
            return
        assignments = ", ".join(f"{key} = ?" for key in values)
        self.connection.execute(f"UPDATE runs SET {assignments} WHERE id = ?", (*values.values(), run_id))
        self.connection.commit()

    def add_paper(self, run_id: str, canonical_id: str, payload: dict) -> None:
        self.connection.execute("INSERT OR IGNORE INTO papers(id, run_id, canonical_id, payload) VALUES (?, ?, ?, ?)", (str(uuid4()), run_id, canonical_id, json.dumps(payload, ensure_ascii=False)))
        self.connection.commit()

    def add_run_event(self, run_id: str, node: str, status: str, message: str, artifact_type: str = "") -> None:
        self.connection.execute(
            "INSERT INTO run_events(run_id, node, status, message, artifact_type, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, node, status, message, artifact_type, now()),
        )
        self.connection.commit()

    def list_run_events(self, run_id: str) -> list[dict]:
        rows = self.connection.execute("SELECT * FROM run_events WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
        return [dict(row) for row in rows]

    def save_run_artifact(self, run_id: str, node: str, payload: dict) -> None:
        self.connection.execute(
            """
            INSERT INTO run_artifacts(run_id, node, payload, created_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(run_id, node) DO UPDATE SET payload=excluded.payload, created_at=excluded.created_at
            """,
            (run_id, node, json.dumps(payload, ensure_ascii=False), now()),
        )
        self.connection.commit()

    def get_run_artifact(self, run_id: str, node: str) -> dict | None:
        row = self.connection.execute("SELECT * FROM run_artifacts WHERE run_id = ? AND node = ?", (run_id, node)).fetchone()
        if not row:
            return None
        return {**dict(row), "payload": json.loads(row["payload"])}

    def list_run_artifacts(self, run_id: str) -> list[dict]:
        rows = self.connection.execute("SELECT * FROM run_artifacts WHERE run_id = ? ORDER BY created_at", (run_id,)).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    def list_papers(self, run_id: str) -> list[dict]:
        rows = self.connection.execute("SELECT * FROM papers WHERE run_id = ? ORDER BY json_extract(payload, '$.relevance_score') DESC", (run_id,)).fetchall()
        return [{**json.loads(row["payload"]), "id": row["id"], "run_id": row["run_id"], "review": row["review"]} for row in rows]

    def review_paper(self, paper_id: str, review: str) -> bool:
        result = self.connection.execute("UPDATE papers SET review = ? WHERE id = ?", (review, paper_id))
        self.connection.commit()
        return result.rowcount > 0

    def seed_builtin_prompts(self, prompts: list[dict]) -> None:
        timestamp = now()
        for prompt in prompts:
            self.connection.execute(
                """
                INSERT INTO prompts(id, role, version, body, builtin) VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(id) DO UPDATE SET role=excluded.role, version=excluded.version, body=excluded.body, builtin=1
                """,
                (prompt["id"], prompt["role"], prompt["version"], prompt["body"]),
            )
            self.connection.execute(
                "UPDATE prompts SET created_at = CASE WHEN created_at = '' THEN ? ELSE created_at END, updated_at = ? WHERE id = ?",
                (timestamp, timestamp, prompt["id"]),
            )
            active = self.connection.execute("SELECT 1 FROM prompts WHERE role = ? AND active = 1", (prompt["role"],)).fetchone()
            if not active:
                self.connection.execute("UPDATE prompts SET active = 1 WHERE id = ?", (prompt["id"],))
        self.connection.commit()

    def list_prompts(self) -> list[dict]:
        rows = self.connection.execute("SELECT * FROM prompts ORDER BY role, version").fetchall()
        return [{**dict(row), "builtin": bool(row["builtin"]), "active": bool(row["active"])} for row in rows]

    def add_decision_call(self, value: dict) -> dict:
        call_id = value.get("id") or str(uuid4())
        row = {
            "id": call_id, "run_id": value["run_id"], "stage": value["stage"],
            "subject_id": value.get("subject_id", ""), "mode": value["mode"], "status": value["status"],
            "requested_model": value["requested_model"], "resolved_model": value.get("resolved_model", ""),
            "schema_version": value["schema_version"], "state_hash": value.get("state_hash", ""),
            "answers": json.dumps(value.get("answers", {}), ensure_ascii=False),
            "outcome": json.dumps(value.get("outcome", {}), ensure_ascii=False),
            "confidence": float(value.get("confidence", 0)), "latency_ms": float(value.get("latency_ms", 0)),
            "input_tokens": int(value.get("input_tokens", 0)), "cached": int(bool(value.get("cached"))),
            "fallback_used": int(bool(value.get("fallback_used"))), "fallback_reason": value.get("fallback_reason", ""),
            "error": value.get("error", ""),
            "created_at": value.get("created_at") or now(),
        }
        with self._lock:
            self.connection.execute(
                """INSERT INTO decision_calls (
                id,run_id,stage,subject_id,mode,status,requested_model,resolved_model,schema_version,state_hash,
                answers,outcome,confidence,latency_ms,input_tokens,cached,fallback_used,fallback_reason,error,created_at
                ) VALUES (
                :id,:run_id,:stage,:subject_id,:mode,:status,:requested_model,:resolved_model,:schema_version,:state_hash,
                :answers,:outcome,:confidence,:latency_ms,:input_tokens,:cached,:fallback_used,:fallback_reason,:error,:created_at
                )""", row)
            self.connection.commit()
        return self.get_decision_call(call_id)

    def get_decision_call(self, call_id: str) -> dict | None:
        row = self.connection.execute("SELECT * FROM decision_calls WHERE id = ?", (call_id,)).fetchone()
        return self._decision(row)

    @staticmethod
    def _decision(row) -> dict | None:
        if not row:
            return None
        value = dict(row)
        value["answers"] = json.loads(value["answers"])
        value["outcome"] = json.loads(value["outcome"])
        value["cached"] = bool(value["cached"])
        value["fallback_used"] = bool(value["fallback_used"])
        return value

    def list_decision_calls(self, run_id: str) -> list[dict]:
        rows = self.connection.execute(
            "SELECT * FROM decision_calls WHERE run_id = ? ORDER BY created_at, id", (run_id,)
        ).fetchall()
        return [self._decision(row) for row in rows]

    def _get_cache(self, table: str, cache_key: str):
        with self._lock:
            row = self.connection.execute(f"SELECT * FROM {table} WHERE cache_key = ?", (cache_key,)).fetchone()
            if not row:
                return None
            if row["expires_at"] <= now():
                self.connection.execute(f"DELETE FROM {table} WHERE cache_key = ?", (cache_key,))
                self.connection.commit()
                return None
        return json.loads(row["payload"])

    def get_decision_cache(self, cache_key: str) -> dict | None:
        return self._get_cache("decision_cache", cache_key)

    def save_decision_cache(self, cache_key: str, model: str, schema_version: str, payload: dict, ttl_hours: int) -> None:
        timestamp = datetime.now(timezone.utc)
        with self._lock:
            self.connection.execute(
                """INSERT INTO decision_cache VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET model=excluded.model, schema_version=excluded.schema_version,
                payload=excluded.payload, expires_at=excluded.expires_at, created_at=excluded.created_at""",
                (cache_key, model, schema_version, json.dumps(payload, ensure_ascii=False),
                 (timestamp + timedelta(hours=ttl_hours)).isoformat(), timestamp.isoformat()),
            )
            self.connection.commit()

    def get_source_cache(self, cache_key: str) -> list[dict] | None:
        payload = self._get_cache("source_cache", cache_key)
        return payload if isinstance(payload, list) else None

    def save_source_cache(self, cache_key: str, provider: str, payload: list[dict], ttl_hours: int) -> None:
        timestamp = datetime.now(timezone.utc)
        with self._lock:
            self.connection.execute(
                """INSERT INTO source_cache VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET provider=excluded.provider, payload=excluded.payload,
                expires_at=excluded.expires_at, created_at=excluded.created_at""",
                (cache_key, provider, json.dumps(payload, ensure_ascii=False),
                 (timestamp + timedelta(hours=ttl_hours)).isoformat(), timestamp.isoformat()),
            )
            self.connection.commit()

    def reserve_source_requests(self, provider: str, count: int, budget: int) -> bool:
        usage_date = date.today().isoformat()
        with self._lock:
            total = self.connection.execute(
                "SELECT COALESCE(SUM(requests), 0) FROM source_usage WHERE usage_date = ?", (usage_date,)
            ).fetchone()[0]
            if count < 1 or total + count > budget:
                return count < 1
            self.connection.execute(
                """INSERT INTO source_usage(provider, usage_date, requests) VALUES (?, ?, ?)
                ON CONFLICT(provider, usage_date) DO UPDATE SET requests=requests+excluded.requests""",
                (provider, usage_date, count),
            )
            self.connection.commit()
        return True

    def source_usage_snapshot(self) -> dict[str, int]:
        rows = self.connection.execute(
            "SELECT provider, requests FROM source_usage WHERE usage_date = ?", (date.today().isoformat(),)
        ).fetchall()
        return {row["provider"]: int(row["requests"]) for row in rows}

    def source_usage_total(self) -> int:
        return sum(self.source_usage_snapshot().values())

    def health(self) -> dict:
        with self._lock:
            self.connection.execute("SELECT 1").fetchone()
            return {
                "ok": True,
                "path": str(self.path),
                "writable": self.path.parent.exists() and os.access(self.path.parent, os.W_OK),
            }

    def backup(self, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target = sqlite3.connect(destination)
            try:
                self.connection.backup(target)
            finally:
                target.close()
        return destination

    @staticmethod
    def validate_backup(path: Path) -> None:
        if not path.is_file():
            raise ValueError("Backup file does not exist")
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            result = connection.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise ValueError("Backup database failed integrity_check")
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"tasks", "runs", "subscriptions"}.issubset(tables):
                raise ValueError("Backup is not a Literature Agent database")
        finally:
            connection.close()

    def cleanup_test_tasks(self) -> int:
        """Remove only explicitly marked or known fixture tasks during app startup."""
        allowlist = {"Evidence test", "RAG test", "Prompt override test", "Protected", "Protected task", "Agentic RAG 测试"}
        rows = self.connection.execute("SELECT id, payload FROM tasks").fetchall()
        candidates: list[str] = []
        for row in rows:
            payload = json.loads(row["payload"])
            marked_test = payload.get("origin") == "test" or payload.get("name") in allowlist
            if marked_test:
                blockers = self.task_blockers(row["id"])
                if not blockers["active_runs"]:
                    candidates.append(row["id"])
        if not candidates:
            return 0
        try:
            self.connection.execute("BEGIN")
            for task_id in candidates:
                self.connection.execute(
                    "DELETE FROM deliveries WHERE subscription_id IN (SELECT id FROM subscriptions WHERE task_id = ?)",
                    (task_id,),
                )
                self.connection.execute("DELETE FROM subscriptions WHERE task_id = ?", (task_id,))
                self._delete_task_data(task_id)
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return len(candidates)

    def task_blockers(self, task_id: str) -> dict:
        subscription = self.connection.execute(
            "SELECT id FROM subscriptions WHERE task_id = ? LIMIT 1", (task_id,)
        ).fetchone()
        active_runs = self.connection.execute(
            "SELECT id FROM runs WHERE task_id = ? AND status IN ('queued', 'running', 'paused') ORDER BY started_at",
            (task_id,),
        ).fetchall()
        return {
            "subscribed": subscription is not None,
            "active_runs": [row["id"] for row in active_runs],
        }

    def _delete_task_data(self, task_id: str) -> None:
        run_rows = self.connection.execute("SELECT id FROM runs WHERE task_id = ?", (task_id,)).fetchall()
        run_ids = [row["id"] for row in run_rows]
        if run_ids:
            placeholders = ",".join("?" for _ in run_ids)
            self.connection.execute(f"DELETE FROM papers WHERE run_id IN ({placeholders})", run_ids)
            self.connection.execute(f"DELETE FROM run_events WHERE run_id IN ({placeholders})", run_ids)
            self.connection.execute(f"DELETE FROM run_artifacts WHERE run_id IN ({placeholders})", run_ids)
            self.connection.execute(f"DELETE FROM runs WHERE id IN ({placeholders})", run_ids)
        self.connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    def delete_task(self, task_id: str) -> str:
        """Delete an unowned task and its run data, returning the outcome."""
        if not self.get_task(task_id):
            return "missing"
        blockers = self.task_blockers(task_id)
        if blockers["subscribed"]:
            return "subscribed"
        if blockers["active_runs"]:
            return "active"
        try:
            self.connection.execute("BEGIN")
            self._delete_task_data(task_id)
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return "deleted"

    def delete_tasks(self, task_ids: list[str]) -> dict:
        missing = [task_id for task_id in task_ids if not self.get_task(task_id)]
        if missing:
            return {"status": "missing", "task_ids": missing}
        subscribed: list[str] = []
        active: dict[str, list[str]] = {}
        for task_id in task_ids:
            blockers = self.task_blockers(task_id)
            if blockers["subscribed"]:
                subscribed.append(task_id)
            if blockers["active_runs"]:
                active[task_id] = blockers["active_runs"]
        if subscribed or active:
            return {"status": "blocked", "subscribed": subscribed, "active": active}
        try:
            self.connection.execute("BEGIN")
            for task_id in task_ids:
                self._delete_task_data(task_id)
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return {"status": "deleted", "task_ids": task_ids}

    def get_prompt(self, prompt_id: str) -> dict | None:
        row = self.connection.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
        if not row:
            return None
        return {**dict(row), "builtin": bool(row["builtin"]), "active": bool(row["active"])}

    def create_prompt_override(self, role: str, body: str, parent_id: str | None = None) -> dict:
        prompt_id = f"{role}.custom.{uuid4().hex[:10]}"
        version = f"custom-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        timestamp = now()
        self.connection.execute("BEGIN")
        try:
            self.connection.execute("UPDATE prompts SET active = 0, updated_at = ? WHERE role = ?", (timestamp, role))
            self.connection.execute(
                "INSERT INTO prompts(id, role, version, body, builtin, active, parent_id, created_at, updated_at) VALUES (?, ?, ?, ?, 0, 1, ?, ?, ?)",
                (prompt_id, role, version, body.strip(), parent_id, timestamp, timestamp),
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return self.get_prompt(prompt_id)  # type: ignore[return-value]

    def activate_prompt(self, prompt_id: str) -> dict | None:
        prompt = self.get_prompt(prompt_id)
        if not prompt:
            return None
        timestamp = now()
        self.connection.execute("BEGIN")
        try:
            self.connection.execute("UPDATE prompts SET active = 0, updated_at = ? WHERE role = ?", (timestamp, prompt["role"]))
            self.connection.execute("UPDATE prompts SET active = 1, updated_at = ? WHERE id = ?", (timestamp, prompt_id))
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return self.get_prompt(prompt_id)

    def delete_prompt_override(self, prompt_id: str) -> dict | None:
        prompt = self.get_prompt(prompt_id)
        if not prompt or prompt["builtin"]:
            return None
        self.connection.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
        if prompt["active"]:
            builtin = self.connection.execute("SELECT id FROM prompts WHERE role = ? AND builtin = 1 ORDER BY version LIMIT 1", (prompt["role"],)).fetchone()
            if builtin:
                self.connection.execute("UPDATE prompts SET active = 1, updated_at = ? WHERE id = ?", (now(), builtin["id"]))
        self.connection.commit()
        return {"id": prompt_id, "deleted": True}

    def resolve_prompts(self, task: dict) -> list[dict]:
        overrides = task.get("prompt_overrides") or {}
        resolved: list[dict] = []
        for role in ("query_planner", "relevance_screener", "literature_summarizer", "evidence_reviewer"):
            selected = self.get_prompt(overrides[role]) if role in overrides else None
            if not selected or selected["role"] != role:
                selected = self.connection.execute("SELECT * FROM prompts WHERE role = ? AND active = 1 LIMIT 1", (role,)).fetchone()
                selected = {**dict(selected), "builtin": bool(selected["builtin"]), "active": bool(selected["active"])} if selected else None
            if not selected:
                raise RuntimeError(f"Missing prompt for role: {role}")
            resolved.append(selected)
        return resolved

    def close(self) -> None:
        self.connection.close()
