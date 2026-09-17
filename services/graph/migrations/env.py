from chirp_common.db.migrations import run_migrations
from app import models  # noqa: F401 - imported so tables register on the metadata
from chirp_common.db.base import Base

run_migrations(Base.metadata)
