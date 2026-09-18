
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "follows",
        sa.Column("follower_id", sa.String(26), primary_key=True),
        sa.Column("followee_id", sa.String(26), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_follows_followee_id", "follows", ["followee_id"])
    op.create_index("ix_follows_created_at", "follows", ["created_at"])

    op.create_table(
        "blocks",
        sa.Column("blocker_id", sa.String(26), primary_key=True),
        sa.Column("blocked_id", sa.String(26), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_blocks_blocked_id", "blocks", ["blocked_id"])
    op.create_index("ix_blocks_created_at", "blocks", ["created_at"])

    op.create_table(
        "mutes",
        sa.Column("user_id", sa.String(26), primary_key=True),
        sa.Column("muted_id", sa.String(26), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mutes_muted_id", "mutes", ["muted_id"])
    op.create_index("ix_mutes_created_at", "mutes", ["created_at"])

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
    op.drop_table("mutes")
    op.drop_table("blocks")
    op.drop_table("follows")
