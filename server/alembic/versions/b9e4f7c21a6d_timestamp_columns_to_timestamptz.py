"""convert timestamp columns to timestamptz (UTC+8 business timezone)

Revision ID: b9e4f7c21a6d
Revises: f3a1c9d02b7e
Create Date: 2026-10-10

时区规范落地(DEV-11):
- 全部 59 个 DateTime 列改为 timestamptz,统一存 UTC;
- 存量 naive 值按 UTC 语义解释(历史值均由 now()/utcnow() 写入,会话时区为 UTC);
- 业务展示与"自然日"边界在应用层锚定 Asia/Shanghai(UTC+8),见 app/common/timeutil.py。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b9e4f7c21a6d"
down_revision: Union[str, None] = "f3a1c9d02b7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("scn_hidden_quest", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_hidden_quest", "expires_at", type_=sa.DateTime(timezone=True), postgresql_using="expires_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_hidden_quest", "starts_at", type_=sa.DateTime(timezone=True), postgresql_using="starts_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_hidden_quest", "updated_at", type_=sa.DateTime(timezone=True), postgresql_using="updated_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_notification", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_notification", "read_at", type_=sa.DateTime(timezone=True), postgresql_using="read_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_notification", "sent_at", type_=sa.DateTime(timezone=True), postgresql_using="sent_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_onboarding_path", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_onboarding_path", "ends_at", type_=sa.DateTime(timezone=True), postgresql_using="ends_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_onboarding_path", "starts_at", type_=sa.DateTime(timezone=True), postgresql_using="starts_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_onboarding_path", "updated_at", type_=sa.DateTime(timezone=True), postgresql_using="updated_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_onboarding_step", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_onboarding_step", "updated_at", type_=sa.DateTime(timezone=True), postgresql_using="updated_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_privilege_template", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_privilege_template", "updated_at", type_=sa.DateTime(timezone=True), postgresql_using="updated_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_privilege_unlock", "last_used_at", type_=sa.DateTime(timezone=True), postgresql_using="last_used_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_privilege_unlock", "unlocked_at", type_=sa.DateTime(timezone=True), postgresql_using="unlocked_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_privilege_use", "used_at", type_=sa.DateTime(timezone=True), postgresql_using="used_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_season", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_season", "end_date", type_=sa.DateTime(timezone=True), postgresql_using="end_date AT TIME ZONE 'UTC'"),
    op.alter_column("scn_season", "start_date", type_=sa.DateTime(timezone=True), postgresql_using="start_date AT TIME ZONE 'UTC'"),
    op.alter_column("scn_season", "updated_at", type_=sa.DateTime(timezone=True), postgresql_using="updated_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_stats_daily", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_stats_daily", "updated_at", type_=sa.DateTime(timezone=True), postgresql_using="updated_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_task_instance", "completed_at", type_=sa.DateTime(timezone=True), postgresql_using="completed_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_task_instance", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_task_instance", "deadline", type_=sa.DateTime(timezone=True), postgresql_using="deadline AT TIME ZONE 'UTC'"),
    op.alter_column("scn_task_instance", "expire_at", type_=sa.DateTime(timezone=True), postgresql_using="expire_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_task_instance", "started_at", type_=sa.DateTime(timezone=True), postgresql_using="started_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_task_instance", "submitted_at", type_=sa.DateTime(timezone=True), postgresql_using="submitted_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_task_instance", "updated_at", type_=sa.DateTime(timezone=True), postgresql_using="updated_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_task_proof", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_task_proof", "deleted_at", type_=sa.DateTime(timezone=True), postgresql_using="deleted_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_task_template", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_task_template", "updated_at", type_=sa.DateTime(timezone=True), postgresql_using="updated_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_task_template_library", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_task_template_library", "updated_at", type_=sa.DateTime(timezone=True), postgresql_using="updated_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_theme_style", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_theme_style", "updated_at", type_=sa.DateTime(timezone=True), postgresql_using="updated_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_time_coin", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_time_coin", "updated_at", type_=sa.DateTime(timezone=True), postgresql_using="updated_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_time_coin_log", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_time_config", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_time_config", "updated_at", type_=sa.DateTime(timezone=True), postgresql_using="updated_at AT TIME ZONE 'UTC'"),
    op.alter_column("scn_trace", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("sys_account", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("sys_account", "updated_at", type_=sa.DateTime(timezone=True), postgresql_using="updated_at AT TIME ZONE 'UTC'"),
    op.alter_column("sys_channel_wechat", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("sys_channel_wechat", "expires_at", type_=sa.DateTime(timezone=True), postgresql_using="expires_at AT TIME ZONE 'UTC'"),
    op.alter_column("sys_child", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("sys_child", "updated_at", type_=sa.DateTime(timezone=True), postgresql_using="updated_at AT TIME ZONE 'UTC'"),
    op.alter_column("sys_family", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("sys_family", "updated_at", type_=sa.DateTime(timezone=True), postgresql_using="updated_at AT TIME ZONE 'UTC'"),
    op.alter_column("sys_invite", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("sys_invite", "expires_at", type_=sa.DateTime(timezone=True), postgresql_using="expires_at AT TIME ZONE 'UTC'"),
    op.alter_column("sys_invite", "used_at", type_=sa.DateTime(timezone=True), postgresql_using="used_at AT TIME ZONE 'UTC'"),
    op.alter_column("sys_parent", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),
    op.alter_column("sys_parent", "updated_at", type_=sa.DateTime(timezone=True), postgresql_using="updated_at AT TIME ZONE 'UTC'"),
    op.alter_column("sys_upload", "created_at", type_=sa.DateTime(timezone=True), postgresql_using="created_at AT TIME ZONE 'UTC'"),


def downgrade() -> None:
    op.alter_column("scn_hidden_quest", "created_at", type_=sa.DateTime()),
    op.alter_column("scn_hidden_quest", "expires_at", type_=sa.DateTime()),
    op.alter_column("scn_hidden_quest", "starts_at", type_=sa.DateTime()),
    op.alter_column("scn_hidden_quest", "updated_at", type_=sa.DateTime()),
    op.alter_column("scn_notification", "created_at", type_=sa.DateTime()),
    op.alter_column("scn_notification", "read_at", type_=sa.DateTime()),
    op.alter_column("scn_notification", "sent_at", type_=sa.DateTime()),
    op.alter_column("scn_onboarding_path", "created_at", type_=sa.DateTime()),
    op.alter_column("scn_onboarding_path", "ends_at", type_=sa.DateTime()),
    op.alter_column("scn_onboarding_path", "starts_at", type_=sa.DateTime()),
    op.alter_column("scn_onboarding_path", "updated_at", type_=sa.DateTime()),
    op.alter_column("scn_onboarding_step", "created_at", type_=sa.DateTime()),
    op.alter_column("scn_onboarding_step", "updated_at", type_=sa.DateTime()),
    op.alter_column("scn_privilege_template", "created_at", type_=sa.DateTime()),
    op.alter_column("scn_privilege_template", "updated_at", type_=sa.DateTime()),
    op.alter_column("scn_privilege_unlock", "last_used_at", type_=sa.DateTime()),
    op.alter_column("scn_privilege_unlock", "unlocked_at", type_=sa.DateTime()),
    op.alter_column("scn_privilege_use", "used_at", type_=sa.DateTime()),
    op.alter_column("scn_season", "created_at", type_=sa.DateTime()),
    op.alter_column("scn_season", "end_date", type_=sa.DateTime()),
    op.alter_column("scn_season", "start_date", type_=sa.DateTime()),
    op.alter_column("scn_season", "updated_at", type_=sa.DateTime()),
    op.alter_column("scn_stats_daily", "created_at", type_=sa.DateTime()),
    op.alter_column("scn_stats_daily", "updated_at", type_=sa.DateTime()),
    op.alter_column("scn_task_instance", "completed_at", type_=sa.DateTime()),
    op.alter_column("scn_task_instance", "created_at", type_=sa.DateTime()),
    op.alter_column("scn_task_instance", "deadline", type_=sa.DateTime()),
    op.alter_column("scn_task_instance", "expire_at", type_=sa.DateTime()),
    op.alter_column("scn_task_instance", "started_at", type_=sa.DateTime()),
    op.alter_column("scn_task_instance", "submitted_at", type_=sa.DateTime()),
    op.alter_column("scn_task_instance", "updated_at", type_=sa.DateTime()),
    op.alter_column("scn_task_proof", "created_at", type_=sa.DateTime()),
    op.alter_column("scn_task_proof", "deleted_at", type_=sa.DateTime()),
    op.alter_column("scn_task_template", "created_at", type_=sa.DateTime()),
    op.alter_column("scn_task_template", "updated_at", type_=sa.DateTime()),
    op.alter_column("scn_task_template_library", "created_at", type_=sa.DateTime()),
    op.alter_column("scn_task_template_library", "updated_at", type_=sa.DateTime()),
    op.alter_column("scn_theme_style", "created_at", type_=sa.DateTime()),
    op.alter_column("scn_theme_style", "updated_at", type_=sa.DateTime()),
    op.alter_column("scn_time_coin", "created_at", type_=sa.DateTime()),
    op.alter_column("scn_time_coin", "updated_at", type_=sa.DateTime()),
    op.alter_column("scn_time_coin_log", "created_at", type_=sa.DateTime()),
    op.alter_column("scn_time_config", "created_at", type_=sa.DateTime()),
    op.alter_column("scn_time_config", "updated_at", type_=sa.DateTime()),
    op.alter_column("scn_trace", "created_at", type_=sa.DateTime()),
    op.alter_column("sys_account", "created_at", type_=sa.DateTime()),
    op.alter_column("sys_account", "updated_at", type_=sa.DateTime()),
    op.alter_column("sys_channel_wechat", "created_at", type_=sa.DateTime()),
    op.alter_column("sys_channel_wechat", "expires_at", type_=sa.DateTime()),
    op.alter_column("sys_child", "created_at", type_=sa.DateTime()),
    op.alter_column("sys_child", "updated_at", type_=sa.DateTime()),
    op.alter_column("sys_family", "created_at", type_=sa.DateTime()),
    op.alter_column("sys_family", "updated_at", type_=sa.DateTime()),
    op.alter_column("sys_invite", "created_at", type_=sa.DateTime()),
    op.alter_column("sys_invite", "expires_at", type_=sa.DateTime()),
    op.alter_column("sys_invite", "used_at", type_=sa.DateTime()),
    op.alter_column("sys_parent", "created_at", type_=sa.DateTime()),
    op.alter_column("sys_parent", "updated_at", type_=sa.DateTime()),
    op.alter_column("sys_upload", "created_at", type_=sa.DateTime()),
