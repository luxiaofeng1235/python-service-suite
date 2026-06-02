"""
============================================
统一响应工具模块
============================================
所有接口必须通过 Response 工具类返回数据，禁止直接 return dict。

统一响应格式：
    - 成功：{"code": 1, "msg": "ok", "data": ...}
    - 失败（业务错误）：{"code": 0, "msg": "用户不存在"}
    - 错误（系统异常）：{"code": -1, "msg": "服务器内部错误"}

使用方式：
    return Response.success(data)
    return Response.error("参数错误")
    return Response.fail("用户已被禁用", code=1001)
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi.responses import JSONResponse
from pydantic import BaseModel


def _serialize(obj: Any) -> Any:
    """递归序列化对象，支持 Pydantic BaseModel、SQLAlchemy ORM、列表、字典、日期等"""
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {key: _serialize(value) for key, value in obj.items()}
    if isinstance(obj, datetime):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    # SQLAlchemy ORM 对象 → 转 dict
    if hasattr(obj, "_sa_instance_state"):
        cols = getattr(obj, "__table__", None)
        if cols is not None:
            return {col.name: _serialize(getattr(obj, col.name)) for col in cols.columns}
        return str(obj)
    return obj


class Response:
    """统一响应工具类 — 全局唯一响应出口"""

    # ==================== 状态码常量 ====================
    SUCCESS_CODE: int = 1
    """成功状态码"""
    FAIL_CODE: int = 0
    """业务失败状态码"""
    ERROR_CODE: int = -1
    """系统错误状态码"""

    # ==================== 成功响应 ====================

    @staticmethod
    def success(data: Any = None, msg: str = "ok") -> JSONResponse:
        """
        成功响应

        Args:
            data: 返回的数据（自动处理 Pydantic 模型序列化）
            msg: 成功消息

        Returns:
            JSONResponse: {"code": 1, "msg": "ok", "data": ...}
        """
        return JSONResponse(
            content={
                "code": Response.SUCCESS_CODE,
                "msg": msg,
                "data": _serialize(data),
            }
        )

    # ==================== 业务失败响应 ====================

    @staticmethod
    def fail(msg: str = "fail", code: int = FAIL_CODE, data: Any = None) -> JSONResponse:
        """
        业务失败响应（如：用户名已存在、余额不足等）

        Args:
            msg: 失败描述
            code: 业务错误码（默认 0）
            data: 附加数据（可选）

        Returns:
            JSONResponse: {"code": 0, "msg": "...", "data": ...}
        """
        return JSONResponse(
            content={
                "code": code,
                "msg": msg,
                "data": data,
            },
            status_code=200,  # 业务错误仍返回 200，由 code 区分
        )

    # ==================== 系统错误响应 ====================

    @staticmethod
    def error(msg: str = "服务器内部错误", code: int = ERROR_CODE) -> JSONResponse:
        """
        系统错误响应（如：数据库异常、IO 错误等）

        Args:
            msg: 错误描述
            code: 错误码（默认 -1）

        Returns:
            JSONResponse: {"code": -1, "msg": "..."}
        """
        return JSONResponse(
            content={
                "code": code,
                "msg": msg,
                "data": None,
            },
            status_code=500,
        )
