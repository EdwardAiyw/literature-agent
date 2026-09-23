"""Core schema and V2 Jev decision, cache and request-budget foundation."""
from alembic import op
import sqlalchemy as sa

revision = "20260922_0001"
down_revision = None
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _create_table(name: str, *columns: sa.Column, constraints=()) -> None:
    if name not in _tables():
        op.create_table(name, *columns, *constraints)


def upgrade():
    _create_table("tasks",
        sa.Column("id", sa.String, primary_key=True), sa.Column("payload", sa.Text, nullable=False),
        sa.Column("created_at", sa.String, nullable=False), sa.Column("updated_at", sa.String, nullable=False))
    _create_table("runs",
        sa.Column("id", sa.String, primary_key=True), sa.Column("task_id", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False), sa.Column("current_node", sa.String, nullable=False, server_default=""),
        sa.Column("paper_count", sa.Integer, nullable=False, server_default="0"), sa.Column("error", sa.Text, nullable=False, server_default=""),
        sa.Column("progress", sa.Integer, nullable=False, server_default="0"), sa.Column("total_steps", sa.Integer, nullable=False, server_default="0"),
        sa.Column("started_at", sa.String), sa.Column("finished_at", sa.String),
        sa.Column("trigger_kind", sa.String, nullable=False, server_default="manual"), sa.Column("subscription_id", sa.String))
    _create_table("papers",
        sa.Column("id", sa.String, primary_key=True), sa.Column("run_id", sa.String, nullable=False),
        sa.Column("canonical_id", sa.String, nullable=False), sa.Column("payload", sa.Text, nullable=False),
        sa.Column("review", sa.String, nullable=False, server_default="unreviewed"),
        constraints=(sa.UniqueConstraint("run_id", "canonical_id", name="uq_papers_run_canonical"),))
    _create_table("prompts",
        sa.Column("id", sa.String, primary_key=True), sa.Column("role", sa.String, nullable=False),
        sa.Column("version", sa.String, nullable=False), sa.Column("body", sa.Text, nullable=False),
        sa.Column("builtin", sa.Integer, nullable=False, server_default="1"), sa.Column("active", sa.Integer, nullable=False, server_default="0"),
        sa.Column("parent_id", sa.String), sa.Column("created_at", sa.String, nullable=False, server_default=""),
        sa.Column("updated_at", sa.String, nullable=False, server_default=""))
    _create_table("run_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True), sa.Column("run_id", sa.String, nullable=False),
        sa.Column("node", sa.String, nullable=False), sa.Column("status", sa.String, nullable=False),
        sa.Column("message", sa.Text, nullable=False), sa.Column("artifact_type", sa.String, nullable=False, server_default=""),
        sa.Column("created_at", sa.String, nullable=False))
    _create_table("run_artifacts",
        sa.Column("run_id", sa.String, primary_key=True), sa.Column("node", sa.String, primary_key=True),
        sa.Column("payload", sa.Text, nullable=False), sa.Column("created_at", sa.String, nullable=False))
    _create_table("subscriptions",
        sa.Column("id", sa.String, primary_key=True), sa.Column("task_id", sa.String, nullable=False),
        sa.Column("payload", sa.Text, nullable=False), sa.Column("enabled", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.String, nullable=False), sa.Column("updated_at", sa.String, nullable=False))
    _create_table("deliveries",
        sa.Column("id", sa.String, primary_key=True), sa.Column("subscription_id", sa.String, nullable=False),
        sa.Column("run_id", sa.String), sa.Column("kind", sa.String, nullable=False), sa.Column("status", sa.String, nullable=False),
        sa.Column("recipient", sa.String, nullable=False), sa.Column("subject", sa.String, nullable=False),
        sa.Column("error", sa.Text, nullable=False, server_default=""), sa.Column("created_at", sa.String, nullable=False),
        sa.Column("sent_at", sa.String))

    # Existing V2 databases were initialized by Database.__init__ before Alembic owned upgrades.
    # Adopt their existing tables and columns, then let Alembic track this foundation revision.
    if "runs" in _tables():
        existing = _columns("runs")
        with op.batch_alter_table("runs") as batch:
            if "progress" not in existing: batch.add_column(sa.Column("progress", sa.Integer, nullable=False, server_default="0"))
            if "total_steps" not in existing: batch.add_column(sa.Column("total_steps", sa.Integer, nullable=False, server_default="0"))
            if "trigger_kind" not in existing: batch.add_column(sa.Column("trigger_kind", sa.String, nullable=False, server_default="manual"))
            if "subscription_id" not in existing: batch.add_column(sa.Column("subscription_id", sa.String))
    if "prompts" in _tables():
        existing = _columns("prompts")
        with op.batch_alter_table("prompts") as batch:
            if "active" not in existing: batch.add_column(sa.Column("active", sa.Integer, nullable=False, server_default="0"))
            if "parent_id" not in existing: batch.add_column(sa.Column("parent_id", sa.String))
            if "created_at" not in existing: batch.add_column(sa.Column("created_at", sa.String, nullable=False, server_default=""))
            if "updated_at" not in existing: batch.add_column(sa.Column("updated_at", sa.String, nullable=False, server_default=""))

    _create_table("decision_calls",
        sa.Column("id", sa.String, primary_key=True), sa.Column("run_id", sa.String, nullable=False),
        sa.Column("stage", sa.String, nullable=False), sa.Column("subject_id", sa.String, nullable=False, server_default=""),
        sa.Column("mode", sa.String, nullable=False), sa.Column("status", sa.String, nullable=False),
        sa.Column("requested_model", sa.String, nullable=False), sa.Column("resolved_model", sa.String, nullable=False, server_default=""),
        sa.Column("schema_version", sa.String, nullable=False), sa.Column("state_hash", sa.String, nullable=False),
        sa.Column("answers", sa.Text, nullable=False, server_default="{}"), sa.Column("outcome", sa.Text, nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0"), sa.Column("latency_ms", sa.Float, nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"), sa.Column("cached", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("fallback_used", sa.Boolean, nullable=False, server_default="0"), sa.Column("error", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.String, nullable=False))
    if "decision_calls" in _tables() and "fallback_reason" not in _columns("decision_calls"):
        with op.batch_alter_table("decision_calls") as batch:
            batch.add_column(sa.Column("fallback_reason", sa.String, nullable=False, server_default=""))
    _create_table("decision_cache",
        sa.Column("cache_key", sa.String, primary_key=True), sa.Column("model", sa.String, nullable=False),
        sa.Column("schema_version", sa.String, nullable=False), sa.Column("payload", sa.Text, nullable=False),
        sa.Column("expires_at", sa.String, nullable=False), sa.Column("created_at", sa.String, nullable=False))
    _create_table("source_cache",
        sa.Column("cache_key", sa.String, primary_key=True), sa.Column("provider", sa.String, nullable=False),
        sa.Column("payload", sa.Text, nullable=False), sa.Column("expires_at", sa.String, nullable=False),
        sa.Column("created_at", sa.String, nullable=False))
    _create_table("source_usage",
        sa.Column("provider", sa.String, primary_key=True), sa.Column("usage_date", sa.String, primary_key=True),
        sa.Column("requests", sa.Integer, nullable=False, server_default="0"))

    indexes = {
        "idx_runs_task_started": ("runs", ["task_id", "started_at"]),
        "idx_run_events_run_id": ("run_events", ["run_id", "id"]),
        "idx_subscriptions_enabled": ("subscriptions", ["enabled"]),
        "idx_deliveries_subscription": ("deliveries", ["subscription_id", "created_at"]),
        "idx_decision_calls_run": ("decision_calls", ["run_id", "created_at"]),
    }
    for name, (table, columns) in indexes.items():
        current = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}
        if name not in current:
            op.create_index(name, table, columns)


def downgrade():
    for name in ("idx_decision_calls_run", "idx_deliveries_subscription", "idx_subscriptions_enabled", "idx_run_events_run_id", "idx_runs_task_started"):
        op.drop_index(name, if_exists=True)
    for table in ("source_usage", "source_cache", "decision_cache", "decision_calls", "deliveries", "subscriptions", "run_artifacts", "run_events", "prompts", "papers", "runs", "tasks"):
        op.drop_table(table, if_exists=True)
