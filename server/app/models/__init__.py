"""
数据模型入口。

所有实体在此集中导入,确保 Alembic autogenerate 能看到完整 metadata。
"""
from app.models.enums import (
    CoinTransactionType,
    InviteRole,
    TaskStatus,
    TaskType,
    ThemeId,
    UploadPurpose,
    UserRole,
)
from app.models.coin_transaction import CoinTransaction
from app.models.family import Family
from app.models.family_invite import FamilyInvite
from app.models.privilege import Privilege
from app.models.redemption import RedemptionRecord
from app.models.season import Season
from app.models.task import Task
from app.models.theme_style import ThemeStyle
from app.models.time_config import TimeConfig
from app.models.time_config_exception import TimeConfigException
from app.models.upload import Upload
from app.models.user import User
from app.models.user_privilege import UserPrivilege
from app.models.wechat_account import WechatAccount

__all__ = [
    "Family",
    "CoinTransaction",
    "CoinTransactionType",
    "FamilyInvite",
    "Privilege",
    "RedemptionRecord",
    "Season",
    "Task",
    "ThemeStyle",
    "TaskStatus",
    "TaskType",
    "ThemeId",
    "TimeConfig",
    "TimeConfigException",
    "Upload",
    "UploadPurpose",
    "User",
    "UserPrivilege",
    "UserRole",
    "WechatAccount",
    "InviteRole",
]
