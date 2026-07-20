"""initial_schema

Revision ID: 4bb73fc2e250
Revises:
Create Date: 2026-07-06 04:36:31.778948

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4bb73fc2e250"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "families",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=True, comment="创建者 user.id,逻辑引用,不建外键以允许清理"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "privileges",
        sa.Column("level_required", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=256), nullable=False),
        sa.Column("icon", sa.String(length=16), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_privileges_level_required"), "privileges", ["level_required"], unique=False)

    op.create_table(
        "theme_styles",
        sa.Column("family_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("scene_prompt", sa.Text(), nullable=False),
        sa.Column("description", sa.String(length=256), nullable=False),
        sa.Column("tokens", sa.JSON(), nullable=False),
        sa.Column("css_vars", sa.JSON(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_theme_styles_family_id"), "theme_styles", ["family_id"], unique=False)
    op.create_index(op.f("ix_theme_styles_is_active"), "theme_styles", ["is_active"], unique=False)
    op.create_index(op.f("ix_theme_styles_is_system"), "theme_styles", ["is_system"], unique=False)

    op.create_table(
        "time_configs",
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("default_daily_allowance", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_time_configs_family_id"), "time_configs", ["family_id"], unique=True)

    op.create_table(
        "users",
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, comment="GUILD_MASTER | ADVENTURER"),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("avatar", sa.String(length=16), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("xp", sa.Integer(), nullable=False),
        sa.Column("time_coins", sa.Integer(), nullable=False),
        sa.Column("daily_abandon_count", sa.Integer(), nullable=False),
        sa.Column("last_login_date", sa.Date(), nullable=True),
        sa.Column("privileges_unlocked", sa.String(length=255), nullable=False, comment='JSON 字符串,如 "[1,2,5]"'),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_family_id"), "users", ["family_id"], unique=False)

    op.create_table(
        "family_invites",
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("used_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["used_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_family_invites_code"), "family_invites", ["code"], unique=True)
    op.create_index(op.f("ix_family_invites_family_id"), "family_invites", ["family_id"], unique=False)

    op.create_table(
        "seasons",
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("theme_id", sa.String(length=32), nullable=False),
        sa.Column("narrative_context", sa.Text(), nullable=False),
        sa.Column("start_date", sa.DateTime(), nullable=False),
        sa.Column("end_date", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_seasons_family_id"), "seasons", ["family_id"], unique=False)
    op.create_index(op.f("ix_seasons_is_active"), "seasons", ["is_active"], unique=False)

    op.create_table(
        "time_config_exceptions",
        sa.Column("time_config_id", sa.String(length=36), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False, comment="0=Sun, 6=Sat"),
        sa.Column("coin_amount", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["time_config_id"], ["time_configs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("time_config_id", "day_of_week", name="uq_tce_config_day"),
    )
    op.create_index(op.f("ix_time_config_exceptions_time_config_id"), "time_config_exceptions", ["time_config_id"], unique=False)

    op.create_table(
        "uploads",
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("uploader_id", sa.String(length=36), nullable=True),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("bucket", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("etag", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploader_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index(op.f("ix_uploads_family_id"), "uploads", ["family_id"], unique=False)
    op.create_index(op.f("ix_uploads_purpose"), "uploads", ["purpose"], unique=False)
    op.create_index(op.f("ix_uploads_uploader_id"), "uploads", ["uploader_id"], unique=False)

    op.create_table(
        "wechat_accounts",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("openid", sa.String(length=64), nullable=False),
        sa.Column("unionid", sa.String(length=64), nullable=True),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("nickname", sa.String(length=64), nullable=True),
        sa.Column("avatar_url", sa.String(length=512), nullable=True),
        sa.Column("access_token", sa.String(length=512), nullable=True),
        sa.Column("refresh_token", sa.String(length=512), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_wechat_accounts_openid"), "wechat_accounts", ["openid"], unique=True)
    op.create_index(op.f("ix_wechat_accounts_unionid"), "wechat_accounts", ["unionid"], unique=False)
    op.create_index(op.f("ix_wechat_accounts_user_id"), "wechat_accounts", ["user_id"], unique=False)

    op.create_table(
        "tasks",
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("season_id", sa.String(length=36), nullable=False),
        sa.Column("creator_id", sa.String(length=36), nullable=True),
        sa.Column("target_user_id", sa.String(length=36), nullable=True),
        sa.Column("assignee_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("lore_snippet", sa.Text(), nullable=True),
        sa.Column("xp_reward", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("deadline", sa.DateTime(), nullable=True),
        sa.Column("required_start_time", sa.Time(), nullable=True),
        sa.Column("proof_object_key", sa.String(length=512), nullable=True, comment="对象存储 key,完整 URL 通过 storage client 生成"),
        sa.Column("rating", sa.Integer(), nullable=True, comment="1-5 星"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("reminder_message", sa.String(length=256), nullable=True),
        sa.Column("reminder_minutes_before", sa.Integer(), nullable=False),
        sa.Column("time_deposit", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["creator_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tasks_assignee_id"), "tasks", ["assignee_id"], unique=False)
    op.create_index(op.f("ix_tasks_family_id"), "tasks", ["family_id"], unique=False)
    op.create_index(op.f("ix_tasks_season_id"), "tasks", ["season_id"], unique=False)
    op.create_index(op.f("ix_tasks_status"), "tasks", ["status"], unique=False)
    op.create_index(op.f("ix_tasks_target_user_id"), "tasks", ["target_user_id"], unique=False)

    op.create_table(
        "coin_transactions",
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False, comment="正数表示增加,负数表示扣减"),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_coin_transactions_created_at"), "coin_transactions", ["created_at"], unique=False)
    op.create_index(op.f("ix_coin_transactions_family_id"), "coin_transactions", ["family_id"], unique=False)
    op.create_index(op.f("ix_coin_transactions_task_id"), "coin_transactions", ["task_id"], unique=False)
    op.create_index(op.f("ix_coin_transactions_type"), "coin_transactions", ["type"], unique=False)
    op.create_index(op.f("ix_coin_transactions_user_id"), "coin_transactions", ["user_id"], unique=False)

    op.create_table(
        "redemption_records",
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("privilege_id", sa.String(length=36), nullable=True),
        sa.Column("privilege_title", sa.String(length=64), nullable=False),
        sa.Column("cost", sa.String(length=32), nullable=True),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["privilege_id"], ["privileges.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_redemption_records_family_id"), "redemption_records", ["family_id"], unique=False)
    op.create_index(op.f("ix_redemption_records_privilege_id"), "redemption_records", ["privilege_id"], unique=False)
    op.create_index(op.f("ix_redemption_records_user_id"), "redemption_records", ["user_id"], unique=False)

    op.create_table(
        "user_privileges",
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("privilege_id", sa.String(length=36), nullable=False),
        sa.Column("unlocked_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["family_id"], ["families.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["privilege_id"], ["privileges.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "privilege_id", name="uq_user_privilege_user_privilege"),
    )
    op.create_index(op.f("ix_user_privileges_family_id"), "user_privileges", ["family_id"], unique=False)
    op.create_index(op.f("ix_user_privileges_privilege_id"), "user_privileges", ["privilege_id"], unique=False)
    op.create_index(op.f("ix_user_privileges_unlocked_at"), "user_privileges", ["unlocked_at"], unique=False)
    op.create_index(op.f("ix_user_privileges_user_id"), "user_privileges", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_privileges_user_id"), table_name="user_privileges")
    op.drop_index(op.f("ix_user_privileges_unlocked_at"), table_name="user_privileges")
    op.drop_index(op.f("ix_user_privileges_privilege_id"), table_name="user_privileges")
    op.drop_index(op.f("ix_user_privileges_family_id"), table_name="user_privileges")
    op.drop_table("user_privileges")

    op.drop_index(op.f("ix_redemption_records_user_id"), table_name="redemption_records")
    op.drop_index(op.f("ix_redemption_records_privilege_id"), table_name="redemption_records")
    op.drop_index(op.f("ix_redemption_records_family_id"), table_name="redemption_records")
    op.drop_table("redemption_records")

    op.drop_index(op.f("ix_coin_transactions_user_id"), table_name="coin_transactions")
    op.drop_index(op.f("ix_coin_transactions_type"), table_name="coin_transactions")
    op.drop_index(op.f("ix_coin_transactions_task_id"), table_name="coin_transactions")
    op.drop_index(op.f("ix_coin_transactions_family_id"), table_name="coin_transactions")
    op.drop_index(op.f("ix_coin_transactions_created_at"), table_name="coin_transactions")
    op.drop_table("coin_transactions")

    op.drop_index(op.f("ix_tasks_target_user_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_status"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_season_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_family_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_assignee_id"), table_name="tasks")
    op.drop_table("tasks")

    op.drop_index(op.f("ix_wechat_accounts_user_id"), table_name="wechat_accounts")
    op.drop_index(op.f("ix_wechat_accounts_unionid"), table_name="wechat_accounts")
    op.drop_index(op.f("ix_wechat_accounts_openid"), table_name="wechat_accounts")
    op.drop_table("wechat_accounts")

    op.drop_index(op.f("ix_uploads_uploader_id"), table_name="uploads")
    op.drop_index(op.f("ix_uploads_purpose"), table_name="uploads")
    op.drop_index(op.f("ix_uploads_family_id"), table_name="uploads")
    op.drop_table("uploads")

    op.drop_index(op.f("ix_time_config_exceptions_time_config_id"), table_name="time_config_exceptions")
    op.drop_table("time_config_exceptions")

    op.drop_index(op.f("ix_seasons_is_active"), table_name="seasons")
    op.drop_index(op.f("ix_seasons_family_id"), table_name="seasons")
    op.drop_table("seasons")

    op.drop_index(op.f("ix_family_invites_family_id"), table_name="family_invites")
    op.drop_index(op.f("ix_family_invites_code"), table_name="family_invites")
    op.drop_table("family_invites")

    op.drop_index(op.f("ix_users_family_id"), table_name="users")
    op.drop_table("users")

    op.drop_index(op.f("ix_time_configs_family_id"), table_name="time_configs")
    op.drop_table("time_configs")

    op.drop_index(op.f("ix_theme_styles_is_system"), table_name="theme_styles")
    op.drop_index(op.f("ix_theme_styles_is_active"), table_name="theme_styles")
    op.drop_index(op.f("ix_theme_styles_family_id"), table_name="theme_styles")
    op.drop_table("theme_styles")

    op.drop_index(op.f("ix_privileges_level_required"), table_name="privileges")
    op.drop_table("privileges")

    op.drop_table("families")
