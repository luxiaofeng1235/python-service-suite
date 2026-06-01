"""
============================================
调试工具模块,方便快速开发测试调试
============================================
用法：
    from app.common.debug import debug

    @router.get("/users/{user_id}")
    async def get_user(user_id: int):
        user = await user_service.get_by_id(user_id)
        return debug(user)  # 👈 终端打印 + 浏览器返回 JSON，一行搞定
"""

import json
from typing import Any

from fastapi.responses import JSONResponse


def debug(*objs: Any) -> JSONResponse:
    """
    PHP var_dump + exit 复刻。

    终端打印变量结构，浏览器返回 JSON 展示。
    FastAPI 里直接 return debug(variable1, variable2, ...) 即可。

    Args:
        *objs: 一个或多个任意 Python 变量

    Returns:
        JSONResponse: 单个变量返回 JSON 对象，多个返回数组
    """
    for obj in objs:
        _print(obj)
    if len(objs) == 1:
        return JSONResponse(content=_to_json(objs[0]))
    return JSONResponse(content=[_to_json(obj) for obj in objs])


def _print(obj: Any, indent: int = 0) -> None:
    """终端打印（递归展开对象）"""
    prefix = "  " * indent
    if isinstance(obj, dict):
        print(f"{prefix}dict ({len(obj)} keys):")
        for k, v in obj.items():
            print(f"{prefix}  {k} => ", end="")
            _print(v, indent + 1)
    elif isinstance(obj, list):
        print(f"{prefix}list ({len(obj)} items):")
        for i, item in enumerate(obj):
            print(f"{prefix}  [{i}] => ", end="")
            _print(item, indent + 1)
    elif hasattr(obj, "_sa_instance_state"):
        # SQLAlchemy ORM 模型 — 只取表字段，跳过 _sa_instance_state 等内部属性
        col_names = [c.name for c in obj.__table__.columns]
        print(f"{prefix}SQLAlchemy [{type(obj).__name__}] ({len(col_names)} fields):")
        _print({k: getattr(obj, k) for k in col_names}, indent + 1)
    elif hasattr(obj, "dict"):
        print(f"{prefix}Pydantic:")
        _print(obj.dict(), indent + 1)
    elif hasattr(obj, "__dict__"):
        print(f"{prefix}{type(obj).__name__}:")
        _print(obj.__dict__, indent + 1)
    else:
        print(f"{prefix}{obj!r}")


def _to_json(obj: Any) -> Any:
    """递归序列化任意对象为 JSON 安全格式"""
    if hasattr(obj, "_sa_instance_state"):
        col_names = [c.name for c in obj.__table__.columns]
        return _to_json({k: getattr(obj, k) for k in col_names})
    if hasattr(obj, "dict"):
        return _to_json(obj.dict())
    if hasattr(obj, "__dict__"):
        return _to_json(obj.__dict__)
    if isinstance(obj, (list, tuple)):
        return [_to_json(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_json(v) for k, v in obj.items()}
    # 尝试直接序列化，失败则转字符串
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)
