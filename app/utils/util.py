"""
============================================
util — 通用序列化工具（对标 Go util.go）
============================================
包含 JSON 序列化、类型安全的存储值转换。
"""

import json
from app.core.logging import get_logger
from typing import Any

logger = get_logger(__name__)


def get_bytes(val: Any) -> bytes:
    """
    将值序列化为 bytes（对标 Go GetBytes，使用 gob 编码）。
    Python 无 gob，改用 pickle 做二进制序列化。
    """
    import pickle
    try:
        return pickle.dumps(val)
    except Exception as exc:
        logger.error("get_bytes 序列化失败: %s", exc)
        return b""


def json_string(v: Any) -> str:
    """
    对象序列化为 JSON 字符串（对标 Go JSONString）。
    对标原版行为：空/None 返回提示文本，序列化失败返回错误信息。
    """
    if v is None:
        return " object is nil  of to json"
    if v == "":
        return " object is nil  of to json"
    try:
        return json.dumps(v, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as exc:
        return str(exc)


def to_storable(val: Any) -> Any:
    """
    将值转为可存储类型（对标 Go Encode）。
    基础类型（str/int/float/bool）原样返回，复杂类型转 JSON 字符串。
    """
    if val is None:
        return None
    if isinstance(val, (str, int, float, bool)):
        return val
    try:
        return json.dumps(val, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as exc:
        logger.error("序列化失败: %s", exc)
        return str(val)
