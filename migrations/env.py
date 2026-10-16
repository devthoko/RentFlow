from alembic import context
from rentflow.config import Config
from rentflow.db import Base, make_engine
from rentflow import models

config = Config.environment()
with make_engine(config.data).connect() as conn:
    context.configure(
        connection=conn, target_metadata=Base.metadata, render_as_batch=True
    )
    with context.begin_transaction():
        context.run_migrations()
