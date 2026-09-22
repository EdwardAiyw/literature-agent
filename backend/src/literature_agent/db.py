from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
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
            id TEXT PRIMARY KEY, role TEXT NOT NULL, version TEXT NOT NULL, body TEXT NOT NULL,
            builtin INTEGER NOT NULL DEFAULT 1, active INTEGER NOT NULL DEFAULT 0,
            parent_id TEXT, created_at TEXT, updated_at TEXT
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
        """)
        self._ensure_column("runs", "progress", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("runs", "total_steps", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("prompts", "active", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("prompts", "parent_id", "TEXT")
        self._ensure_column("prompts", "created_at", "TEXT")
        self._ensure_column("prompts", "updated_at", "TEXT")
        self.connection.execute("UPDATE prompts SET created_at = COALESCE(created_at, ?), updated_at = COALESCE(updated_at, ?)", (now(), now()))
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
        payload = json.loads(row["payload"])
        payload.setdefault("origin", "user")
        return {**payload, "id": row["id"], "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def list_tasks(self) -> list[dict]:
        rows = self.connection.execute("SELECT id FROM tasks ORDER BY created_at DESC").fetchall()
        return [self.get_task(row["id"]) for row in rows]

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

    def update_task(self, task_id: str, payload: dict) -> dict | None:
        timestamp = now()
        result = self.connection.execute("UPDATE tasks SET payload = ?, updated_at = ? WHERE id = ?", (json.dumps(payload, ensure_ascii=False), timestamp, task_id))
        self.connection.commit()
        return self.get_task(task_id) if result.rowcount else None

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
        try:
            self.connection.execute("BEGIN")
            self.connection.execute("DELETE FROM deliveries WHERE subscription_id = ?", (subscription_id,))
            self.connection.execute("DELETE FROM subscriptions WHERE id = ?", (subscription_id,))
            if not shared_task:
                self._delete_task_data(task_id)
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

    def create_run(self, task_id: str, total_steps: int) -> dict:
        run_id = str(uuid4())
        self.connection.execute(
            "INSERT INTO runs(id, task_id, status, total_steps, started_at) VALUES (?, ?, 'queued', ?, ?)",
            (run_id, task_id, total_steps, now()),
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
            timestamp = now()
            self.connection.execute(
                """
                INSERT INTO prompts(id, role, version, body, builtin, active, parent_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, 0, NULL, ?, ?)
                ON CONFLICT(id) DO UPDATE SET role=excluded.role, version=excluded.version, body=excluded.body, builtin=1, updated_at=excluded.updated_at
                """,
                (prompt["id"], prompt["role"], prompt["version"], prompt["body"], timestamp, timestamp),
            )
            active = self.connection.execute("SELECT 1 FROM prompts WHERE role = ? AND active = 1 LIMIT 1", (prompt["role"],)).fetchone()
            if not active:
                self.connection.execute("UPDATE prompts SET active = 1, updated_at = ? WHERE id = ?", (timestamp, prompt["id"]))
        self.connection.commit()

    def list_prompts(self) -> list[dict]:
        rows = self.connection.execute("SELECT * FROM prompts ORDER BY role, created_at, version").fetchall()
        return [{**dict(row), "builtin": bool(row["builtin"]), "active": bool(row["active"])} for row in rows]

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
