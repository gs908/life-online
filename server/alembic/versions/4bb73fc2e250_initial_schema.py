"""initial_schema (static PostgreSQL DDL baseline)

Revision ID: 4bb73fc2e250
Revises:
Create Date: 2026-07-06 04:36:31.778948

DEV-13:初始迁移从动态的 ``Base.metadata.create_all()`` 固化为静态 PostgreSQL DDL。
动态版本在空库重放整条迁移链时会把 P1 场景表一并建出,导致下一个迁移
``d4a5b93011d5`` 重复建表报错;本文件是"初始状态"(即当前模型减去
d4a5b93011d5 / 8aa7c7e1f4d1 / f3a1c9d02b7e 引入的全部对象)的静态固化,
内容变更时请通过重放校验:
空库执行 ``alembic upgrade head`` 后用 ``scripts/diff_pg_schema.py`` 比对
最终 schema 与 ``Base.metadata`` 是否一致。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "4bb73fc2e250"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the initial sys_* / scn_* schema (static, pre-P1 state)."""
    op.create_table('sys_family',
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('owner_id', sa.String(length=36), nullable=True, comment='创建者 sys_account.id,逻辑引用,不建外键以允许清理'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_family'))
    )
    op.create_table('scn_season',
    sa.Column('family_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('theme_id', sa.String(length=32), nullable=False),
    sa.Column('narrative_context', sa.Text(), nullable=False),
    sa.Column('start_date', sa.DateTime(), nullable=False),
    sa.Column('end_date', sa.DateTime(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['family_id'], ['sys_family.id'], name=op.f('fk_scn_season_family_id_sys_family'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_scn_season'))
    )
    op.create_index(op.f('ix_scn_season_family_id'), 'scn_season', ['family_id'], unique=False)
    op.create_index(op.f('ix_scn_season_is_active'), 'scn_season', ['is_active'], unique=False)
    op.create_table('scn_time_config',
    sa.Column('family_id', sa.String(length=36), nullable=False),
    sa.Column('default_daily_allowance', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['family_id'], ['sys_family.id'], name=op.f('fk_scn_time_config_family_id_sys_family'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_scn_time_config'))
    )
    op.create_index(op.f('ix_scn_time_config_family_id'), 'scn_time_config', ['family_id'], unique=True)
    op.create_table('sys_account',
    sa.Column('family_id', sa.String(length=36), nullable=False),
    sa.Column('role', sa.String(length=32), nullable=False, comment='GUILD_MASTER | ADVENTURER'),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('avatar', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False, comment='active | disabled'),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['family_id'], ['sys_family.id'], name=op.f('fk_sys_account_family_id_sys_family'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_account'))
    )
    op.create_index(op.f('ix_sys_account_family_id'), 'sys_account', ['family_id'], unique=False)
    op.create_table('scn_privilege_template',
    sa.Column('family_id', sa.String(length=36), nullable=True),
    sa.Column('season_id', sa.String(length=36), nullable=True),
    sa.Column('level_required', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=64), nullable=False),
    sa.Column('description', sa.String(length=256), nullable=False),
    sa.Column('icon', sa.String(length=16), nullable=False),
    sa.Column('is_system', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['family_id'], ['sys_family.id'], name=op.f('fk_scn_privilege_template_family_id_sys_family'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['season_id'], ['scn_season.id'], name=op.f('fk_scn_privilege_template_season_id_scn_season'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_scn_privilege_template'))
    )
    op.create_index(op.f('ix_scn_privilege_template_family_id'), 'scn_privilege_template', ['family_id'], unique=False)
    op.create_index(op.f('ix_scn_privilege_template_is_active'), 'scn_privilege_template', ['is_active'], unique=False)
    op.create_index(op.f('ix_scn_privilege_template_is_system'), 'scn_privilege_template', ['is_system'], unique=False)
    op.create_index(op.f('ix_scn_privilege_template_level_required'), 'scn_privilege_template', ['level_required'], unique=False)
    op.create_index(op.f('ix_scn_privilege_template_season_id'), 'scn_privilege_template', ['season_id'], unique=False)
    op.create_table('scn_theme_style',
    sa.Column('family_id', sa.String(length=36), nullable=True),
    sa.Column('season_id', sa.String(length=36), nullable=True),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('scene_prompt', sa.Text(), nullable=False),
    sa.Column('description', sa.String(length=256), nullable=False),
    sa.Column('tokens', sa.JSON(), nullable=False),
    sa.Column('css_vars', sa.JSON(), nullable=False),
    sa.Column('is_system', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['family_id'], ['sys_family.id'], name=op.f('fk_scn_theme_style_family_id_sys_family'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['season_id'], ['scn_season.id'], name=op.f('fk_scn_theme_style_season_id_scn_season'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_scn_theme_style'))
    )
    op.create_index(op.f('ix_scn_theme_style_family_id'), 'scn_theme_style', ['family_id'], unique=False)
    op.create_index(op.f('ix_scn_theme_style_is_active'), 'scn_theme_style', ['is_active'], unique=False)
    op.create_index(op.f('ix_scn_theme_style_is_system'), 'scn_theme_style', ['is_system'], unique=False)
    op.create_index(op.f('ix_scn_theme_style_season_id'), 'scn_theme_style', ['season_id'], unique=False)
    op.create_table('scn_time_config_exception',
    sa.Column('time_config_id', sa.String(length=36), nullable=False),
    sa.Column('day_of_week', sa.Integer(), nullable=False, comment='0=Sun, 6=Sat'),
    sa.Column('coin_amount', sa.Integer(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['time_config_id'], ['scn_time_config.id'], name=op.f('fk_scn_time_config_exception_time_config_id_scn_time_config'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_scn_time_config_exception')),
    sa.UniqueConstraint('time_config_id', 'day_of_week', name='uq_scn_time_config_exception_day')
    )
    op.create_index(op.f('ix_scn_time_config_exception_time_config_id'), 'scn_time_config_exception', ['time_config_id'], unique=False)
    op.create_table('sys_channel_wechat',
    sa.Column('account_id', sa.String(length=36), nullable=False),
    sa.Column('openid', sa.String(length=64), nullable=False),
    sa.Column('unionid', sa.String(length=64), nullable=True),
    sa.Column('provider', sa.String(length=16), nullable=False),
    sa.Column('nickname', sa.String(length=64), nullable=True),
    sa.Column('avatar_url', sa.String(length=512), nullable=True),
    sa.Column('access_token', sa.String(length=512), nullable=True),
    sa.Column('refresh_token', sa.String(length=512), nullable=True),
    sa.Column('expires_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['sys_account.id'], name=op.f('fk_sys_channel_wechat_account_id_sys_account'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_channel_wechat'))
    )
    op.create_index(op.f('ix_sys_channel_wechat_account_id'), 'sys_channel_wechat', ['account_id'], unique=False)
    op.create_index(op.f('ix_sys_channel_wechat_openid'), 'sys_channel_wechat', ['openid'], unique=True)
    op.create_index(op.f('ix_sys_channel_wechat_unionid'), 'sys_channel_wechat', ['unionid'], unique=False)
    op.create_table('sys_child',
    sa.Column('account_id', sa.String(length=36), nullable=False),
    sa.Column('family_id', sa.String(length=36), nullable=False),
    sa.Column('display_name', sa.String(length=64), nullable=False),
    sa.Column('avatar', sa.String(length=16), nullable=False),
    sa.Column('level', sa.Integer(), nullable=False),
    sa.Column('xp', sa.Integer(), nullable=False),
    sa.Column('time_coin_balance', sa.Integer(), nullable=False),
    sa.Column('daily_abandon_count', sa.Integer(), nullable=False),
    sa.Column('last_login_date', sa.Date(), nullable=True),
    sa.Column('current_season_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['sys_account.id'], name=op.f('fk_sys_child_account_id_sys_account'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['family_id'], ['sys_family.id'], name=op.f('fk_sys_child_family_id_sys_family'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_child'))
    )
    op.create_index(op.f('ix_sys_child_account_id'), 'sys_child', ['account_id'], unique=True)
    op.create_index(op.f('ix_sys_child_family_id'), 'sys_child', ['family_id'], unique=False)
    op.create_table('sys_invite',
    sa.Column('family_id', sa.String(length=36), nullable=False),
    sa.Column('code', sa.String(length=16), nullable=False),
    sa.Column('role', sa.String(length=32), nullable=False),
    sa.Column('created_by', sa.String(length=36), nullable=True),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('used_at', sa.DateTime(), nullable=True),
    sa.Column('used_by', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['sys_account.id'], name=op.f('fk_sys_invite_created_by_sys_account'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['family_id'], ['sys_family.id'], name=op.f('fk_sys_invite_family_id_sys_family'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['used_by'], ['sys_account.id'], name=op.f('fk_sys_invite_used_by_sys_account'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_invite'))
    )
    op.create_index(op.f('ix_sys_invite_code'), 'sys_invite', ['code'], unique=True)
    op.create_index(op.f('ix_sys_invite_family_id'), 'sys_invite', ['family_id'], unique=False)
    op.create_table('sys_parent',
    sa.Column('account_id', sa.String(length=36), nullable=False),
    sa.Column('family_id', sa.String(length=36), nullable=False),
    sa.Column('display_name', sa.String(length=64), nullable=False),
    sa.Column('notify_settings', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['sys_account.id'], name=op.f('fk_sys_parent_account_id_sys_account'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['family_id'], ['sys_family.id'], name=op.f('fk_sys_parent_family_id_sys_family'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_parent'))
    )
    op.create_index(op.f('ix_sys_parent_account_id'), 'sys_parent', ['account_id'], unique=True)
    op.create_index(op.f('ix_sys_parent_family_id'), 'sys_parent', ['family_id'], unique=False)
    op.create_table('sys_upload',
    sa.Column('family_id', sa.String(length=36), nullable=False),
    sa.Column('uploader_account_id', sa.String(length=36), nullable=True),
    sa.Column('storage_provider', sa.String(length=16), nullable=False),
    sa.Column('bucket', sa.String(length=64), nullable=False),
    sa.Column('object_key', sa.String(length=512), nullable=False),
    sa.Column('public_url', sa.String(length=1024), nullable=True),
    sa.Column('content_type', sa.String(length=64), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('purpose', sa.String(length=32), nullable=False),
    sa.Column('etag', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['family_id'], ['sys_family.id'], name=op.f('fk_sys_upload_family_id_sys_family'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uploader_account_id'], ['sys_account.id'], name=op.f('fk_sys_upload_uploader_account_id_sys_account'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sys_upload')),
    sa.UniqueConstraint('object_key', name=op.f('uq_sys_upload_object_key'))
    )
    op.create_index(op.f('ix_sys_upload_family_id'), 'sys_upload', ['family_id'], unique=False)
    op.create_index(op.f('ix_sys_upload_purpose'), 'sys_upload', ['purpose'], unique=False)
    op.create_index(op.f('ix_sys_upload_uploader_account_id'), 'sys_upload', ['uploader_account_id'], unique=False)
    op.create_table('scn_privilege_unlock',
    sa.Column('family_id', sa.String(length=36), nullable=False),
    sa.Column('child_id', sa.String(length=36), nullable=False),
    sa.Column('season_id', sa.String(length=36), nullable=True),
    sa.Column('privilege_template_id', sa.String(length=36), nullable=False),
    sa.Column('unlocked_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('used_count', sa.Integer(), nullable=False),
    sa.Column('last_used_at', sa.DateTime(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['child_id'], ['sys_child.id'], name=op.f('fk_scn_privilege_unlock_child_id_sys_child'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['family_id'], ['sys_family.id'], name=op.f('fk_scn_privilege_unlock_family_id_sys_family'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['privilege_template_id'], ['scn_privilege_template.id'], name=op.f('fk_scn_privilege_unlock_privilege_template_id_scn_privilege_template'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['season_id'], ['scn_season.id'], name=op.f('fk_scn_privilege_unlock_season_id_scn_season'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_scn_privilege_unlock')),
    sa.UniqueConstraint('child_id', 'privilege_template_id', 'season_id', name='uq_scn_privilege_unlock_scope')
    )
    op.create_index(op.f('ix_scn_privilege_unlock_child_id'), 'scn_privilege_unlock', ['child_id'], unique=False)
    op.create_index(op.f('ix_scn_privilege_unlock_family_id'), 'scn_privilege_unlock', ['family_id'], unique=False)
    op.create_index(op.f('ix_scn_privilege_unlock_privilege_template_id'), 'scn_privilege_unlock', ['privilege_template_id'], unique=False)
    op.create_index(op.f('ix_scn_privilege_unlock_season_id'), 'scn_privilege_unlock', ['season_id'], unique=False)
    op.create_index(op.f('ix_scn_privilege_unlock_unlocked_at'), 'scn_privilege_unlock', ['unlocked_at'], unique=False)
    op.create_table('scn_privilege_use',
    sa.Column('family_id', sa.String(length=36), nullable=False),
    sa.Column('child_id', sa.String(length=36), nullable=False),
    sa.Column('season_id', sa.String(length=36), nullable=True),
    sa.Column('privilege_template_id', sa.String(length=36), nullable=True),
    sa.Column('privilege_title', sa.String(length=64), nullable=False),
    sa.Column('cost', sa.String(length=32), nullable=True),
    sa.Column('used_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['child_id'], ['sys_child.id'], name=op.f('fk_scn_privilege_use_child_id_sys_child'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['family_id'], ['sys_family.id'], name=op.f('fk_scn_privilege_use_family_id_sys_family'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['privilege_template_id'], ['scn_privilege_template.id'], name=op.f('fk_scn_privilege_use_privilege_template_id_scn_privilege_template'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['season_id'], ['scn_season.id'], name=op.f('fk_scn_privilege_use_season_id_scn_season'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_scn_privilege_use'))
    )
    op.create_index(op.f('ix_scn_privilege_use_child_id'), 'scn_privilege_use', ['child_id'], unique=False)
    op.create_index(op.f('ix_scn_privilege_use_family_id'), 'scn_privilege_use', ['family_id'], unique=False)
    op.create_index(op.f('ix_scn_privilege_use_privilege_template_id'), 'scn_privilege_use', ['privilege_template_id'], unique=False)
    op.create_index(op.f('ix_scn_privilege_use_season_id'), 'scn_privilege_use', ['season_id'], unique=False)
    op.create_index(op.f('ix_scn_privilege_use_used_at'), 'scn_privilege_use', ['used_at'], unique=False)
    op.create_table('scn_task_template',
    sa.Column('family_id', sa.String(length=36), nullable=False),
    sa.Column('season_id', sa.String(length=36), nullable=False),
    sa.Column('creator_account_id', sa.String(length=36), nullable=True),
    sa.Column('target_child_id', sa.String(length=36), nullable=True),
    sa.Column('title', sa.String(length=128), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('lore_snippet', sa.Text(), nullable=True),
    sa.Column('xp_reward', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(length=32), nullable=False),
    sa.Column('required_start_time', sa.Time(), nullable=True),
    sa.Column('reminder_message', sa.String(length=256), nullable=True),
    sa.Column('reminder_minutes_before', sa.Integer(), nullable=False),
    sa.Column('time_deposit', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['creator_account_id'], ['sys_account.id'], name=op.f('fk_scn_task_template_creator_account_id_sys_account'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['family_id'], ['sys_family.id'], name=op.f('fk_scn_task_template_family_id_sys_family'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['season_id'], ['scn_season.id'], name=op.f('fk_scn_task_template_season_id_scn_season'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['target_child_id'], ['sys_child.id'], name=op.f('fk_scn_task_template_target_child_id_sys_child'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_scn_task_template'))
    )
    op.create_index(op.f('ix_scn_task_template_family_id'), 'scn_task_template', ['family_id'], unique=False)
    op.create_index(op.f('ix_scn_task_template_is_active'), 'scn_task_template', ['is_active'], unique=False)
    op.create_index(op.f('ix_scn_task_template_season_id'), 'scn_task_template', ['season_id'], unique=False)
    op.create_index(op.f('ix_scn_task_template_target_child_id'), 'scn_task_template', ['target_child_id'], unique=False)
    op.create_table('scn_time_coin',
    sa.Column('family_id', sa.String(length=36), nullable=False),
    sa.Column('child_id', sa.String(length=36), nullable=False),
    sa.Column('season_id', sa.String(length=36), nullable=True),
    sa.Column('balance', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['child_id'], ['sys_child.id'], name=op.f('fk_scn_time_coin_child_id_sys_child'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['family_id'], ['sys_family.id'], name=op.f('fk_scn_time_coin_family_id_sys_family'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['season_id'], ['scn_season.id'], name=op.f('fk_scn_time_coin_season_id_scn_season'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_scn_time_coin')),
    sa.UniqueConstraint('family_id', 'child_id', 'season_id', name='uq_scn_time_coin_scope')
    )
    op.create_index(op.f('ix_scn_time_coin_child_id'), 'scn_time_coin', ['child_id'], unique=False)
    op.create_index(op.f('ix_scn_time_coin_family_id'), 'scn_time_coin', ['family_id'], unique=False)
    op.create_index(op.f('ix_scn_time_coin_season_id'), 'scn_time_coin', ['season_id'], unique=False)
    op.create_table('scn_trace',
    sa.Column('family_id', sa.String(length=36), nullable=False),
    sa.Column('season_id', sa.String(length=36), nullable=True),
    sa.Column('actor_account_id', sa.String(length=36), nullable=True),
    sa.Column('child_id', sa.String(length=36), nullable=True),
    sa.Column('event_type', sa.String(length=64), nullable=False),
    sa.Column('ref_type', sa.String(length=64), nullable=True),
    sa.Column('ref_id', sa.String(length=36), nullable=True),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['actor_account_id'], ['sys_account.id'], name=op.f('fk_scn_trace_actor_account_id_sys_account'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['child_id'], ['sys_child.id'], name=op.f('fk_scn_trace_child_id_sys_child'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['family_id'], ['sys_family.id'], name=op.f('fk_scn_trace_family_id_sys_family'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['season_id'], ['scn_season.id'], name=op.f('fk_scn_trace_season_id_scn_season'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_scn_trace'))
    )
    op.create_index(op.f('ix_scn_trace_actor_account_id'), 'scn_trace', ['actor_account_id'], unique=False)
    op.create_index(op.f('ix_scn_trace_child_id'), 'scn_trace', ['child_id'], unique=False)
    op.create_index(op.f('ix_scn_trace_created_at'), 'scn_trace', ['created_at'], unique=False)
    op.create_index(op.f('ix_scn_trace_event_type'), 'scn_trace', ['event_type'], unique=False)
    op.create_index(op.f('ix_scn_trace_family_id'), 'scn_trace', ['family_id'], unique=False)
    op.create_index(op.f('ix_scn_trace_ref_id'), 'scn_trace', ['ref_id'], unique=False)
    op.create_index(op.f('ix_scn_trace_ref_type'), 'scn_trace', ['ref_type'], unique=False)
    op.create_index(op.f('ix_scn_trace_season_id'), 'scn_trace', ['season_id'], unique=False)
    op.create_table('scn_task_instance',
    sa.Column('family_id', sa.String(length=36), nullable=False),
    sa.Column('season_id', sa.String(length=36), nullable=False),
    sa.Column('template_id', sa.String(length=36), nullable=True),
    sa.Column('creator_account_id', sa.String(length=36), nullable=True),
    sa.Column('target_child_id', sa.String(length=36), nullable=True),
    sa.Column('assignee_child_id', sa.String(length=36), nullable=True),
    sa.Column('title', sa.String(length=128), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('lore_snippet', sa.Text(), nullable=True),
    sa.Column('xp_reward', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('deadline', sa.DateTime(), nullable=True),
    sa.Column('proof_object_key', sa.String(length=512), nullable=True),
    sa.Column('rating', sa.Integer(), nullable=True, comment='1-5 星'),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('submitted_at', sa.DateTime(), nullable=True),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.Column('time_deposit', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['assignee_child_id'], ['sys_child.id'], name=op.f('fk_scn_task_instance_assignee_child_id_sys_child'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['creator_account_id'], ['sys_account.id'], name=op.f('fk_scn_task_instance_creator_account_id_sys_account'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['family_id'], ['sys_family.id'], name=op.f('fk_scn_task_instance_family_id_sys_family'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['season_id'], ['scn_season.id'], name=op.f('fk_scn_task_instance_season_id_scn_season'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['target_child_id'], ['sys_child.id'], name=op.f('fk_scn_task_instance_target_child_id_sys_child'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['template_id'], ['scn_task_template.id'], name=op.f('fk_scn_task_instance_template_id_scn_task_template'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_scn_task_instance'))
    )
    op.create_index(op.f('ix_scn_task_instance_assignee_child_id'), 'scn_task_instance', ['assignee_child_id'], unique=False)
    op.create_index(op.f('ix_scn_task_instance_family_id'), 'scn_task_instance', ['family_id'], unique=False)
    op.create_index(op.f('ix_scn_task_instance_season_id'), 'scn_task_instance', ['season_id'], unique=False)
    op.create_index(op.f('ix_scn_task_instance_status'), 'scn_task_instance', ['status'], unique=False)
    op.create_index(op.f('ix_scn_task_instance_target_child_id'), 'scn_task_instance', ['target_child_id'], unique=False)
    op.create_index(op.f('ix_scn_task_instance_template_id'), 'scn_task_instance', ['template_id'], unique=False)
    op.create_table('scn_time_coin_log',
    sa.Column('family_id', sa.String(length=36), nullable=False),
    sa.Column('child_id', sa.String(length=36), nullable=False),
    sa.Column('season_id', sa.String(length=36), nullable=True),
    sa.Column('task_instance_id', sa.String(length=36), nullable=True),
    sa.Column('type', sa.String(length=32), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False, comment='正数表示增加,负数表示扣减'),
    sa.Column('balance_after', sa.Integer(), nullable=False),
    sa.Column('note', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['child_id'], ['sys_child.id'], name=op.f('fk_scn_time_coin_log_child_id_sys_child'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['family_id'], ['sys_family.id'], name=op.f('fk_scn_time_coin_log_family_id_sys_family'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['season_id'], ['scn_season.id'], name=op.f('fk_scn_time_coin_log_season_id_scn_season'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['task_instance_id'], ['scn_task_instance.id'], name=op.f('fk_scn_time_coin_log_task_instance_id_scn_task_instance'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_scn_time_coin_log'))
    )
    op.create_index(op.f('ix_scn_time_coin_log_child_id'), 'scn_time_coin_log', ['child_id'], unique=False)
    op.create_index(op.f('ix_scn_time_coin_log_created_at'), 'scn_time_coin_log', ['created_at'], unique=False)
    op.create_index(op.f('ix_scn_time_coin_log_family_id'), 'scn_time_coin_log', ['family_id'], unique=False)
    op.create_index(op.f('ix_scn_time_coin_log_season_id'), 'scn_time_coin_log', ['season_id'], unique=False)
    op.create_index(op.f('ix_scn_time_coin_log_task_instance_id'), 'scn_time_coin_log', ['task_instance_id'], unique=False)
    op.create_index(op.f('ix_scn_time_coin_log_type'), 'scn_time_coin_log', ['type'], unique=False)


def downgrade() -> None:
    """Drop the initial sys_* / scn_* schema."""
    op.drop_table('scn_time_coin_log')
    op.drop_table('scn_task_instance')
    op.drop_table('scn_trace')
    op.drop_table('scn_time_coin')
    op.drop_table('scn_task_template')
    op.drop_table('scn_privilege_use')
    op.drop_table('scn_privilege_unlock')
    op.drop_table('sys_upload')
    op.drop_table('sys_parent')
    op.drop_table('sys_invite')
    op.drop_table('sys_child')
    op.drop_table('sys_channel_wechat')
    op.drop_table('scn_time_config_exception')
    op.drop_table('scn_theme_style')
    op.drop_table('scn_privilege_template')
    op.drop_table('sys_account')
    op.drop_table('scn_time_config')
    op.drop_table('scn_season')
    op.drop_table('sys_family')
