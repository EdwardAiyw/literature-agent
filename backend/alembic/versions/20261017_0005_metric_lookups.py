"""Durable public journal-metric lookup cache."""
from alembic import op
import sqlalchemy as sa

revision = "20261017_0005"
down_revision = "20261017_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "journal_metric_lookups",
        sa.Column("cache_key", sa.String, primary_key=True),
        sa.Column("payload", sa.Text, nullable=False),
        sa.Column("checked_at", sa.String, nullable=False),
        sa.Column("expires_at", sa.String, nullable=False),
    )


def downgrade():
    op.drop_table("journal_metric_lookups")
