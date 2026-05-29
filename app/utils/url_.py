"""
============================================
url_ — URL/路径处理工具（对标 Go url.go）
============================================
对标 Go url.go 全部导出函数，适配 FastAPI / Python 环境。
注意：文件名带下划线后缀避免与 Python 标准库 urllib 冲突。
"""

import logging
import re
from urllib.parse import urlparse, unquote
from fastapi import Request

logger = logging.getLogger(__name__)

# ── 常量（对标 Go 全局变量，调用方可根据项目需要覆写） ──

# 默认图片路径
DEFAULT_PIC = "/static/images/default.png"
# 需要被替换的文件夹名
REPLACE_FOLDER = "/upload/"
# 文件存储根目录
STORAGE_ROOT = "/data/www/storage"


# ── 上下文相关（依赖 Request） ──────────────────────────────


def get_scheme(request: Request) -> str:
    """
    获取请求协议（对标 Go GetScheme）。
    优先读取 X-Forwarded-Proto 请求头，其次从 request.url 获取。
    """
    if scheme := request.headers.get("X-Forwarded-Proto"):
        return scheme
    if request.url.scheme:
        return request.url.scheme
    return "http"


def get_site(request: Request) -> str:
    """
    获取站点基础 URL（对标 Go GetSite）。
    例: http://www.example.com
    """
    return f"{get_scheme(request)}://{request.url.hostname}"


# ── 配置相关（对标 viper 读取） ────────────────────────────


def get_down_url() -> str:
    """
    获取下载域名（对标 Go GetDownUrl）。
    调用方可自行设置 app.state.down_url，或返回空字符串。
    """
    # 使用时可在 FastAPI 应用层设置 request.app.state.down_url
    return ""


def get_api_url() -> str:
    """
    获取 API 基础 URL（对标 Go GetApiUrl，兼容旧 api.apiUrl）。
    """
    return ""


def get_api_encrypt() -> bool:
    """
    是否启用 API 加密（对标 Go GetApiEncrypt）。
    """
    return False


def get_source_public_base_url() -> str:
    """
    获取静态资源对外访问域名（对标 Go GetSourcePublicBaseUrl）。
    """
    return ""


def get_source_base_url() -> str:
    """
    获取静态资源服务基础域名（对标 Go GetSourceBaseUrl）。
    优先 publicBaseUrl，其次 apiUrl + port 组合。
    """
    base = get_source_public_base_url()
    if base:
        return base.rstrip("/")

    api_url = ""  # 可替换为实际的 source.apiUrl
    source_port = ""  # 可替换为实际的 source.port
    if not api_url:
        api_url = get_api_url()
    if not api_url:
        return ""

    parsed = urlparse(api_url)
    host = api_url.rstrip("/")

    if not parsed.scheme or not parsed.host:
        if source_port and ":" not in host:
            host = f"{host}:{source_port}"
        return host

    if source_port and not parsed.port:
        parsed = parsed._replace(netloc=f"{parsed.hostname}:{source_port}")

    base_path = parsed.path.rstrip("/")
    if base_path in ("", "."):
        base_path = ""

    result = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        result = f"{result}:{parsed.port}"
    return f"{result}{base_path}".rstrip("/")


def get_admin_url() -> str:
    """
    获取管理后台基础 URL（对标 Go GetAdminUrl）。
    """
    return get_source_base_url()


# ── 文件路径处理 ──────────────────────────────────────────


def _file_exists(path: str) -> bool:
    """检查文件是否存在（对标 Go FileExist）"""
    import os
    return os.path.isfile(path)


def _is_pic(path: str) -> bool:
    """判断是否为图片文件（对标 Go IsPic）"""
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return ext in ("jpg", "jpeg", "png", "gif", "webp", "bmp", "svg")


def get_file_url(path: str) -> str:
    """
    拼接文件完整 URL（对标 Go GetFileUrl）。
    如果 path 以 http 开头则原样返回。
    """
    if path.startswith("http"):
        return path

    if not path:
        return ""

    base = get_source_base_url()
    if not base:
        base = get_api_url()
    if not base:
        return path

    file_url = f"{base}{path}"

    if not _file_exists(path):
        file_url = f"{base}{DEFAULT_PIC}"
    elif path.endswith(".apk"):
        file_url = f"{base}{path}"
    elif not _is_pic(path):
        file_url = f"{base}{DEFAULT_PIC}"

    return file_url.replace(REPLACE_FOLDER, "")


def parse_local_url(path: str) -> str:
    """
    解析本地路径（对标 Go ParseLocalUrl）。
    当前直接返回原路径。
    """
    return path


def get_admin_file_url(path: str) -> str:
    """
    获取管理后台文件完整 URL（对标 Go GetAdminFileUrl）。
    """
    is_http = path.startswith("http")
    spath = path
    path = parse_local_url(path)
    source_base = get_source_base_url()

    if is_http:
        return spath

    if not path:
        return ""

    file_url = f"{source_base}{spath}"

    if not _file_exists(path):
        file_url = f"{source_base}{DEFAULT_PIC}"
        return file_url

    if path.endswith(".apk"):
        file_url = f"{source_base}{spath}"
        return file_url

    if not _is_pic(path):
        file_url = f"{source_base}{DEFAULT_PIC}"
        return file_url

    return file_url.replace(REPLACE_FOLDER, "")


def get_url_last_number(url_path: str) -> int:
    """
    取 URL 路径中倒数第二段并转为整数（对标 Go GetLastNumber）。
    例: "/book/123/chapter/456" → 123（倒数第二段）
    """
    segments = url_path.strip("/").split("/")
    if len(segments) < 2:
        return 0
    try:
        return int(segments[-2])
    except (ValueError, IndexError):
        return 0


def get_url_domain(link_url: str) -> str:
    """
    从完整 URL 提取 scheme + hostname（对标 Go GetUrlDomain）。
    """
    if not link_url:
        return ""
    try:
        parsed = urlparse(link_url)
        return f"{parsed.scheme}://{parsed.hostname}"
    except Exception as exc:
        logger.error("URL 解析失败: %s", exc)
        return ""


def get_url_book_num(book_url: str) -> str:
    """
    从 URL 中提取最后一段数字（对标 Go GetUrlBookNum）。
    例: "https://example.com/book/12345.html" → "12345"
    """
    if not book_url:
        return ""
    matches = re.findall(r"\d+", book_url)
    return matches[-1] if matches else ""


def get_url_suffix(url_path: str) -> str:
    """
    取 URL 路径最后一段（对标 Go GetUrlSuffix）。
    例: "/book/123/chapter/456" → "456"
    """
    idx = url_path.rstrip("/").rfind("/")
    if idx == -1:
        return url_path
    return url_path[idx + 1:]


def get_replace_callback(callback_url: str, atype: int, source: str) -> str:
    """
    拼装神马搜索回调字段（对标 Go GetReplaceChaojihuiCallbak）。

    :param callback_url: 回调 URL
    :param atype: 类型，1=激活(imei_sum)，其他=留存(idfa)
    :param source: 渠道标识
    :return: 拼接后的完整回调 URL
    """
    import time
    if not callback_url:
        return ""
    decoded = unquote(callback_url)
    url_str = "imei_sum" if atype == 1 else "idfa"
    return f"{decoded}&type={atype}&{url_str}=&event_time={int(time.time())}&source="


def get_http_response(url: str) -> str:
    """
    GET 请求获取 URL 内容（对标 Go GetHttpResponse）。
    """
    import requests
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        text = resp.text
        logger.info("GET url=【%s】 Response body: %s", url, text[:200])
        return text
    except Exception as exc:
        logger.error("GET 请求失败 url=%s, err=%s", url, exc)
        return ""
