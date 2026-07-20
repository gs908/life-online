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
    """外部服务(LLM / 微信 / 存储)调用失败。"""
    code = "external_service_error"
    http_status = 502
