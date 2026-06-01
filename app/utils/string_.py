"""
============================================
string_ — 字符串工具（对标 Go string.go）
============================================
注意：文件名带下划线后缀避免与 Python 标准库 string 冲突。
"""

from app.core.logging import get_logger

logger = get_logger(__name__)


def join_int_str(nums: list[int], sep: str = ", ") -> str:
    """
    整数列表拼接为字符串（对标 Go JoinInt64ToString）。
    例: [1, 2, 3] → "1, 2, 3"
    """
    return sep.join(str(n) for n in nums)


def remove_trailing_eq(s: str) -> str:
    """
    移除末尾的 = 号（对标 Go RemoveEqualSigns）。
    先检查 == 再检查单个 =，只移除一次。
    """
    if not s:
        return ""

    n = len(s)
    if n > 1 and s[n - 2] == "=" and s[n - 1] == "=":
        new_str = s[: n - 2]
        logger.debug("移除末尾两个 =: %s -> %s", s, new_str)
        return new_str
    if s[n - 1] == "=":
        new_str = s[: n - 1]
        logger.debug("移除末尾一个 =: %s -> %s", s, new_str)
        return new_str

    logger.debug("无尾部 = 号: %s", s)
    return s
