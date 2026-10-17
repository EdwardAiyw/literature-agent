"""User-imported journal impact factors with year and provenance."""
from alembic import op
import sqlalchemy as sa

revision = "20261017_0004"
down_revision = "20261014_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "journal_metrics",
        sa.Column("issn", sa.String, primary_key=True),
        sa.Column("year", sa.Integer, primary_key=True),
        sa.Column("payload", sa.Text, nullable=False),
        sa.Column("updated_at", sa.String, nullable=False),
    )


def downgrade():
    op.drop_table("journal_metrics")
