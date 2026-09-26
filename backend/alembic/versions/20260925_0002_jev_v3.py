"""Jev V3 provider, routing and probability audit fields."""
from alembic import op
import sqlalchemy as sa

revision = "20260925_0002"
down_revision = "20260922_0001"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    existing = _columns("decision_calls")
    additions = [
        ("provider", sa.Column("provider", sa.String, nullable=False, server_default="typesafe_cloud")),
        ("probability_kind", sa.Column("probability_kind", sa.String, nullable=False, server_default="unknown")),
        ("routing", sa.Column("routing", sa.String, nullable=False, server_default="fallback")),
        ("baseline_outcome", sa.Column("baseline_outcome", sa.Text, nullable=False, server_default="{}")),
        ("final_outcome", sa.Column("final_outcome", sa.Text, nullable=False, server_default="{}")),
        ("probabilities", sa.Column("probabilities", sa.Text, nullable=False, server_default="{}")),
        ("attempt_count", sa.Column("attempt_count", sa.Integer, nullable=False, server_default="1")),
        ("validation_error", sa.Column("validation_error", sa.Text, nullable=False, server_default="")),
    ]
    with op.batch_alter_table("decision_calls") as batch:
        for name, column in additions:
            if name not in existing:
                batch.add_column(column)


def downgrade():
    existing = _columns("decision_calls")
    with op.batch_alter_table("decision_calls") as batch:
        for name in ("validation_error", "attempt_count", "probabilities", "final_outcome", "baseline_outcome", "routing", "probability_kind", "provider"):
            if name in existing:
                batch.drop_column(name)
