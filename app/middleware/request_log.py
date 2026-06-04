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

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.core.logging import request_logger, slow_logger
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
    def _mask_body_dict(data: dict) -> dict:
        """递归脱敏 JSON body 中的敏感字段"""
        masked: dict = {}
        for key, value in data.items():
            if key.lower() in SENSITIVE_KEYS:
                masked[key] = "***"
            elif isinstance(value, dict):
                masked[key] = RequestLogMiddleware._mask_body_dict(value)
            elif isinstance(value, list):
                masked[key] = [
                    RequestLogMiddleware._mask_body_dict(v) if isinstance(v, dict) else v
                    for v in value
                ]
            else:
                masked[key] = value
        return masked

    @staticmethod
    async def _capture_body(request: Request) -> str:
        """捕获请求体（JSON / form / raw），脱敏后截断返回字符串"""
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

        # 截断大 body
        raw_str = raw.decode("utf-8", errors="replace")
        if len(raw_str) > MAX_BODY_LOG_LEN:
            raw_str = raw_str[:MAX_BODY_LOG_LEN] + "..."

        # JSON body → 脱敏后返回
        if "application/json" in content_type:
            try:
                data = json.loads(raw_str)
                if isinstance(data, dict):
                    data = RequestLogMiddleware._mask_body_dict(data)
                return json.dumps(data, ensure_ascii=False)
            except json.JSONDecodeError:
                pass  # 非标准 JSON，回退原始字符串

        # form-urlencoded → 脱敏后返回
        if "application/x-www-form-urlencoded" in content_type:
            try:
                from urllib.parse import parse_qsl

                params = dict(parse_qsl(raw_str))
                for key in params:
                    if key.lower() in SENSITIVE_KEYS:
                        params[key] = "***"
                return json.dumps(params, ensure_ascii=False)
            except Exception:
                pass

        return raw_str
