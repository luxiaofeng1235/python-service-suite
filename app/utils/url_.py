"""
============================================
url_ — URL 解析与客户端 IP 获取
============================================
提供基础的 URL 解析能力，以及从 HTTP 请求中提取真实客户端 IP。
文件名带下划线后缀避免与 Python 标准库 urllib 冲突。

注意：同步 requests 调用已移除（会阻塞 FastAPI 事件循环）。
如需 HTTP 调用请直接使用 httpx.AsyncClient（项目其它位置已统一）。
"""

from urllib.parse import urlparse

from fastapi import Request
from starlette.requests import Request as StarletteRequest

from app.pkg.logging import get_logger

logger = get_logger(__name__)


# ── URL 解析 ────────────────────────────────


def get_domain(link_url: str) -> str:
    """从完整 URL 提取 scheme + hostname，例如 ``https://www.example.com``。"""
    if not link_url:
        return ""
    try:
        parsed = urlparse(link_url)
        return f"{parsed.scheme}://{parsed.hostname}"
    except Exception as exc:
        logger.error("URL 解析失败: {}", exc)
        return ""


def get_last_segment(url_path: str) -> str:
    """
    取 URL 路径最后一段。
    例: ``/book/123/chapter/456`` → ``456``
    """
    idx = url_path.rstrip("/").rfind("/")
    if idx == -1:
        return url_path
    return url_path[idx + 1:]


# ── 客户端 IP ────────────────────────────────


def get_client_ip(request: Request | StarletteRequest) -> str:
    """
    从请求中提取真实客户端 IP，优先兼容代理转发头。

    Args:
        request: FastAPI / Starlette 请求对象

    Returns:
        客户端 IP 字符串，空串表示无法获取
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    return request.client.host if request.client else ""
