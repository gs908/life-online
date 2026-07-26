"""
业务异常定义。

服务层 / 业务代码抛出 AppError 子类,
由全局异常处理器(后续添加)统一转换为 HTTP 响应。
"""
from __future__ import annotations


class AppError(Exception):
    """所有业务异常的基类。"""

    code: str = "app_error"
    http_status: int = 500

    def __init__(self, message: str = "", *, code: str | None = None, http_status: int | None = None) -> None:
        super().__init__(message or self.__class__.__name__)
        self.message = message or self.__class__.__name__
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status


class NotFoundError(AppError):
    code = "not_found"
    http_status = 404


class PermissionDeniedError(AppError):
    code = "permission_denied"
    http_status = 403


class UnauthorizedError(AppError):
    code = "unauthorized"
    http_status = 401


class ValidationError(AppError):
    code = "validation_error"
    http_status = 422


class ConflictError(AppError):
    code = "conflict"
    http_status = 409


class ExternalServiceError(AppError):
    """外部服务(LLM / 微信 / 存储)调用失败(已配置,但请求本身失败)。"""
    code = "external_service_error"
    http_status = 502


class ServiceUnavailableError(AppError):
    """依赖的外部服务(LLM / MinIO 等)尚未配置,功能暂不可用。

    与 ExternalServiceError 的区别:这里请求根本没有发出去,是部署/配置缺失,
    前端应据此提示"该功能未开放"而不是"稍后重试"。
    """
    code = "service_unavailable"
    http_status = 503
