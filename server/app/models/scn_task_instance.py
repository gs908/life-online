"""
任务实例:某个任务模板在具体周期/孩子上的执行记录。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ContentSource, TaskStatus

if TYPE_CHECKING:
    from app.models.scn_season import ScnSeason
    from app.models.scn_task_participant import ScnTaskParticipant
    from app.models.scn_task_template import ScnTaskTemplate


class ScnTaskInstance(Base, TimestampMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "scn_task_instance"
    # 实例池幂等兜底(docs/12 块 A):同模板同逻辑日至多一条生成实例,
    # 并发生成靠该 partial unique index 撞库回捞,生成器不再依赖锁。
    __table_args__ = (
        Index(
            "uq_scn_task_instance_template_generated_for_date",
            "template_id",
            "generated_for_date",
            unique=True,
            postgresql_where=text("generated_for_date IS NOT NULL"),
        ),
    )

    family_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sys_family.id", ondelete="CASCADE"), nullable=False, index=True
    )
    season_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scn_season.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scn_task_template.id", ondelete="SET NULL"), nullable=True, index=True
    )
    creator_account_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sys_account.id", ondelete="SET NULL"), nullable=True
    )
    target_child_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sys_child.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assignee_child_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sys_child.id", ondelete="SET NULL"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    lore_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    xp_reward: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    status: Mapped[TaskStatus] = mapped_column(
        String(32), nullable=False, default=TaskStatus.AVAILABLE, index=True
    )
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    # 实例归属逻辑日(docs/12 块 A):生成器产出实例时锚定"为哪一天生成",
    # 与 template_id 构成 partial unique index 兜底并发;一次性手工任务为 NULL。
    generated_for_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    proof_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="1-5 星")
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    xp_awarded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    coin_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    abandon_count_at_submit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_deposit: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    # ---- CHAIN 递进串行(DEV-36 块 F)------------------------------------
    # 实例化时从模板快照:chain_index = 模板.chain_order(1-based)。
    # 链末步骤(chain_index == chain_total)审批通过时享受链末 XP 加成。
    chain_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chain_total: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ---- 任务内容生成(docs/15 §5)------------------------------------
    # 叙事来源:TEMPLATE(模板文本)/ LLM(生成成功)/ FALLBACK(LLM 失败或能力关闭)。
    # generation_meta 为内部数据(模型名/提示词哈希/token 数/耗时/失败错误类名),
    # 不出 API(docs/15 R25)。
    content_source: Mapped[ContentSource] = mapped_column(
        String(16), nullable=False, default=ContentSource.TEMPLATE, comment="叙事来源:TEMPLATE/LLM/FALLBACK"
    )
    generation_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    season: Mapped["ScnSeason"] = relationship(back_populates="task_instances", lazy="raise")
    # template 被 _to_read / approve_task 读取(含 create_task 提交后的 refresh 路径),
    # 是 16 处 noload 中唯一确有加载需求的,按语义改 selectin 而非 raise。
    template: Mapped["ScnTaskTemplate | None"] = relationship(lazy="selectin")
    # COOP 参与者(DEV-36 块 F):非 COOP 任务无记录;COOP 任务至少有主接取人一条
    participants: Mapped[list["ScnTaskParticipant"]] = relationship(
        back_populates="task_instance",
        lazy="selectin",
        order_by="ScnTaskParticipant.created_at",
        cascade="all, delete-orphan",
    )
