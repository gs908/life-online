"""
数据模型入口。

所有实体在此集中导入,确保 Alembic autogenerate 能看到完整 metadata。
"""
from app.models.enums import (
    CoinTransactionType,
    HiddenTriggerKind,
    InviteRole,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    ProofKind,
    TaskCategory,
    TaskStatus,
    TaskType,
    ThemeId,
    UploadPurpose,
    UserRole,
)
from app.models.scn_hidden_quest import ScnHiddenQuest
from app.models.scn_notification import ScnNotification
from app.models.scn_onboarding_path import ScnOnboardingPath
from app.models.scn_onboarding_step import ScnOnboardingStep
from app.models.scn_privilege_template import ScnPrivilegeTemplate
from app.models.scn_privilege_unlock import ScnPrivilegeUnlock
from app.models.scn_privilege_use import ScnPrivilegeUse
from app.models.scn_season import ScnSeason
from app.models.scn_stats_daily import ScnStatsDaily
from app.models.scn_task_instance import ScnTaskInstance
from app.models.scn_task_proof import ScnTaskProof
from app.models.scn_task_template import ScnTaskTemplate
from app.models.scn_task_template_library import ScnTaskTemplateLibrary
from app.models.scn_theme_style import ScnThemeStyle
from app.models.scn_time_coin import ScnTimeCoin
from app.models.scn_time_coin_log import ScnTimeCoinLog
from app.models.scn_time_config import ScnTimeConfig
from app.models.scn_time_config_exception import ScnTimeConfigException
from app.models.scn_trace import ScnTrace
from app.models.sys_account import SysAccount
from app.models.sys_channel_wechat import SysChannelWechat
from app.models.sys_child import SysChild
from app.models.sys_family import SysFamily
from app.models.sys_invite import SysInvite
from app.models.sys_parent import SysParent
from app.models.sys_upload import SysUpload

__all__ = [
    "CoinTransactionType",
    "HiddenTriggerKind",
    "InviteRole",
    "NotificationChannel",
    "NotificationStatus",
    "NotificationType",
    "ProofKind",
    "ScnHiddenQuest",
    "ScnNotification",
    "ScnOnboardingPath",
    "ScnOnboardingStep",
    "ScnPrivilegeTemplate",
    "ScnPrivilegeUnlock",
    "ScnPrivilegeUse",
    "ScnSeason",
    "ScnStatsDaily",
    "ScnTaskInstance",
    "ScnTaskProof",
    "ScnTaskTemplate",
    "ScnTaskTemplateLibrary",
    "ScnThemeStyle",
    "ScnTimeCoin",
    "ScnTimeCoinLog",
    "ScnTimeConfig",
    "ScnTimeConfigException",
    "ScnTrace",
    "SysAccount",
    "SysChannelWechat",
    "SysChild",
    "SysFamily",
    "SysInvite",
    "SysParent",
    "SysUpload",
    "TaskCategory",
    "TaskStatus",
    "TaskType",
    "ThemeId",
    "UploadPurpose",
    "UserRole",
]
