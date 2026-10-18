"""Durable delivered-paper snapshots independent of run retention."""
from alembic import op
import sqlalchemy as sa

revision = "20261018_0006"
down_revision = "20261017_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "digest_history",
        sa.Column("delivery_id", sa.String, primary_key=True),
        sa.Column("subscription_id", sa.String, nullable=False, index=True),
        sa.Column("run_id", sa.String),
        sa.Column("papers", sa.Text, nullable=False),
        sa.Column("sent_at", sa.String, nullable=False),
        sa.Column("missing_papers", sa.Integer, nullable=False, server_default="0"),
    )
    connection = op.get_bind()
    import json
    for row in connection.execute(sa.text("SELECT * FROM deliveries WHERE kind='digest' AND status='sent'")).mappings():
        papers = [json.loads(p[0]) for p in connection.execute(sa.text("SELECT payload FROM papers WHERE run_id=:run"), {"run": row["run_id"]})]
        expected = connection.execute(sa.text("SELECT paper_count FROM runs WHERE id=:run"), {"run": row["run_id"]}).scalar()
        connection.execute(sa.text("INSERT INTO digest_history VALUES (:delivery, :subscription, :run, :papers, :sent, :missing)"),
            {"delivery": row["id"], "subscription": row["subscription_id"], "run": row["run_id"],
             "papers": json.dumps(papers, ensure_ascii=False), "sent": row["sent_at"] or row["created_at"],
             "missing": max(0, expected - len(papers)) if expected is not None else 1})


def downgrade():
    op.drop_table("digest_history")
