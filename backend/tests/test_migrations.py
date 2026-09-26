import sqlite3

import pytest

from literature_agent import db as db_module
from literature_agent.db import Database, upgrade_database


def test_empty_database_upgrade_is_repeatable_and_has_v2_schema(tmp_path):
    path = tmp_path / "fresh.db"
    upgrade_database(path)
    upgrade_database(path)
    database = Database(path)
    columns = {row["name"] for row in database.connection.execute("PRAGMA table_info(decision_calls)")}
    assert "fallback_reason" in columns
    assert {"provider", "probability_kind", "routing", "baseline_outcome", "final_outcome",
            "probabilities", "attempt_count", "validation_error"} <= columns
    assert database.connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "20260925_0002"
    database.close()


def test_legacy_core_tables_are_extended_without_losing_rows(tmp_path):
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE tasks (id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        INSERT INTO tasks VALUES ('task-1', '{\"name\":\"preserved\"}', 'created', 'updated');
        CREATE TABLE runs (
            id TEXT PRIMARY KEY, task_id TEXT NOT NULL, status TEXT NOT NULL,
            current_node TEXT NOT NULL DEFAULT '', paper_count INTEGER NOT NULL DEFAULT 0,
            error TEXT NOT NULL DEFAULT '', started_at TEXT, finished_at TEXT
        );
        INSERT INTO runs(id, task_id, status) VALUES ('run-1', 'task-1', 'completed');
        CREATE TABLE prompts (id TEXT PRIMARY KEY, role TEXT NOT NULL, version TEXT NOT NULL, body TEXT NOT NULL,
            builtin INTEGER NOT NULL DEFAULT 1);
        INSERT INTO prompts(id, role, version, body) VALUES ('p1', 'query_planner', 'v1', 'keep');
    """)
    connection.commit()
    connection.close()

    upgrade_database(path)
    database = Database(path)
    assert database.get_task("task-1")["name"] == "preserved"
    assert database.get_run("run-1")["id"] == "run-1"
    assert database.get_prompt("p1")["body"] == "keep"
    run_columns = {row["name"] for row in database.connection.execute("PRAGMA table_info(runs)")}
    assert {"progress", "total_steps", "trigger_kind", "subscription_id"} <= run_columns
    database.close()


def test_pre_alembic_v2_decision_audit_is_adopted_without_losing_rows(tmp_path):
    path = tmp_path / "pre-alembic-v2.db"
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE decision_calls (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, stage TEXT NOT NULL, subject_id TEXT NOT NULL DEFAULT '',
            mode TEXT NOT NULL, status TEXT NOT NULL, requested_model TEXT NOT NULL,
            resolved_model TEXT NOT NULL DEFAULT '', schema_version TEXT NOT NULL, state_hash TEXT NOT NULL,
            answers TEXT NOT NULL DEFAULT '{}', outcome TEXT NOT NULL DEFAULT '{}', confidence REAL NOT NULL DEFAULT 0,
            latency_ms REAL NOT NULL DEFAULT 0, input_tokens INTEGER NOT NULL DEFAULT 0, cached INTEGER NOT NULL DEFAULT 0,
            fallback_used INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        INSERT INTO decision_calls(id, run_id, stage, mode, status, requested_model, schema_version, state_hash, created_at)
        VALUES ('decision-1', 'run-1', 'relevance_screener', 'shadow', 'completed', 'jev-1.13.0', 'paper-screen.v1', 'hash', 'created');
    """)
    connection.commit()
    connection.close()

    upgrade_database(path)
    database = Database(path)
    audit = database.get_decision_call("decision-1")
    assert audit is not None
    assert audit["run_id"] == "run-1"
    assert audit["fallback_reason"] == ""
    database.close()


def test_database_does_not_open_connection_if_migration_fails(tmp_path, monkeypatch):
    def fail(_path):
        raise RuntimeError("migration failed")

    monkeypatch.setattr(db_module, "upgrade_database", fail)
    with pytest.raises(RuntimeError, match="migration failed"):
        Database(tmp_path / "blocked.db")
