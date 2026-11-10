"""
============================================
AI 接口服务 - 聊天记录、流式转发与图片视频生成
============================================
负责当前用户的聊天记录查询和删除，复用公共服务的流式对话和图片视频生成能力。
"""

from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack
from typing import Any

import anyio
import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from app.common.exception import AppException
from app.common.pagination import PageParams, paginate
from app.models.ai_chat_log import AiChatLog
from app.pkg.logging import app_logger
from app.schemas.ai import ChatRequest, ImageRequest, OmniStreamRequest, VideoRequest
from app.services.ai_image_service import AIImageService
from app.services.ai_stream_service import AIService as CoreAIService
from app.services.ai_video_service import AIVideoService
from app.services.qwen_ai_service import QwenAIService
from app.utils.time_ import TimeUtil


class AIService(CoreAIService):
    """供接口调用的 AI 服务，复用公共服务的对话和图片视频生成能力。"""

    @staticmethod
    async def stream_new(req: OmniStreamRequest) -> StreamingResponse:
        """转发多模态原始 SSE，消息上下文由本次请求提供，不写聊天记录。"""
        stack = AsyncExitStack()

        async def close_stream() -> None:
            # 断开连接时仍完成清理，释放千问响应和 HTTP 客户端。
            with anyio.CancelScope(shield=True):
                await stack.aclose()

        try:
            messages = [item.model_dump(mode="json", exclude_unset=True) for item in req.message]
            # 先连接并校验上游状态，再向前端发送 SSE 响应头。
            upstream = await stack.enter_async_context(QwenAIService.stream_omni(messages))
        except BaseException:
            await close_stream()
            raise

        async def forward_stream() -> AsyncGenerator[bytes, None]:
            try:
                # 分片可能跨越 SSE 事件边界，直接转发即可；不解析或重复添加 data:。
                async for chunk in upstream.aiter_bytes():
                    yield chunk
            except httpx.HTTPError:
                app_logger.warning("千问多模态流式连接异常")
                # 流已开始，使用与 PHP 一致的 SSE 错误提示，不伪造正常结束标记。
                yield "\n\ndata: [ERROR] 千问多模态流式连接中断，请重试\n\n".encode()
            finally:
                await close_stream()

        return StreamingResponse(
            forward_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            # 覆盖前端在读取第一个分片前就断开连接的情况。
            background=BackgroundTask(close_stream),
        )

    @staticmethod
    async def to_video(db: AsyncSession, req: VideoRequest, user_id: int) -> str:
        """提交文生视频任务，返回任务 ID，对应 PHP 的 toVideo。"""
        return await AIVideoService.to_video(db, req, user_id)

    @staticmethod
    async def get_video(
        db: AsyncSession, task_id: str, user_id: int
    ) -> dict[str, list[str]] | str:
        """查询视频进度，生成后由公共服务加水印、上传 OSS 并缓存结果。"""
        return await AIVideoService.get_video(db, task_id, user_id)

    @staticmethod
    async def to_image(
        db: AsyncSession,
        req: ImageRequest,
        user_id: int,
    ) -> str:
        """提交文生图任务，返回任务 ID，对应 PHP 的 toImage。"""
        return await AIImageService.to_image(db, req, user_id)

    @staticmethod
    async def get_image(
        db: AsyncSession,
        task_id: str,
        user_id: int,
    ) -> dict[str, list[str]] | str:
        """查询文生图结果，生成中返回任务 ID，对应 PHP 的 getImage。"""
        return await AIImageService.get_image(db, task_id, user_id)

    @staticmethod
    async def stream_chat(req: ChatRequest, user_id: int = 0) -> AsyncGenerator[str, None]:
        """调用公共 AI 服务，逐段向接口返回流式内容。"""
        # 模型请求、历史消息处理和回复保存由公共服务完成，此处收到一段就转发一段。
        async for chunk in CoreAIService.stream_chat(req, user_id):
            yield chunk

    @staticmethod
    async def list_chat_logs(
        db: AsyncSession,
        user_id: int,
        page_params: PageParams,
        model_id: int | None = None,
    ) -> dict[str, Any]:
        """分页查询当前用户的聊天记录，可按模型筛选，按记录 ID 倒序返回。"""
        conditions = [AiChatLog.user_id == user_id]
        if model_id is not None:
            conditions.append(AiChatLog.model_id == model_id)
        stmt = select(AiChatLog).where(*conditions).order_by(AiChatLog.id.desc())
        count_stmt = select(func.count(AiChatLog.id)).where(*conditions)
        data = await paginate(db, stmt, page_params, count_stmt)
        items = [AIService._serialize_chat_log(item) for item in data["items"]]
        return {**data, "items": items}

    @staticmethod
    async def get_chat_log_detail(
        db: AsyncSession,
        chat_id: int,
        user_id: int,
    ) -> dict[str, Any]:
        """查询聊天记录详情，仅允许访问当前用户自己的记录。"""
        chat = await AIService._get_existing_chat_log(db, chat_id, user_id)
        return AIService._serialize_chat_log(chat)

    @staticmethod
    async def delete_chat_log(db: AsyncSession, chat_id: int, user_id: int) -> dict[str, int]:
        """删除当前用户的指定聊天记录，并提交数据库事务。"""
        # 先校验记录归属，执行删除时仍限定用户，避免删除其他用户的记录。
        await AIService._get_existing_chat_log(db, chat_id, user_id)
        await db.execute(
            delete(AiChatLog).where(AiChatLog.id == chat_id, AiChatLog.user_id == user_id)
        )
        await db.commit()
        return {"deleted": 1}

    @staticmethod
    async def _get_existing_chat_log(
        db: AsyncSession,
        chat_id: int,
        user_id: int,
    ) -> AiChatLog:
        """按记录 ID 和用户 ID 查询；记录不存在或不属于当前用户时统一报错。"""
        result = await db.execute(
            select(AiChatLog).where(AiChatLog.id == chat_id, AiChatLog.user_id == user_id)
        )
        chat = result.scalar_one_or_none()
        if chat is None:
            raise AppException(msg="聊天记录不存在")
        return chat

    @staticmethod
    def _serialize_chat_log(chat: AiChatLog) -> dict[str, Any]:
        """将聊天记录转换为接口数据，统一处理消息内容和时间格式。"""
        return {
            "id": chat.id,
            "user_id": chat.user_id,
            "model_id": chat.model_id,
            # 兼容 JSON 列表和 JSON 字符串，将聊天内容统一转换为消息列表。
            "chat": CoreAIService._load_history(chat.chat),
            "create_time": TimeUtil.format_datetime(chat.create_time),
            "update_time": TimeUtil.format_datetime(chat.update_time),
        }
