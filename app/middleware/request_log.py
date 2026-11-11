"""
============================================
请求日志中间件
============================================
主要功能：记录接口请求路径、状态码、耗时、客户端 IP 和 trace_id。
"""

import json
import time
import uuid
from collections.abc import Callable
from urllib.parse import parse_qsl

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.pkg.logging import request_logger, slow_logger
from app.utils.url_ import get_client_ip

SENSITIVE_KEYS = {"password", "token", "access_token", "authorization", "code"}
MAX_BODY_LOG_LEN = 500  # 请求体最大日志长度


class RequestLogMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
        start_time = time.perf_counter()
        response: Response | None = None

        # 提前捕获请求体（Starlette 会缓存，不影响下游消费）
        body_str = await self._capture_body(request)
        log_body = f" body={body_str}" if body_str else ""

        try:
            response = await call_next(request)
            return response
        except Exception:
            cost_ms = round((time.perf_counter() - start_time) * 1000, 2)
            request_logger.exception(
                "trace_id={} method={} path={} status=500 cost_ms={} client_ip={} query={}{}",
                trace_id,
                request.method,
                request.url.path,
                cost_ms,
                get_client_ip(request),
                self._masked_query(request),
                log_body,
            )
            raise
        finally:
            cost_ms = round((time.perf_counter() - start_time) * 1000, 2)
            status_code = response.status_code if response else 500
            client_ip = get_client_ip(request)

            request_logger.info(
                "trace_id={} method={} path={} status={} cost_ms={} client_ip={} query={}{}",
                trace_id,
                request.method,
                request.url.path,
                status_code,
                cost_ms,
                client_ip,
                self._masked_query(request),
                log_body,
            )

            if cost_ms >= settings.SLOW_REQUEST_MS:
                slow_logger.warning(
                    "trace_id={} method={} path={} status={} cost_ms={} client_ip={} query={}{}",
                    trace_id,
                    request.method,
                    request.url.path,
                    status_code,
                    cost_ms,
                    client_ip,
                    self._masked_query(request),
                    log_body,
                )

            if response is not None:
                response.headers["X-Trace-Id"] = trace_id
                response.headers["X-Process-Time"] = f"{cost_ms}ms"

    @staticmethod
    def _masked_query(request: Request) -> dict[str, str]:
        """脱敏查询参数，避免 token、密码、验证码进入日志"""
        masked: dict[str, str] = {}
        for key, value in request.query_params.items():
            masked[key] = "***" if key.lower() in SENSITIVE_KEYS else value
        return masked

    @staticmethod
    def _mask_body(data: object) -> object:
        """Mask sensitive fields at every JSON nesting level."""
        if isinstance(data, dict):
            return {
                key: "***" if key.lower() in SENSITIVE_KEYS else RequestLogMiddleware._mask_body(value)
                for key, value in data.items()
            }
        if isinstance(data, list):
            return [RequestLogMiddleware._mask_body(value) for value in data]
        return data

    @staticmethod
    async def _capture_body(request: Request) -> str:
        """Parse and mask structured bodies before limiting log length."""
        if request.method in ("GET", "HEAD", "DELETE"):
            return ""

        content_type = request.headers.get("content-type", "").lower()
        # 文件上传不记 body
        if "multipart/form-data" in content_type:
            return "<multipart>"

        try:
            raw = await request.body()
        except Exception:
            return "<read_error>"

        if not raw:
            return ""

        # 完整解析后再脱敏，不能截断原文后回退记录敏感内容。
        media_type = content_type.split(";", 1)[0].strip()
        try:
            if media_type == "application/json" or media_type.endswith("+json"):
                data = json.loads(raw)
            elif media_type == "application/x-www-form-urlencoded":
                data = dict(parse_qsl(raw.decode("utf-8"), keep_blank_values=True, errors="strict"))
            else:
                return "<unlogged_body>"
            body_str = json.dumps(RequestLogMiddleware._mask_body(data), ensure_ascii=False)
        except (ValueError, UnicodeError, RecursionError):
            return "<invalid_body>"

        if len(body_str) > MAX_BODY_LOG_LEN:
            return body_str[:MAX_BODY_LOG_LEN - 3] + "..."
        return body_str
