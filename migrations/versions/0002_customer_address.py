"""Structured billing address."""

from alembic import op
from sqlalchemy import inspect, Column, JSON, text

revision = "0002"
down_revision = "0001"


def upgrade():
    if "address_data" not in [
        c["name"] for c in inspect(op.get_bind()).get_columns("customers")
    ]:
        op.add_column(
            "customers",
            Column("address_data", JSON, nullable=False, server_default=text("'{}'")),
        )


def downgrade():
    raise RuntimeError("Destructive downgrade is disabled.")
