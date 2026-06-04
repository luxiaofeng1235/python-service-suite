"""
============================================
url_ — HTTP 请求、URL 解析、客户端 IP 获取
============================================
提供通用的 HTTP GET/POST 请求封装、基础 URL 解析能力以及客户端 IP 提取。
文件名带下划线后缀避免与 Python 标准库 urllib 冲突。
"""

from fastapi import Request
from starlette.requests import Request as StarletteRequest

from app.pkg.logging import get_logger
from urllib.parse import urlparse
import requests

logger = get_logger(__name__)

# ── HTTP 请求 ────────────────────────────────

_TIMEOUT = 10  # 默认超时（秒）


def get(url: str, timeout: int = _TIMEOUT) -> str:
    """
    HTTP GET 请求，返回响应文本。
    失败时返回空字符串并记日志。
    """

    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        logger.error("GET 失败 url=%s, err=%s", url, exc)
        return ""


def post(url: str, data: dict = None, json: dict = None,
         timeout: int = _TIMEOUT) -> str:
    """
    HTTP POST 请求，返回响应文本。
    可传 form data 或 json body，失败时返回空字符串。
    """
    try:
        resp = requests.post(url, data=data, json=json, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        logger.error("POST 失败 url=%s, err=%s", url, exc)
        return ""


# ── URL 解析 ────────────────────────────────


def get_domain(link_url: str) -> str:
    """从完整 URL 提取 scheme + hostname，例如 ``https://www.example.com``。"""
    if not link_url:
        return ""
    try:
        parsed = urlparse(link_url)
        return f"{parsed.scheme}://{parsed.hostname}"
    except Exception as exc:
        logger.error("URL 解析失败: %s", exc)
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
