"""
============================================
Qwen Task Client - shared DashScope task requests
============================================
Centralize authentication, HTTP requests, task polling and upstream error handling.
"""

from typing import Any, Literal
from urllib.parse import quote

import httpx

from app.common.exception import AppException
from app.core.config import settings


TaskMediaType = Literal["图片", "视频"]


class QwenTaskClient:
    """Shared DashScope client for image and video generation tasks."""

    _COMMON_ERRORS = {
        "DataInspectionFailed": "敏感内容，生成失败",
        "data_inspection_failed": "敏感内容，生成失败",
        "IPInfringementSuspect": "IP侵权，生成失败",
    }
    # 错误码集中维护，保留图片和视频原有的提示文案。
    _MEDIA_ERRORS = {
        "图片": {
            "InvalidParameter": "AI 服务器错误，请联系客服处理或稍后再试",
            "APIConnectionError": "AI 服务器网络出错，请稍后再试",
            "invalid_request_error": "AI 服务器错误，请联系客服处理或稍后再试",
        },
        "视频": {
            "InvalidParameter": "AI 请求参数错误，请联系客服处理",
            "InvalidApiKey": "AI 服务认证失败，请检查后端配置",
            "ModelNotFound": "视频模型不存在或当前账号无权限",
            "APIConnectionError": "AI 服务器网络出错，请稍后重试",
        },
    }

    @classmethod
    async def request(
        cls,
        method: Literal["GET", "POST"],
        url: str,
        *,
        media_type: TaskMediaType,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call a task endpoint with backend credentials and validate its output."""
        if not settings.QWEN_API_KEY:
            raise AppException(msg="QWEN_API_KEY 未配置")
        if not url:
            raise AppException(msg=f"千问{media_type}服务地址未配置")

        headers = {"Authorization": f"Bearer {settings.QWEN_API_KEY}"}
        # 异步任务头只用于提交；查询任务时使用普通 GET 请求。
        if method == "POST":
            headers.update({"Content-Type": "application/json", "X-DashScope-Async": "enable"})
        retry = "再试" if media_type == "图片" else "重试"
        format_error = f"{media_type}服务返回格式错误，请稍后{retry}"
        try:
            async with cls._create_client() as client:
                response = await client.request(method, url, headers=headers, json=payload)
            data = response.json()
        except httpx.HTTPError as exc:
            raise AppException(msg=f"{media_type}服务网络出错，请稍后{retry}") from exc
        except ValueError as exc:
            raise AppException(msg=format_error) from exc

        if not isinstance(data, dict):
            raise AppException(msg=format_error)
        if response.is_error or data.get("code"):
            prefix = f"{media_type}生成失败" if method == "POST" else f"{media_type}任务查询失败"
            raise AppException(
                msg=f"{prefix}，{cls.error_message(data.get('code'), media_type=media_type)}"
            )
        if not isinstance(data.get("output"), dict):
            raise AppException(msg=format_error)
        return data

    @classmethod
    async def get_task(cls, task_id: str, *, media_type: TaskMediaType) -> dict[str, Any]:
        """Query a task using the configured endpoint and an escaped task ID."""
        if not settings.QWEN_TASK_URL:
            raise AppException(msg="QWEN_TASK_URL 未配置")
        url = f"{settings.QWEN_TASK_URL.rstrip('/')}/{quote(task_id, safe='')}"
        return await cls.request("GET", url, media_type=media_type)

    @staticmethod
    def _create_client() -> httpx.AsyncClient:
        """Create an asynchronous task client with the shared timeout policy."""
        return httpx.AsyncClient(
            timeout=httpx.Timeout(settings.QWEN_REQUEST_TIMEOUT, connect=settings.QWEN_CONNECT_TIMEOUT),
            trust_env=False,
        )

    @classmethod
    def error_message(cls, code: str | None, *, media_type: TaskMediaType) -> str:
        """Translate an upstream error code without returning its raw message."""
        retry = "再试" if media_type == "图片" else "重试"
        default = f"服务错误，请稍后{retry}"
        if not isinstance(code, str):
            return default
        return cls._MEDIA_ERRORS[media_type].get(code, cls._COMMON_ERRORS.get(code, default))
