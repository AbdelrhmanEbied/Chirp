"""Initial user schema: profiles, username history, processed events.

Revision ID: 0001
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        # Same value as the auth service's account id. No foreign key: that
        # row lives in another service's database.
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("username", sa.String(20), nullable=False),
        sa.Column("display_name", sa.String(50), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("location", sa.String(100), nullable=True),
        sa.Column("website", sa.String(200), nullable=True),
        sa.Column("avatar_media_id", sa.String(26), nullable=True),
        sa.Column("banner_media_id", sa.String(26), nullable=True),
        sa.Column("username_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("followers_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("following_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("posts_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("followers_count >= 0", name="ck_user_profiles_followers_non_negative"),
        sa.CheckConstraint("following_count >= 0", name="ck_user_profiles_following_non_negative"),
        sa.CheckConstraint("posts_count >= 0", name="ck_user_profiles_posts_non_negative"),
    )
    op.create_index("ix_user_profiles_username", "user_profiles", ["username"], unique=True)
    op.create_index("ix_user_profiles_username_active", "user_profiles", ["username", "deleted_at"])
    op.create_index("ix_user_profiles_display_name", "user_profiles", ["display_name"])
    op.create_index("ix_user_profiles_created_at", "user_profiles", ["created_at"])
    op.create_index("ix_user_profiles_deleted_at", "user_profiles", ["deleted_at"])

    op.create_table(
        "username_history",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("user_id", sa.String(26), nullable=False),
        sa.Column("username", sa.String(20), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_username_history_user_id", "username_history", ["user_id"])
    op.create_index("ix_username_history_username", "username_history", ["username"])
    op.create_index("ix_username_history_created_at", "username_history", ["created_at"])

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
    op.drop_table("username_history")
    op.drop_table("user_profiles")
