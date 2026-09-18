
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feed_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(26), nullable=False),
        sa.Column("post_id", sa.String(26), nullable=False),
        sa.Column("author_id", sa.String(26), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("likes_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reposts_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("replies_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("inserted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_feed_entries_user_id", "feed_entries", ["user_id"])
    op.create_index("ix_feed_entries_post_id", "feed_entries", ["post_id"])
    op.create_index("ix_feed_entries_author_id", "feed_entries", ["author_id"])
    op.create_index("ix_feed_entries_user_created", "feed_entries", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("feed_entries")
