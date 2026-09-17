from app import models  # noqa: F401
from chirp_common.db.base import Base
from chirp_common.db.migrations import run_migrations

run_migrations(Base.metadata)
