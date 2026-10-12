"""
业务枚举。全部使用大驼峰命名(str Enum,便于 JSON 序列化)。
"""
from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    GUILD_MASTER = "GUILD_MASTER"  # 父母 / 公会会长
    ADVENTURER = "ADVENTURER"      # 孩子 / 冒险者


class TaskType(str, Enum):
    DAILY = "DAILY"
    CHALLENGE = "CHALLENGE"
    CHAIN = "CHAIN"          # 串行任务
    TIMED = "TIMED"          # 必须在某时间点前开始
    COOP = "COOP"            # 多人/亲子合作


class TaskStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING_REVIEW = "PENDING_REVIEW"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"


class TriggerKind(str, Enum):
    """模板触发规则类型(docs/12 块 A):一个模板可挂多条规则,任一命中即到期。"""

    DAILY = "DAILY"          # 每天
    WEEKDAYS = "WEEKDAYS"    # 指定星期(0=周一..6=周日)
    MONTHLY = "MONTHLY"      # 每月某日(月末不足取当月最后一天)
    CRON = "CRON"            # 5 段 cron 表达式,家庭本地时区
    ONCE = "ONCE"            # 一次性,在 starts_on 当天生成


class TimedMode(str, Enum):
    """模板限时模式:决定实例 expire_at 的计算方式。"""

    NONE = "NONE"            # 非限时,expire_at 为 NULL
    DEADLINE = "DEADLINE"    # 当日截止时刻 deadline_time
    DURATION = "DURATION"    # 从 start_time 起持续 duration_minutes


class PoolPolicy(str, Enum):
    """实例池策略(docs/12 块 A,决策 D1)。"""

    REUSE_UNTIL_CONSUMED = "REUSE_UNTIL_CONSUMED"  # 默认:未消费实例跨天顺延
    NEW_EACH_PERIOD = "NEW_EACH_PERIOD"            # 备选:每周期新开(本轮不默认)


class ThemeId(str, Enum):
    DEFAULT = "DEFAULT"
    FROSTBOUND = "FROSTBOUND"
    INFERNO = "INFERNO"
    SYLVAN = "SYLVAN"
    CYBERPUNK = "CYBERPUNK"


class InviteRole(str, Enum):
    """家庭邀请时可指定的目标角色。"""
    GUILD_MASTER = "GUILD_MASTER"
    ADVENTURER = "ADVENTURER"


class UploadPurpose(str, Enum):
    AVATAR = "avatar"
    TASK_PROOF = "task_proof"
    SEASON_BANNER = "season_banner"
    OTHER = "other"


class CoinTransactionType(str, Enum):
    DAILY_RESET = "DAILY_RESET"
    TASK_DEPOSIT = "TASK_DEPOSIT"
    TASK_REFUND = "TASK_REFUND"
    ABANDON_PENALTY = "ABANDON_PENALTY"
    TIMEOUT_PENALTY = "TIMEOUT_PENALTY"  # 限时任务超时(非孩子主动放弃)扣罚
    MANUAL_ADJUST = "MANUAL_ADJUST"


class NotificationType(str, Enum):
    TASK_SUBMITTED = "TASK_SUBMITTED"
    TASK_APPROVED = "TASK_APPROVED"
    TASK_REJECTED = "TASK_REJECTED"
    TASK_REMINDER = "TASK_REMINDER"
    TASK_EXPIRED = "TASK_EXPIRED"
    PRIVILEGE_UNLOCKED = "PRIVILEGE_UNLOCKED"
    LEVEL_UP = "LEVEL_UP"
    TIME_COIN_RESET = "TIME_COIN_RESET"
    SEASON_START = "SEASON_START"
    ONBOARDING_STEP_COMPLETED = "ONBOARDING_STEP_COMPLETED"


class NotificationChannel(str, Enum):
    INAPP = "INAPP"
    WECHAT_TMPL = "WECHAT_TMPL"
    BOTH = "BOTH"


class NotificationStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    READ = "READ"


class TaskCategory(str, Enum):
    STUDY = "STUDY"
    CHORE = "CHORE"
    SPORT = "SPORT"
    ART = "ART"
    LIFE = "LIFE"
    OTHER = "OTHER"


class HiddenTriggerKind(str, Enum):
    AFTER_TASK_COMPLETED = "AFTER_TASK_COMPLETED"
    MANUAL = "MANUAL"
    RANDOM_IN_TIME_WINDOW = "RANDOM_IN_TIME_WINDOW"


class TaskParticipantRole(str, Enum):
    """COOP 任务的参与者角色。

    - OWNER: 主接取人,对应 scn_task_instance.assignee_child_id,接取时自动登记。
    - MEMBER: 其他孩子参与者,主动 join 时登记。
    - PARENT: 亲子协作中的家长参与者。家长没有时间币/XP 账户,
      不参与押金均摊,也不获得 XP(见 docs/04 §4)。
    """

    OWNER = "OWNER"
    MEMBER = "MEMBER"
    PARENT = "PARENT"


class ProofKind(str, Enum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
