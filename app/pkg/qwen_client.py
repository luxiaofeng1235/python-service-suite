"""
============================================
千问任务客户端 - 图片与视频共用的 DashScope SDK 适配
============================================
集中处理后端鉴权、异步任务提交与查询，转换 SDK 返回值和错误，保持现有业务协议。
"""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, ClassVar, Literal
from urllib.parse import quote, urlsplit

import anyio
import httpx
from dashscope import AsyncClient
from dashscope.errors import APIConnectionError, DashScopeError
from dashscope.resources._jobs import Job

from app.common.exception import AppException
from app.core.config import settings

TaskMediaType = Literal["图片", "视频"]


class QwenTaskClient:
    """复用 DashScope 异步客户端，供图片和视频业务提交、查询任务。"""

    _SUBMIT_PATHS: ClassVar[dict[TaskMediaType, str]] = {
        "图片": "/services/aigc/text2image/image-synthesis",
        "视频": "/services/aigc/video-generation/video-synthesis",
    }

    _COMMON_ERRORS: ClassVar[dict[str, str]] = {
        "DataInspectionFailed": "敏感内容，生成失败",
        "data_inspection_failed": "敏感内容，生成失败",
        "IPInfringementSuspect": "IP侵权，生成失败",
    }
    # 错误码集中维护，保留图片和视频原有的提示文案。
    _MEDIA_ERRORS: ClassVar[dict[TaskMediaType, dict[str, str]]] = {
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
        """调用 SDK 的 create 或 fetch，返回业务层沿用的 output 结构。"""
        if not settings.QWEN_API_KEY:
            raise AppException(msg="QWEN_API_KEY 未配置")
        if not url:
            raise AppException(msg=f"千问{media_type}服务地址未配置")

        retry = "再试" if media_type == "图片" else "重试"
        format_error = f"{media_type}服务返回格式错误，请稍后{retry}"
        prefix = f"{media_type}生成失败" if method == "POST" else f"{media_type}任务查询失败"
        if method == "POST":
            base_url = cls._base_url(url, cls._SUBMIT_PATHS[media_type])
        else:
            task_url, separator, encoded_task_id = url.rpartition("/tasks/")
            if not separator or not encoded_task_id:
                raise AppException(msg="QWEN_TASK_URL 必须配置完整的 /tasks 接口地址")
            base_url = cls._base_url(task_url + "/tasks", "/tasks")

        # SDK 的单次请求接受 HTTPX 超时配置，保留独立的连接超时。
        timeout = httpx.Timeout(
            settings.QWEN_REQUEST_TIMEOUT, connect=settings.QWEN_CONNECT_TIMEOUT
        )
        try:
            async with cls._create_client(base_url) as client:
                jobs = client.images.jobs if media_type == "图片" else client.videos.jobs
                if method == "POST":
                    job = await jobs.create(
                        model=payload["model"],
                        prompt=payload["input"]["prompt"],
                        parameters=payload.get("parameters"),
                        timeout=timeout,
                    )
                else:
                    # get_task 已转义任务 ID；直接传递，避免 SDK 拼接时引入路径或查询参数。
                    job = await jobs.fetch(encoded_task_id, timeout=timeout)
                return cls._normalize_job(job, format_error)
        except (APIConnectionError, httpx.HTTPError) as exc:
            raise AppException(msg=f"{media_type}服务网络出错，请稍后{retry}") from exc
        except DashScopeError as exc:
            # SDK 会将 FAILED 任务当作异常。恢复 HTTP 200 的任务快照，交由业务层落库失败状态。
            body = exc.body
            output = body.get("output") if isinstance(body, dict) else None
            if (
                method == "GET"
                and exc.status_code == 200
                and isinstance(output, dict)
                and not body.get("code")
                and output.get("task_status") in {"FAILED", "CANCELED", "UNKNOWN"}
            ):
                return body
            if not isinstance(body, dict) or isinstance(exc.__cause__, ValueError):
                raise AppException(msg=format_error) from exc
            raise AppException(
                msg=f"{prefix}，{cls.error_message(exc.code, media_type=media_type)}"
            ) from exc
        except ValueError as exc:
            raise AppException(msg=format_error) from exc

    @staticmethod
    def _normalize_job(job: Job, format_error: str) -> dict[str, Any]:
        """将 SDK 扁平字段还原为现有图片、视频服务使用的任务结构。"""
        if not isinstance(job.output, dict):
            raise AppException(msg=format_error)
        output = dict(job.output)
        output.setdefault("task_id", job.task_id)
        output.setdefault("task_status", job.status)
        data = {"request_id": job.request_id, "output": output}
        if job.usage is not None:
            data["usage"] = job.usage.model_dump(exclude_none=True)
        return data

    @staticmethod
    def _base_url(url: str, suffix: str) -> str:
        """从现有原生接口地址派生 SDK 根地址，继续使用后端已配置的域名。"""
        url = url.rstrip("/")
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
            or not url.endswith(suffix)
        ):
            raise AppException(msg="千问任务接口地址格式错误，请检查后端配置")
        return url[: -len(suffix)]

    @classmethod
    async def get_task(cls, task_id: str, *, media_type: TaskMediaType) -> dict[str, Any]:
        """查询已转义的任务 ID，继续沿用独立配置的任务查询地址。"""
        if not settings.QWEN_TASK_URL:
            raise AppException(msg="QWEN_TASK_URL 未配置")
        url = f"{settings.QWEN_TASK_URL.rstrip('/')}/{quote(task_id, safe='')}"
        return await cls.request("GET", url, media_type=media_type)

    @staticmethod
    @asynccontextmanager
    async def _create_client(base_url: str) -> AsyncIterator[AsyncClient]:
        """创建 SDK 客户端；禁用自动重试，并在取消时关闭 SDK 和 HTTP 连接。"""
        stack = AsyncExitStack()
        try:
            http_client = await stack.enter_async_context(
                httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        settings.QWEN_REQUEST_TIMEOUT, connect=settings.QWEN_CONNECT_TIMEOUT
                    ),
                    trust_env=False,
                )
            )
            client = await stack.enter_async_context(
                AsyncClient(
                    api_key=settings.QWEN_API_KEY,
                    base_url=base_url,
                    protocol="native",
                    timeout=settings.QWEN_REQUEST_TIMEOUT,
                    max_retries=0,
                    http_client=http_client,
                )
            )
            yield client
        finally:
            # HTTP 客户端由本适配层提供，SDK 不会代为关闭，两个上下文都必须退出。
            with anyio.CancelScope(shield=True):
                await stack.aclose()

    @classmethod
    def error_message(cls, code: str | None, *, media_type: TaskMediaType) -> str:
        """按媒体类型转换错误码，不向前端暴露上游原始错误信息。"""
        retry = "再试" if media_type == "图片" else "重试"
        default = f"服务错误，请稍后{retry}"
        if not isinstance(code, str):
            return default
        return cls._MEDIA_ERRORS[media_type].get(code, cls._COMMON_ERRORS.get(code, default))
