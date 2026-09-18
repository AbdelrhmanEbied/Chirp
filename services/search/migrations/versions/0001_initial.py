
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "post_search",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("post_id", sa.String(26), nullable=False),
        sa.Column("author_id", sa.String(26), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at_index", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_post_search_post_id", "post_search", ["post_id"], unique=True)
    op.create_index("ix_post_search_author", "post_search", ["author_id"])
    op.create_index("ix_post_search_created", "post_search", ["created_at_index"])

    op.create_table(
        "hashtag_usage",
        sa.Column("hashtag", sa.String(100), primary_key=True),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.String(26), primary_key=True),
        sa.Column("consumer", sa.String(128), primary_key=True),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_processed_events_processed_at", "processed_events", ["processed_at"])


def downgrade() -> None:
    op.drop_table("processed_events")
    op.drop_table("hashtag_usage")
    op.drop_table("post_search")
