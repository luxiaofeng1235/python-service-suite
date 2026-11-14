"""
============================================
AI 对话服务 - 流式调用与记录保存
============================================
组织模型对话、上游流式调用和聊天记录保存。
控制器只负责参数校验和流式响应。
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import AppException
from app.database import async_session
from app.models.ai_chat_log import AiChatLog
from app.pkg.logging import app_logger
from app.schemas.ai import ChatRequest
from app.services.qwen_ai_service import QwenAIService
from app.utils.time_ import TimeUtil


class AIService:
    """复用千问客户端处理流式对话并保存上下文。"""

    @staticmethod
    async def stream_chat(req: ChatRequest, user_id: int = 0) -> AsyncGenerator[str, None]:
        """逐段返回本轮回答，并保存完整的助手消息。"""
        # 流的生命周期可能超过请求依赖，因此在生成器内部管理数据库会话。
        async with async_session() as db:
            chat: AiChatLog | None = None
            messages: list[dict[str, Any]] | None = None
            reply = ""
            reasoning = ""
            try:
                chat = await AIService._get_or_create_chat_log(
                    db, req.chat_id, req.model, user_id,
                )
                config = QwenAIService.resolve_config(req.model, req.is_deep_reflection)
                messages = AIService._prepare_messages(
                    chat, req.msg, req.restart, config.system_prompt,
                )
                async for event_type, content in QwenAIService.stream_completion(
                    messages, config,
                ):
                    if event_type == "delta":
                        reply += content
                        yield AIService._format_stream_content(content)
                    elif event_type == "reasoning":
                        reasoning += content
                        yield json.dumps(
                            {
                                "type": "reasoning_content",
                                "data": AIService._format_stream_content(content),
                            },
                            ensure_ascii=False,
                        )

                await AIService._save_chat_log(
                    db, chat, messages, assistant_content=reply, reasoning_content=reasoning,
                )
                await db.commit()
            except AppException as exc:
                await AIService._save_partial_chat(db, chat, messages, reply, reasoning)
                yield str(exc)
                yield "[EXCEPTION]"
            except asyncio.CancelledError:
                await AIService._save_partial_chat(db, chat, messages, reply, reasoning)
                raise
            except Exception as exc:
                await AIService._save_partial_chat(db, chat, messages, reply, reasoning)
                app_logger.opt(exception=exc).error("AI 流式对话异常")
                yield f"上游流式调用失败: {exc!s}"
                yield "[EXCEPTION]"
            else:
                yield f"[LOG_ID]:{chat.id}"
                yield "[DONE]"

    @staticmethod
    async def _save_partial_chat(
        db: AsyncSession,
        chat: AiChatLog | None,
        messages: list[dict[str, Any]] | None,
        reply: str,
        reasoning: str,
    ) -> None:
        """上游异常或连接中断时，保存已接收的部分回答。"""
        if chat is None or messages is None:
            await db.rollback()
            return

        try:
            await AIService._save_chat_log(db, chat, messages, reply, reasoning)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            app_logger.opt(exception=exc).error("AI 流式部分结果保存失败")

    @staticmethod
    async def _get_or_create_chat_log(
        db: AsyncSession,
        chat_id: int,
        model_id: int,
        user_id: int,
    ) -> AiChatLog:
        """查询当前用户所属的聊天记录，或创建新记录。"""
        if chat_id > 0:
            result = await db.execute(
                select(AiChatLog).where(
                    AiChatLog.id == chat_id,
                    AiChatLog.model_id == model_id,
                    AiChatLog.user_id == user_id,
                )
            )
            chat = result.scalar_one_or_none()
            if chat is None:
                raise AppException(msg="聊天记录不存在")
            return chat

        now = TimeUtil.get_date()
        chat = AiChatLog(
            user_id=user_id,
            model_id=model_id,
            chat=[],
            create_time=now,
            update_time=now,
        )
        db.add(chat)
        await db.flush()
        await db.refresh(chat)
        return chat

    @staticmethod
    def _prepare_messages(
        chat: AiChatLog,
        msg: str,
        restart: int,
        system_prompt: str,
    ) -> list[dict[str, Any]]:
        """组合系统提示词、历史消息和本轮用户输入。"""
        history = AIService._load_history(chat.chat)
        if restart == 1:
            if history:
                history.pop()
        else:
            history.append({"role": "user", "content": msg})
        return [{"role": "system", "content": system_prompt}, *history]

    @staticmethod
    def _load_history(chat_json: Any) -> list[dict[str, Any]]:
        """兼容历史 JSON 字符串，将聊天内容转换为消息列表。"""
        if isinstance(chat_json, list):
            return [item for item in chat_json if isinstance(item, dict)]
        try:
            history = json.loads(chat_json or "[]")
        except (TypeError, json.JSONDecodeError):
            return []
        return [item for item in history if isinstance(item, dict)] if isinstance(history, list) else []

    @staticmethod
    def _format_stream_content(content: str) -> str:
        """将流内容转换为 PHP 兼容格式，数据库仍保存原始文本。"""
        return content.replace("\n", "<br/>").replace(" ", "&nbsp;")

    @staticmethod
    async def _save_chat_log(
        db: AsyncSession,
        chat: AiChatLog,
        messages: list[dict[str, Any]],
        assistant_content: str,
        reasoning_content: str,
    ) -> None:
        """追加助手回答并将聊天记录刷新至数据库会话。"""
        history = [dict(item) for item in messages[1:]]
        history.append(
            {
                "role": "assistant",
                "reasoning_content": reasoning_content,
                "content": assistant_content,
            }
        )
        chat.chat = history
        chat.update_time = TimeUtil.get_date()
        await db.flush()
