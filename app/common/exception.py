"""
============================================
全局异常处理模块
============================================
自定义异常类 + 全局异常捕获，保证所有异常返回统一格式。

已在 main.py 中注册全局处理器，覆盖：
    - AppException（自定义业务异常）
    - HTTPException（FastAPI 原生）
    - ValidationError（Pydantic 校验）
    - Exception（兜底）
"""

from typing import Any

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.common.response import Response
from app.pkg.logging import app_logger

# ==================== 自定义异常基类 ====================


class AppException(Exception):
    """自定义业务异常基类"""

    def __init__(self, msg: str = "业务异常", code: int = 0, data: Any | None = None):
        self.msg = msg
        self.code = code
        self.data = data
        super().__init__(self.msg)


# ==================== 全局异常处理器 ====================


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """捕获自定义 AppException，返回统一业务失败格式"""
    return Response.fail(msg=exc.msg, code=exc.code, data=exc.data)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    捕获 FastAPI HTTPException
    将 status_code 映射到统一响应格式
    """
    return JSONResponse(
        content={
            "code": exc.status_code,
            "msg": exc.detail,
            "data": None,
        },
        status_code=exc.status_code,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    捕获 Pydantic 参数校验异常
    将详细错误信息合并为可读的字符串
    """
    errors = exc.errors()
    # 提取所有校验错误信息
    error_messages = []
    for err in errors:
        field = ".".join(str(loc) for loc in err.get("loc", []))
        msg = err.get("msg", "")
        if field:
            error_messages.append(f"{field}: {msg}")
        else:
            error_messages.append(msg)

    return JSONResponse(
        content={
            "code": 422,
            "msg": "参数校验失败: " + "; ".join(error_messages),
            "data": errors,
        },
        status_code=422,
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底异常处理器 — 捕获所有未预期的异常"""
    app_logger.opt(exception=exc).error(
        "Unhandled exception path={} method={}", request.url.path, request.method,
    )
    return JSONResponse(
        content={
            "code": -1,
            "msg": f"服务器内部错误: {exc!s}",
            "data": None,
        },
        status_code=500,
    )
