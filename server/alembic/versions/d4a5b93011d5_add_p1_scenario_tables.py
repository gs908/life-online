"""add p1 scenario tables

Revision ID: d4a5b93011d5
Revises: 4bb73fc2e250
Create Date: 2026-07-26 01:37:17.387363

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4a5b93011d5"
down_revision: Union[str, None] = "4bb73fc2e250"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scn_onboarding_path",
        sa.Column("family_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=256), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["family_id"], ["sys_family.id"],
            name=op.f("fk_scn_onboarding_path_family_id_sys_family"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scn_onboarding_path")),
    )
    op.create_index(op.f("ix_scn_onboarding_path_family_id"), "scn_onboarding_path", ["family_id"], unique=False)
    op.create_index(op.f("ix_scn_onboarding_path_is_active"), "scn_onboarding_path", ["is_active"], unique=False)
    op.create_index(op.f("ix_scn_onboarding_path_is_system"), "scn_onboarding_path", ["is_system"], unique=False)

    op.create_table(
        "scn_task_template_library",
        sa.Column("family_id", sa.String(length=36), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("suggested_xp", sa.Integer(), nullable=False),
        sa.Column("suggested_time_deposit", sa.Integer(), nullable=False),
        sa.Column("suggested_type", sa.String(length=32), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["family_id"], ["sys_family.id"],
            name=op.f("fk_scn_task_template_library_family_id_sys_family"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scn_task_template_library")),
    )
    op.create_index(op.f("ix_scn_task_template_library_category"), "scn_task_template_library", ["category"], unique=False)
    op.create_index(op.f("ix_scn_task_template_library_family_id"), "scn_task_template_library", ["family_id"], unique=False)
    op.create_index(op.f("ix_scn_task_template_library_is_active"), "scn_task_template_library", ["is_active"], unique=False)

    op.add_column("scn_task_template", sa.Column("library_id", sa.String(length=36), nullable=True))
    op.add_column("scn_task_template", sa.Column("category", sa.String(length=32), nullable=True))
    op.create_index(op.f("ix_scn_task_template_category"), "scn_task_template", ["category"], unique=False)
    op.create_index(op.f("ix_scn_task_template_library_id"), "scn_task_template", ["library_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_scn_task_template_library_id_scn_task_template_library"),
        "scn_task_template", "scn_task_template_library", ["library_id"], ["id"], ondelete="SET NULL",
    )

    op.create_table(
        "scn_onboarding_step",
        sa.Column("path_id", sa.String(length=36), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=True),
        sa.Column("unlocks_after", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("reward_xp", sa.Integer(), nullable=False),
        sa.Column("reward_coin", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["path_id"], ["scn_onboarding_path.id"],
            name=op.f("fk_scn_onboarding_step_path_id_scn_onboarding_path"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"], ["scn_task_template.id"],
            name=op.f("fk_scn_onboarding_step_template_id_scn_task_template"), ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["unlocks_after"], ["scn_onboarding_step.id"],
            name=op.f("fk_scn_onboarding_step_unlocks_after_scn_onboarding_step"), ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scn_onboarding_step")),
        sa.UniqueConstraint("path_id", "sort_order", name="uq_scn_onboarding_step_order"),
    )
    op.create_index(op.f("ix_scn_onboarding_step_path_id"), "scn_onboarding_step", ["path_id"], unique=False)
    op.create_index(op.f("ix_scn_onboarding_step_template_id"), "scn_onboarding_step", ["template_id"], unique=False)
    op.create_index(op.f("ix_scn_onboarding_step_unlocks_after"), "scn_onboarding_step", ["unlocks_after"], unique=False)

    op.create_table(
        "scn_stats_daily",
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("child_id", sa.String(length=36), nullable=False),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column("quests_completed", sa.Integer(), nullable=False),
        sa.Column("quests_submitted", sa.Integer(), nullable=False),
        sa.Column("quests_rejected", sa.Integer(), nullable=False),
        sa.Column("quests_abandoned", sa.Integer(), nullable=False),
        sa.Column("avg_rating", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("xp_earned", sa.Integer(), nullable=False),
        sa.Column("time_coins_earned", sa.Integer(), nullable=False),
        sa.Column("time_coins_spent", sa.Integer(), nullable=False),
        sa.Column("minutes_active", sa.Integer(), nullable=False),
        sa.Column("by_type", sa.JSON(), nullable=False),
        sa.Column("by_category", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["child_id"], ["sys_child.id"], name=op.f("fk_scn_stats_daily_child_id_sys_child"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["family_id"], ["sys_family.id"], name=op.f("fk_scn_stats_daily_family_id_sys_family"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scn_stats_daily")),
        sa.UniqueConstraint("family_id", "child_id", "stat_date", name="uq_scn_stats_daily_scope"),
    )
    op.create_index(op.f("ix_scn_stats_daily_child_id"), "scn_stats_daily", ["child_id"], unique=False)
    op.create_index(op.f("ix_scn_stats_daily_family_id"), "scn_stats_daily", ["family_id"], unique=False)
    op.create_index(op.f("ix_scn_stats_daily_stat_date"), "scn_stats_daily", ["stat_date"], unique=False)

    op.create_table(
        "scn_hidden_quest",
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("season_id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=True),
        sa.Column("trigger_kind", sa.String(length=32), nullable=False),
        sa.Column("trigger_rule", sa.JSON(), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("lore_snippet", sa.Text(), nullable=True),
        sa.Column("xp_reward", sa.Integer(), nullable=False),
        sa.Column("time_deposit", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("max_claims", sa.Integer(), nullable=False),
        sa.Column("claimed_count", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["sys_account.id"], name=op.f("fk_scn_hidden_quest_created_by_sys_account"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["family_id"], ["sys_family.id"], name=op.f("fk_scn_hidden_quest_family_id_sys_family"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["season_id"], ["scn_season.id"], name=op.f("fk_scn_hidden_quest_season_id_scn_season"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["scn_task_template.id"], name=op.f("fk_scn_hidden_quest_template_id_scn_task_template"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scn_hidden_quest")),
    )
    op.create_index(op.f("ix_scn_hidden_quest_created_by"), "scn_hidden_quest", ["created_by"], unique=False)
    op.create_index(op.f("ix_scn_hidden_quest_expires_at"), "scn_hidden_quest", ["expires_at"], unique=False)
    op.create_index(op.f("ix_scn_hidden_quest_family_id"), "scn_hidden_quest", ["family_id"], unique=False)
    op.create_index(op.f("ix_scn_hidden_quest_is_active"), "scn_hidden_quest", ["is_active"], unique=False)
    op.create_index(op.f("ix_scn_hidden_quest_season_id"), "scn_hidden_quest", ["season_id"], unique=False)
    op.create_index(op.f("ix_scn_hidden_quest_starts_at"), "scn_hidden_quest", ["starts_at"], unique=False)
    op.create_index(op.f("ix_scn_hidden_quest_template_id"), "scn_hidden_quest", ["template_id"], unique=False)
    op.create_index(op.f("ix_scn_hidden_quest_trigger_kind"), "scn_hidden_quest", ["trigger_kind"], unique=False)

    op.create_table(
        "scn_notification",
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("recipient_account_id", sa.String(length=36), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("wechat_msg_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["family_id"], ["sys_family.id"], name=op.f("fk_scn_notification_family_id_sys_family"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_account_id"], ["sys_account.id"], name=op.f("fk_scn_notification_recipient_account_id_sys_account"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scn_notification")),
    )
    op.create_index(op.f("ix_scn_notification_channel"), "scn_notification", ["channel"], unique=False)
    op.create_index(op.f("ix_scn_notification_created_at"), "scn_notification", ["created_at"], unique=False)
    op.create_index(op.f("ix_scn_notification_family_id"), "scn_notification", ["family_id"], unique=False)
    op.create_index(op.f("ix_scn_notification_recipient_account_id"), "scn_notification", ["recipient_account_id"], unique=False)
    op.create_index(op.f("ix_scn_notification_status"), "scn_notification", ["status"], unique=False)
    op.create_index(op.f("ix_scn_notification_type"), "scn_notification", ["type"], unique=False)

    op.create_table(
        "scn_task_proof",
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("task_instance_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["family_id"], ["sys_family.id"], name=op.f("fk_scn_task_proof_family_id_sys_family"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_instance_id"], ["scn_task_instance.id"], name=op.f("fk_scn_task_proof_task_instance_id_scn_task_instance"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["sys_account.id"], name=op.f("fk_scn_task_proof_uploaded_by_sys_account"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scn_task_proof")),
        sa.UniqueConstraint("object_key", name=op.f("uq_scn_task_proof_object_key")),
    )
    op.create_index(op.f("ix_scn_task_proof_created_at"), "scn_task_proof", ["created_at"], unique=False)
    op.create_index(op.f("ix_scn_task_proof_deleted_at"), "scn_task_proof", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_scn_task_proof_family_id"), "scn_task_proof", ["family_id"], unique=False)
    op.create_index(op.f("ix_scn_task_proof_kind"), "scn_task_proof", ["kind"], unique=False)
    op.create_index(op.f("ix_scn_task_proof_task_instance_id"), "scn_task_proof", ["task_instance_id"], unique=False)
    op.create_index(op.f("ix_scn_task_proof_uploaded_by"), "scn_task_proof", ["uploaded_by"], unique=False)

    op.add_column("scn_task_instance", sa.Column("expire_at", sa.DateTime(), nullable=True))
    op.add_column("scn_task_instance", sa.Column("review_comment", sa.Text(), nullable=True))
    op.add_column("scn_task_instance", sa.Column("xp_awarded", sa.Integer(), nullable=True))
    op.add_column("scn_task_instance", sa.Column("coin_delta", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("scn_task_instance", sa.Column("abandon_count_at_submit", sa.Integer(), nullable=False, server_default="0"))
    op.alter_column("scn_task_instance", "coin_delta", server_default=None)
    op.alter_column("scn_task_instance", "abandon_count_at_submit", server_default=None)
    op.create_index(op.f("ix_scn_task_instance_expire_at"), "scn_task_instance", ["expire_at"], unique=False)

    op.add_column("sys_child", sa.Column("onboarding_path_id", sa.String(length=36), nullable=True))
    op.add_column("sys_child", sa.Column("onboarding_step_id", sa.String(length=36), nullable=True))
    op.create_index(op.f("ix_sys_child_onboarding_path_id"), "sys_child", ["onboarding_path_id"], unique=False)
    op.create_index(op.f("ix_sys_child_onboarding_step_id"), "sys_child", ["onboarding_step_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_sys_child_onboarding_path_id_scn_onboarding_path"),
        "sys_child", "scn_onboarding_path", ["onboarding_path_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_sys_child_onboarding_step_id_scn_onboarding_step"),
        "sys_child", "scn_onboarding_step", ["onboarding_step_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_sys_child_onboarding_step_id_scn_onboarding_step"), "sys_child", type_="foreignkey")
    op.drop_constraint(op.f("fk_sys_child_onboarding_path_id_scn_onboarding_path"), "sys_child", type_="foreignkey")
    op.drop_index(op.f("ix_sys_child_onboarding_step_id"), table_name="sys_child")
    op.drop_index(op.f("ix_sys_child_onboarding_path_id"), table_name="sys_child")
    op.drop_column("sys_child", "onboarding_step_id")
    op.drop_column("sys_child", "onboarding_path_id")

    op.drop_index(op.f("ix_scn_task_instance_expire_at"), table_name="scn_task_instance")
    op.drop_column("scn_task_instance", "abandon_count_at_submit")
    op.drop_column("scn_task_instance", "coin_delta")
    op.drop_column("scn_task_instance", "xp_awarded")
    op.drop_column("scn_task_instance", "review_comment")
    op.drop_column("scn_task_instance", "expire_at")

    op.drop_index(op.f("ix_scn_task_proof_uploaded_by"), table_name="scn_task_proof")
    op.drop_index(op.f("ix_scn_task_proof_task_instance_id"), table_name="scn_task_proof")
    op.drop_index(op.f("ix_scn_task_proof_kind"), table_name="scn_task_proof")
    op.drop_index(op.f("ix_scn_task_proof_family_id"), table_name="scn_task_proof")
    op.drop_index(op.f("ix_scn_task_proof_deleted_at"), table_name="scn_task_proof")
    op.drop_index(op.f("ix_scn_task_proof_created_at"), table_name="scn_task_proof")
    op.drop_table("scn_task_proof")

    op.drop_index(op.f("ix_scn_notification_type"), table_name="scn_notification")
    op.drop_index(op.f("ix_scn_notification_status"), table_name="scn_notification")
    op.drop_index(op.f("ix_scn_notification_recipient_account_id"), table_name="scn_notification")
    op.drop_index(op.f("ix_scn_notification_family_id"), table_name="scn_notification")
    op.drop_index(op.f("ix_scn_notification_created_at"), table_name="scn_notification")
    op.drop_index(op.f("ix_scn_notification_channel"), table_name="scn_notification")
    op.drop_table("scn_notification")

    op.drop_index(op.f("ix_scn_hidden_quest_trigger_kind"), table_name="scn_hidden_quest")
    op.drop_index(op.f("ix_scn_hidden_quest_template_id"), table_name="scn_hidden_quest")
    op.drop_index(op.f("ix_scn_hidden_quest_starts_at"), table_name="scn_hidden_quest")
    op.drop_index(op.f("ix_scn_hidden_quest_season_id"), table_name="scn_hidden_quest")
    op.drop_index(op.f("ix_scn_hidden_quest_is_active"), table_name="scn_hidden_quest")
    op.drop_index(op.f("ix_scn_hidden_quest_family_id"), table_name="scn_hidden_quest")
    op.drop_index(op.f("ix_scn_hidden_quest_expires_at"), table_name="scn_hidden_quest")
    op.drop_index(op.f("ix_scn_hidden_quest_created_by"), table_name="scn_hidden_quest")
    op.drop_table("scn_hidden_quest")

    op.drop_index(op.f("ix_scn_stats_daily_stat_date"), table_name="scn_stats_daily")
    op.drop_index(op.f("ix_scn_stats_daily_family_id"), table_name="scn_stats_daily")
    op.drop_index(op.f("ix_scn_stats_daily_child_id"), table_name="scn_stats_daily")
    op.drop_table("scn_stats_daily")

    op.drop_index(op.f("ix_scn_onboarding_step_unlocks_after"), table_name="scn_onboarding_step")
    op.drop_index(op.f("ix_scn_onboarding_step_template_id"), table_name="scn_onboarding_step")
    op.drop_index(op.f("ix_scn_onboarding_step_path_id"), table_name="scn_onboarding_step")
    op.drop_table("scn_onboarding_step")

    op.drop_constraint(op.f("fk_scn_task_template_library_id_scn_task_template_library"), "scn_task_template", type_="foreignkey")
    op.drop_index(op.f("ix_scn_task_template_library_id"), table_name="scn_task_template")
    op.drop_index(op.f("ix_scn_task_template_category"), table_name="scn_task_template")
    op.drop_column("scn_task_template", "category")
    op.drop_column("scn_task_template", "library_id")

    op.drop_index(op.f("ix_scn_task_template_library_is_active"), table_name="scn_task_template_library")
    op.drop_index(op.f("ix_scn_task_template_library_family_id"), table_name="scn_task_template_library")
    op.drop_index(op.f("ix_scn_task_template_library_category"), table_name="scn_task_template_library")
    op.drop_table("scn_task_template_library")

    op.drop_index(op.f("ix_scn_onboarding_path_is_system"), table_name="scn_onboarding_path")
    op.drop_index(op.f("ix_scn_onboarding_path_is_active"), table_name="scn_onboarding_path")
    op.drop_index(op.f("ix_scn_onboarding_path_family_id"), table_name="scn_onboarding_path")
    op.drop_table("scn_onboarding_path")
