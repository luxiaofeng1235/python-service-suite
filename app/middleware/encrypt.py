"""
============================================
接口签名验签中间件（ASGI 原生实现）
============================================
在路由之前拦截 POST/PUT 请求，完成参数排序 + SHA256 签名校验，
通过者透传原始参数给路由，不通过者直接 403 拒绝。

开关：settings.API_ENCRYPT_ENABLED（.env 配置）
"""

import json
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qsl, urlencode

from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.dependency import match_white_list
from app.pkg.logging import app_logger
from app.utils.crypto import verify_sign


def _should_verify(scope: dict[str, Any]) -> bool:
    """判断该请求是否需要走签名校验"""
    if not settings.API_ENCRYPT_ENABLED:
        return False
    if scope.get("method") not in ("POST", "PUT"):
        return False

    # 白名单路径跳过校验（复用 dependency 的纯路径匹配，
    # 避免 startswith(prefix) 不带 "/" 边界导致 /api/user/loginabc 被误匹配）
    path = scope.get("path", scope.get("root_path", ""))
    if match_white_list(path):
        return False

    return True


class ApiEncryptMiddleware:
    """Verify JSON and form signatures and preserve ASGI disconnect events."""

    def __init__(self, app: Callable):
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Callable, send: Callable) -> None:
        if scope["type"] != "http" or not _should_verify(scope):
            await self.app(scope, receive, send)
            return

        # 1. 读取完整 body
        body_chunks: list[bytes] = []
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body_chunks.append(message.get("body", b""))
            more_body = message.get("more_body", False)
        raw_body = b"".join(body_chunks)

        # 2. 提取 sign + timestamp，验签
        try:
            body, media_type = await self._parse_body(scope, raw_body)
            sign = body.pop("sign", None)
            timestamp = body.pop("timestamp", None)
            if not isinstance(sign, str) or not sign or isinstance(timestamp, bool) or not timestamp:
                raise ValueError("缺少 sign 或 timestamp 参数")
            verify_sign(body, sign, settings.API_ENCRYPT_KEY, int(timestamp))
        except (ValueError, TypeError, UnicodeError, HTTPException):
            app_logger.warning("签名校验失败 path={}", scope.get("path"))
            response = JSONResponse(
                status_code=403,
                content={"code": -1, "msg": "签名验证失败，请求被拒绝", "data": None},
            )
            await response(scope, receive, send)
            return
        except Exception:
            app_logger.exception("签名校验异常")
            response = JSONResponse(
                status_code=500,
                content={"code": -1, "msg": "签名校验异常", "data": None},
            )
            await response(scope, receive, send)
            return

        # 3. 验签通过 → 把去掉 sign/timestamp 的 body 注入下游
        if media_type == "multipart/form-data":
            # 文件与 boundary 保持原样，签名仅覆盖文本字段，文件仍由上传服务校验。
            cleaned_body = raw_body
        elif media_type == "application/x-www-form-urlencoded":
            cleaned_body = urlencode(body).encode("utf-8")
        else:
            cleaned_body = json.dumps(body).encode("utf-8")

        body_sent = False

        async def cleaned_receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": cleaned_body, "more_body": False}
            return await receive()

        # 更新 Content-Length
        headers = scope.get("headers", [])
        new_headers = [(k, v) for k, v in headers if k.lower() != b"content-length"]
        new_headers.append((b"content-length", str(len(cleaned_body)).encode()))
        scope["headers"] = new_headers

        await self.app(scope, cleaned_receive, send)

    @staticmethod
    async def _parse_body(scope: dict[str, Any], raw_body: bytes) -> tuple[dict, str]:
        """Read unique signed fields; binary multipart files are not signed."""
        headers = dict(scope.get("headers", []))
        media_type = headers.get(b"content-type", b"").decode().split(";", 1)[0].strip().lower()
        if media_type == "application/json" or media_type.endswith("+json"):
            body = json.loads(raw_body)
            if not isinstance(body, dict):
                raise ValueError("签名请求体必须为 JSON 对象")
            return body, media_type

        if media_type == "application/x-www-form-urlencoded":
            pairs = parse_qsl(raw_body.decode("utf-8"), keep_blank_values=True, errors="strict")
        elif media_type == "multipart/form-data":
            async def replay_body():
                return {"type": "http.request", "body": raw_body, "more_body": False}

            async with Request(scope, replay_body).form() as form:
                pairs = [(key, value) for key, value in form.multi_items() if not isinstance(value, UploadFile)]
        else:
            raise ValueError("验签请求仅支持 JSON 或表单")

        body = dict(pairs)
        if len(body) != len(pairs):
            raise ValueError("签名表单不允许重复字段")
        return body, media_type
