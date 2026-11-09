"""
============================================
AI API Service - compatibility facade
============================================
Keeps API-specific chat-log queries while delegating streaming to the common AI service.
"""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import AppException
from app.common.pagination import PageParams, paginate
from app.models.ai_chat_log import AiChatLog
from app.schemas.ai import ChatRequest
from app.services.ai_service import AIService as CoreAIService
from app.utils.time_ import TimeUtil


class AIService(CoreAIService):
    """API facade for the common AI conversation service."""

    @staticmethod
    async def stream_chat(req: ChatRequest, user_id: int = 0) -> AsyncGenerator[str, None]:
        """Stream a chat using the shared conversation workflow."""
        async for chunk in CoreAIService.stream_chat(req, user_id):
            yield chunk

    @staticmethod
    async def list_chat_logs(
        db: AsyncSession,
        user_id: int,
        page_params: PageParams,
        model_id: int | None = None,
    ) -> dict[str, Any]:
        """Get the current user's paginated chat logs."""
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
        """Get one chat log owned by the current user."""
        chat = await AIService._get_existing_chat_log(db, chat_id, user_id)
        return AIService._serialize_chat_log(chat)

    @staticmethod
    async def delete_chat_log(db: AsyncSession, chat_id: int, user_id: int) -> dict[str, int]:
        """Delete one chat log owned by the current user."""
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
        """Get one chat log and enforce ownership."""
        result = await db.execute(
            select(AiChatLog).where(AiChatLog.id == chat_id, AiChatLog.user_id == user_id)
        )
        chat = result.scalar_one_or_none()
        if chat is None:
            raise AppException(msg="聊天记录不存在")
        return chat

    @staticmethod
    def _serialize_chat_log(chat: AiChatLog) -> dict[str, Any]:
        """Serialize a chat log for API responses."""
        return {
            "id": chat.id,
            "user_id": chat.user_id,
            "model_id": chat.model_id,
            "chat": CoreAIService._load_history(chat.chat),
            "create_time": TimeUtil.format_datetime(chat.create_time),
            "update_time": TimeUtil.format_datetime(chat.update_time),
        }
