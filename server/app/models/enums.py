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
    MANUAL_ADJUST = "MANUAL_ADJUST"


class NotificationType(str, Enum):
    TASK_SUBMITTED = "TASK_SUBMITTED"
    TASK_APPROVED = "TASK_APPROVED"
    TASK_REJECTED = "TASK_REJECTED"
    TASK_REMINDER = "TASK_REMINDER"
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


class ProofKind(str, Enum):
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
