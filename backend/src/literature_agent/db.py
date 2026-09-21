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
            paper_count INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '', started_at TEXT, finished_at TEXT
        );
        CREATE TABLE IF NOT EXISTS papers (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, canonical_id TEXT NOT NULL, payload TEXT NOT NULL,
            review TEXT NOT NULL DEFAULT 'unreviewed', UNIQUE(run_id, canonical_id)
        );
        CREATE TABLE IF NOT EXISTS prompts (
            id TEXT PRIMARY KEY, role TEXT NOT NULL, version TEXT NOT NULL, body TEXT NOT NULL, builtin INTEGER NOT NULL DEFAULT 1
        );
        """)
        self.connection.commit()

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

    def create_run(self, task_id: str) -> dict:
        run_id = str(uuid4())
        self.connection.execute("INSERT INTO runs(id, task_id, status) VALUES (?, ?, 'queued')", (run_id, task_id))
        self.connection.commit()
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict | None:
        row = self.connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        return dict(row)

    def update_run(self, run_id: str, **values) -> None:
        if not values:
            return
        assignments = ", ".join(f"{key} = ?" for key in values)
        self.connection.execute(f"UPDATE runs SET {assignments} WHERE id = ?", (*values.values(), run_id))
        self.connection.commit()

    def add_paper(self, run_id: str, canonical_id: str, payload: dict) -> None:
        self.connection.execute("INSERT OR IGNORE INTO papers(id, run_id, canonical_id, payload) VALUES (?, ?, ?, ?)", (str(uuid4()), run_id, canonical_id, json.dumps(payload, ensure_ascii=False)))
        self.connection.commit()

    def list_papers(self, run_id: str) -> list[dict]:
        rows = self.connection.execute("SELECT * FROM papers WHERE run_id = ? ORDER BY json_extract(payload, '$.relevance_score') DESC", (run_id,)).fetchall()
        return [{**json.loads(row["payload"]), "id": row["id"], "run_id": row["run_id"], "review": row["review"]} for row in rows]

    def review_paper(self, paper_id: str, review: str) -> bool:
        result = self.connection.execute("UPDATE papers SET review = ? WHERE id = ?", (review, paper_id))
        self.connection.commit()
        return result.rowcount > 0

    def close(self) -> None:
        self.connection.close()
