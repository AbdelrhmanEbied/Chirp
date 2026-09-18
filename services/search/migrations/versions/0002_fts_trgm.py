
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.add_column(
        "post_search",
        sa.Column(
            "text_search",
            sa.dialects.postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', text)", persisted=True),
        ),
    )

    op.create_index(
        "ix_post_search_text_search",
        "post_search",
        ["text_search"],
        postgresql_using="gin",
    )

    op.execute(
        "CREATE INDEX ix_post_search_text_trgm "
        "ON post_search USING GIN (text gin_trgm_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_post_search_text_trgm", postgresql_using="gin")
    op.drop_index("ix_post_search_text_search", postgresql_using="gin")
    op.drop_column("post_search", "text_search")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
