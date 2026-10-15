"""Initial RentFlow schema."""
from alembic import op
from rentflow.db import Base
from rentflow import models
revision = "0001"
down_revision = None
def upgrade():
    Base.metadata.create_all(op.get_bind())
    for table in ["documents", "evidence", "payments", "deposits", "audit", "assets"]:
        for action in ["UPDATE", "DELETE"]:
            op.execute(f"CREATE TRIGGER protect_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Archivierte Datensätze sind unveränderlich'); END")
def downgrade():
    raise RuntimeError("Destruktive Rückmigration gesperrt; geprüften Restore verwenden.")
