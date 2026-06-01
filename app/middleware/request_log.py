"""
============================================
请求日志中间件
============================================
主要功能：记录接口请求路径、状态码、耗时、客户端 IP 和 trace_id。
"""

import time
import uuid
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.logging import request_logger, slow_logger

SENSITIVE_KEYS = {"password", "token", "access_token", "authorization", "code"}


class RequestLogMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
        start_time = time.perf_counter()
        response: Response | None = None

        try:
            response = await call_next(request)
            return response
        except Exception:
            cost_ms = round((time.perf_counter() - start_time) * 1000, 2)
            request_logger.exception(
                "trace_id={} method={} path={} status=500 cost_ms={} client_ip={} query={}",
                trace_id,
                request.method,
                request.url.path,
                cost_ms,
                self._get_client_ip(request),
                self._masked_query(request),
            )
            raise
        finally:
            cost_ms = round((time.perf_counter() - start_time) * 1000, 2)
            status_code = response.status_code if response else 500
            client_ip = self._get_client_ip(request)

            request_logger.info(
                "trace_id={} method={} path={} status={} cost_ms={} client_ip={} query={}",
                trace_id,
                request.method,
                request.url.path,
                status_code,
                cost_ms,
                client_ip,
                self._masked_query(request),
            )

            if cost_ms >= settings.SLOW_REQUEST_MS:
                slow_logger.warning(
                    "trace_id={} method={} path={} status={} cost_ms={} client_ip={} query={}",
                    trace_id,
                    request.method,
                    request.url.path,
                    status_code,
                    cost_ms,
                    client_ip,
                    self._masked_query(request),
                )

            if response is not None:
                response.headers["X-Trace-Id"] = trace_id
                response.headers["X-Process-Time"] = f"{cost_ms}ms"

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """获取客户端 IP，优先兼容代理转发头"""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        return request.client.host if request.client else ""

    @staticmethod
    def _masked_query(request: Request) -> dict[str, str]:
        """脱敏查询参数，避免 token、密码、验证码进入日志"""
        masked: dict[str, str] = {}
        for key, value in request.query_params.items():
            masked[key] = "***" if key.lower() in SENSITIVE_KEYS else value
        return masked
