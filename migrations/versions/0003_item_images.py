"""Multiple immutable images per catalog item."""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"


def upgrade():
    op.add_column(
        "items", sa.Column("image_ids", sa.JSON(), nullable=False, server_default="[]")
    )
    op.execute(
        "UPDATE items SET image_ids=json_array(image_id) WHERE image_id IS NOT NULL"
    )


def downgrade():
    raise RuntimeError(
        "Destruktive Rückmigration gesperrt; geprüften Restore verwenden."
    )
