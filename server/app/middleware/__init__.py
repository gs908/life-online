"""
全局异常处理:把业务异常统一转换为 JSON 响应。
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

from app.common.exceptions import AppError
from app.common.logging import get_logger

log = get_logger("app.error")


def _json_safe(errors: list) -> list:
    """exc.errors() 里的 ctx 可能带 ValueError 等异常对象(model_validator 抛出),
    JSONResponse 无法序列化,统一降级为其字符串表示。"""
    def clean(value):
        if isinstance(value, Exception):
            return str(value)
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [clean(v) for v in value]
        return value

    return [clean(e) for e in errors]


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": 1, "data": {"error_code": exc.code}, "msg": exc.message},
        )

    @app.exception_handler(RequestValidationError)
    async def _req_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"code": 1, "data": _json_safe(exc.errors()), "msg": "请求参数校验失败"},
        )

    @app.exception_handler(PydanticValidationError)
    async def _pyd_validation(_: Request, exc: PydanticValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"code": 1, "data": _json_safe(exc.errors()), "msg": "数据校验失败"},
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"code": 1, "data": None, "msg": "内部错误"},
        )
