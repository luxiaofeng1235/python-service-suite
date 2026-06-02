"""
============================================
接口加解密中间件
============================================
根据配置决定是否对 POST/PUT 请求体进行解密验签。

启用条件（同时满足）：
    1. settings.API_ENCRYPT_ENABLED = True
    2. 请求路径不在白名单内
    3. Content-Type 为 application/json
    4. 请求方法为 POST 或 PUT
"""

import json

from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.utils.crypto import decrypt_request


# ==================== 不需要加密的白名单路径前缀 ====================
ENCRYPT_WHITE_LIST = (
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
    "/api/user/login",
    "/api/user/register",
    "/api/user/forgot-password",
    "/api/user/reset-password",
    "/api/file/upload",
)


class ApiEncryptMiddleware(BaseHTTPMiddleware):
    """API 请求加解密中间件"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # # 未开启加密 → 直接放行
        if not settings.API_ENCRYPT_ENABLED:
            return await call_next(request)

        # 白名单路径 → 放行
        path = request.url.path
        if path.startswith(ENCRYPT_WHITE_LIST):
            return await call_next(request)

        # 只拦截 POST / PUT + JSON 请求
        if request.method not in ("POST", "PUT"):
            return await call_next(request)

        content_type = request.headers.get("content-type", "")
        if "application/json" not in content_type:
            return await call_next(request)

        # 读取原始请求体
        try:
            body = await request.body()
            if not body:
                return await call_next(request)

            encrypted_data = json.loads(body)
            decrypted_params = decrypt_request(encrypted_data, settings.API_ENCRYPT_KEY)

            # 将解密后的 body 重新注入请求
            new_body = json.dumps(decrypted_params).encode("utf-8")

            # 创建新的 ASGI scope 和接收通道
            async def receive():
                return {"type": "http.request", "body": new_body, "more_body": False}

            new_request = Request(request.scope, receive=receive)
            # 保持原始请求头
            new_request._headers = MutableHeaders(request.headers)

            return await call_next(new_request)

        except ValueError as exc:
            return JSONResponse(
                status_code=403,
                content={"code": -1, "msg": f"加解密验证失败: {exc!s}", "data": None},
            )
        except json.JSONDecodeError:
            # 非加密格式 → 直接放行（兼容还没适配加密的客户端）
            return await call_next(request)
        except Exception:
            return JSONResponse(
                status_code=500,
                content={"code": -1, "msg": "加解密处理异常", "data": None},
            )
