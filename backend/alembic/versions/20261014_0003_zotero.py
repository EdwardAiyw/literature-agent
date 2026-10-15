"""Persist per-paper, per-destination Zotero import results."""
from alembic import op
import sqlalchemy as sa

revision = "20261014_0003"
down_revision = "20260925_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "zotero_imports",
        sa.Column("paper_id", sa.String, primary_key=True),
        sa.Column("destination", sa.String, primary_key=True),
        sa.Column("payload", sa.Text, nullable=False),
        sa.Column("updated_at", sa.String, nullable=False),
    )


def downgrade():
    op.drop_table("zotero_imports")
