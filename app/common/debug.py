"""
============================================
调试工具模块 — PHP var_dump + exit 风味
============================================
调试时用 dd() 替代 print + return，不用写两行。

用法：
    from app.common.debug import dd
    dd(variable)

效果：
    - 终端打印变量
    - 浏览器返回 JSON 展示变量内容
    - 进程不挂，不影响后续请求
"""

from typing import Any

from fastapi.responses import JSONResponse


def dd(obj: Any) -> JSONResponse:
    """
    PHP var_dump + exit 复刻，但不杀进程。

    Args:
        obj: 要调试的变量

    Returns:
        JSONResponse: 直接 return 给 FastAPI
    """
    print(obj)
    return JSONResponse(content=_to_debug(obj))


def _to_debug(obj: Any) -> Any:
    """将任意对象转为可 JSON 序列化的格式"""
    if hasattr(obj, "dict"):  # Pydantic model
        return obj.dict()
    if hasattr(obj, "__dict__"):  # ORM / dataclass / 普通对象
        return _to_debug(obj.__dict__)
    if isinstance(obj, list):
        return [_to_debug(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _to_debug(v) for k, v in obj.items()}
    try:
        # 测试是否能被 json.dumps 直接处理
        import json

        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)
