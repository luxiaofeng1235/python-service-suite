"""
============================================
url_ — HTTP 请求与 URL 解析工具
============================================
提供通用的 HTTP GET/POST 请求封装以及基础 URL 解析能力。
文件名带下划线后缀避免与 Python 标准库 urllib 冲突。
"""

from app.core.logging import get_logger
from urllib.parse import urlparse

logger = get_logger(__name__)

# ── HTTP 请求 ────────────────────────────────

_TIMEOUT = 10  # 默认超时（秒）


def get(url: str, timeout: int = _TIMEOUT) -> str:
    """
    HTTP GET 请求，返回响应文本。
    失败时返回空字符串并记日志。
    """
    import requests
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
    import requests
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
