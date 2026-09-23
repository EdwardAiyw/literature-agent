"""V2 Jev decision, cache and request-budget foundation."""
from alembic import op
import sqlalchemy as sa

revision = "20260922_0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind(); inspector = sa.inspect(bind); tables = set(inspector.get_table_names())
    if "decision_calls" not in tables:
        op.create_table("decision_calls", sa.Column("id", sa.String, primary_key=True), sa.Column("run_id", sa.String, nullable=False),
            sa.Column("stage", sa.String, nullable=False), sa.Column("subject_id", sa.String, nullable=False, server_default=""),
            sa.Column("mode", sa.String, nullable=False), sa.Column("status", sa.String, nullable=False),
            sa.Column("requested_model", sa.String, nullable=False), sa.Column("resolved_model", sa.String, nullable=False, server_default=""),
            sa.Column("schema_version", sa.String, nullable=False), sa.Column("state_hash", sa.String, nullable=False),
            sa.Column("answers", sa.Text, nullable=False, server_default="{}"), sa.Column("outcome", sa.Text, nullable=False, server_default="{}"),
            sa.Column("confidence", sa.Float, nullable=False, server_default="0"), sa.Column("latency_ms", sa.Float, nullable=False, server_default="0"),
            sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"), sa.Column("cached", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("fallback_used", sa.Boolean, nullable=False, server_default="0"), sa.Column("error", sa.Text, nullable=False, server_default=""),
            sa.Column("created_at", sa.String, nullable=False))
    if "decision_cache" not in tables:
        op.create_table("decision_cache", sa.Column("cache_key", sa.String, primary_key=True), sa.Column("model", sa.String, nullable=False),
            sa.Column("schema_version", sa.String, nullable=False), sa.Column("payload", sa.Text, nullable=False),
            sa.Column("expires_at", sa.String, nullable=False), sa.Column("created_at", sa.String, nullable=False))
    if "source_cache" not in tables:
        op.create_table("source_cache", sa.Column("cache_key", sa.String, primary_key=True), sa.Column("provider", sa.String, nullable=False),
            sa.Column("payload", sa.Text, nullable=False), sa.Column("expires_at", sa.String, nullable=False), sa.Column("created_at", sa.String, nullable=False))
    if "source_usage" not in tables:
        op.create_table("source_usage", sa.Column("provider", sa.String, primary_key=True), sa.Column("usage_date", sa.String, primary_key=True),
            sa.Column("requests", sa.Integer, nullable=False, server_default="0"))
    if "runs" in tables:
        columns = {c["name"] for c in inspector.get_columns("runs")}
        with op.batch_alter_table("runs") as batch:
            if "trigger_kind" not in columns: batch.add_column(sa.Column("trigger_kind", sa.String, nullable=False, server_default="manual"))
            if "subscription_id" not in columns: batch.add_column(sa.Column("subscription_id", sa.String, nullable=True))

def downgrade():
    for table in ("source_usage", "source_cache", "decision_cache", "decision_calls"):
        op.drop_table(table)
