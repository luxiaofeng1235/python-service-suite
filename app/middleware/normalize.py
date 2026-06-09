"""
============================================
404 统一响应中间件 + 路径归一化
============================================
- 路径归一化：连续斜杠 // 转为单斜杠 /
- 404 拦截：未匹配路由返回统一 JSON 格式

注册在最外层（最后注册），最早处理请求和响应。
"""

import re

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.status import HTTP_404_NOT_FOUND


class NotFoundMiddleware(BaseHTTPMiddleware):
    """
    拦截 404 Not Found，返回统一 JSON 格式。
    同时将路径中的连续斜杠归一化（如 //api/user/center → /api/user/center）。
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        # --- 路径归一化 ---
        original_path = request.url.path
        normalized = re.sub(r"/{2,}", "/", original_path)
        if normalized != original_path:
            request.scope["path"] = normalized
            request.scope["raw_path"] = normalized.encode()

        response = await call_next(request)

        # --- 404 统一 JSON ---
        if response.status_code == HTTP_404_NOT_FOUND:
            return JSONResponse(
                content={"code": 404, "msg": "Not Found", "data": None},
                status_code=404,
            )
        return response
