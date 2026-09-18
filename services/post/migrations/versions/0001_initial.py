
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "posts",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("author_id", sa.String(26), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("reply_to_id", sa.String(26), nullable=True),
        sa.Column("quote_of_id", sa.String(26), nullable=True),
        sa.Column("media_ids", sa.Text(), nullable=True),
        sa.Column("likes_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reposts_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("replies_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("quotes_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_posts_author_id", "posts", ["author_id"])
    op.create_index("ix_posts_author_created", "posts", ["author_id", "created_at"])
    op.create_index("ix_posts_reply_to_id", "posts", ["reply_to_id"])
    op.create_index("ix_posts_reply_to", "posts", ["reply_to_id"])
    op.create_index("ix_posts_created_at", "posts", ["created_at"])
    op.create_index("ix_posts_deleted_at", "posts", ["deleted_at"])

    op.create_table(
        "likes",
        sa.Column("user_id", sa.String(26), primary_key=True),
        sa.Column("post_id", sa.String(26), primary_key=True),
        sa.Column("post_author_id", sa.String(26), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_likes_post", "likes", ["post_id"])

    op.create_table(
        "reposts",
        sa.Column("user_id", sa.String(26), primary_key=True),
        sa.Column("post_id", sa.String(26), primary_key=True),
        sa.Column("post_author_id", sa.String(26), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "bookmarks",
        sa.Column("user_id", sa.String(26), primary_key=True),
        sa.Column("post_id", sa.String(26), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bookmarks_user_created", "bookmarks", ["user_id", "created_at"])

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
    op.drop_table("bookmarks")
    op.drop_table("reposts")
    op.drop_table("likes")
    op.drop_table("posts")
