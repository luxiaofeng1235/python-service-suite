"""
============================================
接口签名验签中间件（ASGI 原生实现）
============================================
在路由之前拦截 POST/PUT 请求，完成参数排序 + SHA256 签名校验，
通过者透传原始参数给路由，不通过者直接 403 拒绝。

开关：settings.API_ENCRYPT_ENABLED（.env 配置）
"""

import json
from typing import Any, Callable

from loguru import logger
from starlette.responses import JSONResponse

from app.core.config import settings
from app.utils.crypto import verify_sign


def _should_verify(scope: dict[str, Any]) -> bool:
    """判断该请求是否需要走签名校验"""
    if not settings.API_ENCRYPT_ENABLED:
        return False
    if scope.get("method") not in ("POST", "PUT"):
        return False

    # 白名单路径跳过校验
    path = scope.get("path", scope.get("root_path", ""))
    white_list = settings.white_list
    for prefix in white_list:
        if prefix == "/" or not prefix:
            continue
        if path == prefix or path.startswith(prefix):
            return False

    # 只处理 application/json
    headers = dict(scope.get("headers", []))
    content_type = headers.get(b"content-type", b"").decode()
    if "application/json" not in content_type:
        return False
    return True


class ApiEncryptMiddleware:
    """API 请求签名校验中间件（原生 ASGI，仅校验不修改 body）"""

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
            body_chunks.append(message.get("body", b""))
            more_body = message.get("more_body", False)
        raw_body = b"".join(body_chunks)

        if not raw_body:
            await self.app(scope, receive, send)
            return

        # 2. 提取 sign + timestamp，验签
        try:
            body = json.loads(raw_body)
            sign = body.pop("sign", None)
            timestamp = body.pop("timestamp", None)
            if not sign or not timestamp:
                raise ValueError("缺少 sign 或 timestamp 参数")
            verify_sign(body, sign, settings.API_ENCRYPT_KEY, int(timestamp))
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warning("签名校验失败: {}", exc)
            response = JSONResponse(
                status_code=403,
                content={"code": -1, "msg": "签名验证失败，请求被拒绝", "data": None},
            )
            await response(scope, receive, send)
            return
        except Exception:
            logger.exception("签名校验异常")
            response = JSONResponse(
                status_code=500,
                content={"code": -1, "msg": "签名校验异常", "data": None},
            )
            await response(scope, receive, send)
            return

        # 3. 验签通过 → 把去掉 sign/timestamp 的 body 注入下游
        cleaned_body = json.dumps(body).encode("utf-8")

        async def cleaned_receive():
            return {"type": "http.request", "body": cleaned_body, "more_body": False}

        # 更新 Content-Length
        headers = scope.get("headers", [])
        new_headers = [(k, v) for k, v in headers if k.lower() != b"content-length"]
        new_headers.append((b"content-length", str(len(cleaned_body)).encode()))
        scope["headers"] = new_headers

        await self.app(scope, cleaned_receive, send)
