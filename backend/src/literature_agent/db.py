from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._lock = RLock()
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY, task_id TEXT NOT NULL, status TEXT NOT NULL, current_node TEXT NOT NULL DEFAULT '',
            paper_count INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '', progress INTEGER NOT NULL DEFAULT 0,
            total_steps INTEGER NOT NULL DEFAULT 0, started_at TEXT, finished_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_runs_task_started ON runs(task_id, started_at DESC);
        CREATE TABLE IF NOT EXISTS papers (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, canonical_id TEXT NOT NULL, payload TEXT NOT NULL,
            review TEXT NOT NULL DEFAULT 'unreviewed', UNIQUE(run_id, canonical_id)
        );
        CREATE TABLE IF NOT EXISTS prompts (
            id TEXT PRIMARY KEY, role TEXT NOT NULL, version TEXT NOT NULL, body TEXT NOT NULL, builtin INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS run_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, node TEXT NOT NULL, status TEXT NOT NULL,
            message TEXT NOT NULL, artifact_type TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_run_events_run_id ON run_events(run_id, id);
        CREATE TABLE IF NOT EXISTS run_artifacts (
            run_id TEXT NOT NULL, node TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY(run_id, node)
        );
        CREATE TABLE IF NOT EXISTS subscriptions (
            id TEXT PRIMARY KEY, task_id TEXT NOT NULL, payload TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_subscriptions_enabled ON subscriptions(enabled);
        CREATE TABLE IF NOT EXISTS deliveries (
            id TEXT PRIMARY KEY, subscription_id TEXT NOT NULL, run_id TEXT, kind TEXT NOT NULL,
            status TEXT NOT NULL, recipient TEXT NOT NULL, subject TEXT NOT NULL, error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, sent_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_deliveries_subscription ON deliveries(subscription_id, created_at);
        CREATE TABLE IF NOT EXISTS decision_calls (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, stage TEXT NOT NULL, subject_id TEXT NOT NULL DEFAULT '',
            mode TEXT NOT NULL, status TEXT NOT NULL, requested_model TEXT NOT NULL, resolved_model TEXT NOT NULL DEFAULT '',
            schema_version TEXT NOT NULL, state_hash TEXT NOT NULL, answers TEXT NOT NULL DEFAULT '{}',
            outcome TEXT NOT NULL DEFAULT '{}', confidence REAL NOT NULL DEFAULT 0, latency_ms REAL NOT NULL DEFAULT 0,
            input_tokens INTEGER NOT NULL DEFAULT 0, cached INTEGER NOT NULL DEFAULT 0,
            fallback_used INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_decision_calls_run ON decision_calls(run_id, created_at);
        CREATE TABLE IF NOT EXISTS decision_cache (
            cache_key TEXT PRIMARY KEY, model TEXT NOT NULL, schema_version TEXT NOT NULL,
            payload TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS source_cache (
            cache_key TEXT PRIMARY KEY, provider TEXT NOT NULL, payload TEXT NOT NULL,
            expires_at TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS source_usage (
            provider TEXT NOT NULL, usage_date TEXT NOT NULL, requests INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(provider, usage_date)
        );
        """)
        self._ensure_column("runs", "progress", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("runs", "total_steps", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("runs", "trigger_kind", "TEXT NOT NULL DEFAULT 'manual'")
        self._ensure_column("runs", "subscription_id", "TEXT")
        self.connection.commit()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in self.connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            self.connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

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
        for prompt in prompts:
            self.connection.execute(
                """
                INSERT INTO prompts(id, role, version, body, builtin) VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(id) DO UPDATE SET role=excluded.role, version=excluded.version, body=excluded.body, builtin=1
                """,
                (prompt["id"], prompt["role"], prompt["version"], prompt["body"]),
            )
        self.connection.commit()

    def list_prompts(self) -> list[dict]:
        rows = self.connection.execute("SELECT * FROM prompts ORDER BY role, version").fetchall()
        return [{**dict(row), "builtin": bool(row["builtin"])} for row in rows]

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
            "fallback_used": int(bool(value.get("fallback_used"))), "error": value.get("error", ""),
            "created_at": value.get("created_at") or now(),
        }
        with self._lock:
            self.connection.execute(
                """INSERT INTO decision_calls VALUES (:id,:run_id,:stage,:subject_id,:mode,:status,:requested_model,
                :resolved_model,:schema_version,:state_hash,:answers,:outcome,:confidence,:latency_ms,:input_tokens,
                :cached,:fallback_used,:error,:created_at)""", row)
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

    def close(self) -> None:
        self.connection.close()
