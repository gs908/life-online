"""Pydantic DTO 集合(API 层的输入/输出契约)。"""
from app.schemas.common import ApiResponse, PageQuery, PageResult
from app.schemas.token import RefreshRequest, TokenPair, WechatJscodeRequest
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.schemas.family import (
    FamilyCreate,
    FamilyInviteCreate,
    FamilyInviteRead,
    FamilyJoinRequest,
    FamilyRead,
)
from app.schemas.task import (
    TaskCreate,
    TaskRead,
    TaskStartRequest,
    TaskSubmitRequest,
    TaskApproveRequest,
    TaskAbandonRequest,
)
from app.schemas.season import SeasonCreate, SeasonRead, SeasonUpdate
from app.schemas.time_config import TimeConfigExceptionRead, TimeConfigRead, TimeConfigUpdate
from app.schemas.privilege import PrivilegeRead
from app.schemas.redemption import RedemptionCreate, RedemptionRead
from app.schemas.upload import UploadRead, UploadUrlRequest

__all__ = [
    "ApiResponse", "PageQuery", "PageResult",
    "RefreshRequest", "TokenPair", "WechatJscodeRequest",
    "UserCreate", "UserRead", "UserUpdate",
    "FamilyCreate", "FamilyInviteCreate", "FamilyInviteRead",
    "FamilyJoinRequest", "FamilyRead",
    "TaskCreate", "TaskRead",
    "TaskStartRequest", "TaskSubmitRequest", "TaskApproveRequest", "TaskAbandonRequest",
    "SeasonCreate", "SeasonRead", "SeasonUpdate",
    "TimeConfigExceptionRead", "TimeConfigRead", "TimeConfigUpdate",
    "PrivilegeRead",
    "RedemptionCreate", "RedemptionRead",
    "UploadRead", "UploadUrlRequest",
]
