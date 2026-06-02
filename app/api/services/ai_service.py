"""
============================================
AI 业务逻辑服务层
============================================
负责处理千问兼容模式对话、流式输出与聊天记录落库。
"""

import json
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

import httpx
from loguru import logger

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PageParams, paginate
from app.common.exception import AppException
from app.core.config import settings
from app.database import async_session
from app.schemas.ai import ChatRequest, ChatResponse, StreamChunk
from app.models.ai_chat_log import AiChatLog


class AIService:
    """AI 对话服务"""

    # ============================================================
    # 模型配置映射表
    # 键: 模型ID (1)
    # 值: 上游模型名、System Prompt、是否启用搜索、是否启用深度思考
    # ============================================================
    MODEL_CONFIGS: dict[int, dict[str, Any]] = {  # noqa: RUF012
        1: {
            "upstream_model": "qwen-max",
            "deep_reflection_model": "qwen-plus",
            "system": "你现在是一个全能生活小助手，擅长星座运势、生活百科、情感建议、健康养生、美食旅行、科技数码等各个领域的知识问答。你可以为用户查询星座运势、解读命理、推荐美食、规划旅行、解答情感困惑、分享生活技巧等。请以热情友好的方式回答；如果用户输入了链接，请不要声称你能直接访问网页内容。全程使用简体中文，如果回答中有数学相关公式请使用双$符加换行的markdown语法",
            "enable_search": True,
        },
    }

    @staticmethod
    async def chat(db: AsyncSession, req: ChatRequest, user_id: int = 0) -> ChatResponse:
        """普通对话接口，聚合上游完整回复并落库"""
        # 1. 获取或创建聊天记录
        chat = await AIService._get_or_create_chat_log(db, req.chat_id, req.model, user_id)
        # 2. 解析模型配置（含深度思考回退逻辑）
        config = AIService._resolve_model_config(req.model, req.is_deep_reflection)
        # 3. 组装消息列表（history + 本轮用户消息）
        messages = AIService._prepare_messages(chat, req.msg, req.restart, config["system"])
        # 4. 请求上游 LLM 非流式接口
        response_data = await AIService._request_completion(
            messages=messages,
            upstream_model=config["upstream_model"],
            enable_search=config["enable_search"],
            stream=False,
        )
        # 5. 解析回复内容与推理过程
        choice = (response_data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        reply = message.get("content", "")
        reasoning_content = message.get("reasoning_content", "")
        # 6. 写入数据库持久化
        await AIService._save_chat_log(
            db=db,
            chat=chat,
            messages=messages,
            assistant_content=reply,
            reasoning_content=reasoning_content,
        )
        # 7. 返回结构化响应
        return ChatResponse(
            reply=reply,
            chat_id=chat.id,
            usage=response_data.get("usage"),
            reasoning_content=reasoning_content,
        )

    @staticmethod
    async def stream_chat(
        req: ChatRequest, user_id: int = 0
    ) -> AsyncGenerator[str, None]:
        """流式对话接口，自管 DB 事务，按旧协议直接输出文本片段"""
        # 在生成器内部自建独立 session，避免 FastAPI yield 依赖提前 commit/close
        async with async_session() as db:
            try:
                # 1. 获取/创建聊天记录、解析配置、组装消息
                chat = await AIService._get_or_create_chat_log(db, req.chat_id, req.model, user_id)
                config = AIService._resolve_model_config(req.model, req.is_deep_reflection)
                messages = AIService._prepare_messages(chat, req.msg, req.restart, config["system"])

                # 2. 初始化累积变量（用于流结束后落库）
                accumulated_reply = ""
                accumulated_reasoning = ""

                # 并行启动推荐问题生成任务（已屏蔽）
                # suggestions_task = asyncio.create_task(
                #     AIService._generate_suggestions(
                #         messages=messages,
                #         upstream_model=config["upstream_model"],
                #         enable_search=config["enable_search"],
                #     )
                # )

                # 3. 建立 httpx 流式连接请求上游 LLM
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(300.0, connect=30.0),
                    trust_env=False,
                ) as client:
                    async with client.stream(
                        "POST",
                        settings.QWEN_CHAT_URL,
                        headers=AIService._build_headers(),
                        json={
                            "model": config["upstream_model"],
                            "messages": messages,
                            "stream": True,
                            "enable_search": config["enable_search"],
                        },
                    ) as resp:
                        # 4. 检查上游 HTTP 状态码
                        if resp.status_code >= 400:
                            error_text = await resp.aread()
                            raise AppException(msg=AIService._extract_error_message(resp, error_text))

                        # 5. 逐行解析 SSE 事件并实时 yield 给客户端
                        async for raw_line in resp.aiter_lines():
                            event = AIService._parse_stream_line(raw_line, chat.id)
                            if not event:
                                continue

                            # 5a. 普通文本片段 → 累加后直接输出
                            if event["type"] == "delta":
                                accumulated_reply += event["content"]
                                yield event["content"]
                            # 5b. 推理过程片段 → 包装为 JSON 格式输出
                            elif event["type"] == "reasoning":
                                accumulated_reasoning += event["content"]
                                yield json.dumps(
                                    {"type": "reasoning_content", "data": event["content"]},
                                    ensure_ascii=False,
                                )
                            # 5c. 结束标记 → 跳过（后续走 else 分支收尾）
                            elif event["type"] == "end":
                                continue

                # 6. 流结束后将完整对话落库
                await AIService._save_chat_log(
                    db=db,
                    chat=chat,
                    messages=messages,
                    assistant_content=accumulated_reply,
                    reasoning_content=accumulated_reasoning,
                )
                await db.commit()

            except AppException as exc:
                # 7a. 业务错误 → 先 rollback 再 yield，避免客户端断连时 rollback 不执行
                await db.rollback()
                try:
                    yield str(exc)
                    yield "[EXCEPTION]"
                except RuntimeError:
                    pass
            except Exception as exc:
                # 7b. 系统异常 → 先 rollback，堆栈日志，再 yield
                await db.rollback()
                logger.exception("流式对话系统异常")
                try:
                    yield f"上游流式调用失败: {exc!s}"
                    yield "[EXCEPTION]"
                except RuntimeError:
                    pass
            else:
                # 7c. 正常结束 → 返回日志 ID 和完成标记（推荐问题已屏蔽）
                # suggestions = await suggestions_task
                # if suggestions:
                #     yield json.dumps(
                #         {"type": "suggestions", "data": suggestions},
                #         ensure_ascii=False,
                #     )
                yield f"[LOG_ID]:{chat.id}"
                yield "[DONE]"

    @staticmethod
    async def list_chat_logs(
        db: AsyncSession,
        user_id: int,
        page_params: PageParams,
        model_id: int | None = None,
    ) -> dict[str, Any]:
        """获取当前用户的 AI 对话列表"""
        # 1. 拼装查询条件（用户ID + 可选模型筛选）
        conditions = [AiChatLog.user_id == user_id]
        if model_id is not None:
            conditions.append(AiChatLog.model_id == model_id)

        # 2. 构建查询语句
        stmt = (
            select(AiChatLog)
            .where(*conditions)
            .order_by(AiChatLog.id.desc())
        )
        count_stmt = select(func.count(AiChatLog.id)).where(*conditions)

        # 3. 分页查询
        data = await paginate(db, stmt, page_params, count_stmt)

        # 4. 序列化并返回
        items = [AIService._serialize_chat_log(item) for item in data["items"]]
        return {**data, "items": items}

    @staticmethod
    async def get_chat_log_detail(db: AsyncSession, chat_id: int, user_id: int) -> dict[str, Any]:
        """获取当前用户的对话详情"""
        # 1. 校验并获取聊天记录
        chat = await AIService._get_existing_chat_log(db, chat_id, user_id)
        # 2. 序列化返回
        return AIService._serialize_chat_log(chat)

    @staticmethod
    async def delete_chat_log(db: AsyncSession, chat_id: int, user_id: int) -> dict[str, Any]:
        """删除当前用户的指定对话"""
        # 1. 校验记录归属权（不存在则抛异常）
        await AIService._get_existing_chat_log(db, chat_id, user_id)
        # 2. 执行删除
        await db.execute(
            delete(AiChatLog).where(AiChatLog.id == chat_id, AiChatLog.user_id == user_id)
        )
        return {"deleted": 1}

    @staticmethod
    async def delChatLog(db: AsyncSession, params: dict[str, Any], uid: int) -> dict[str, Any]:
        """
        删除指定 AI 对话（PHP 风格，按 find → delete 流程）

        Args:
            params: 参数字典，含 chat_id
            uid: 用户 ID

        Returns:
            删除成功消息
        """
        chat_id = params["chat_id"]
        result = await db.execute(
            select(AiChatLog).where(AiChatLog.id == chat_id, AiChatLog.user_id == uid)
        )
        chat = result.scalar_one_or_none()
        if not chat:
            raise AppException(msg="聊天记录不存在")
        await db.delete(chat)
        return {"msg": "删除成功"}

    @staticmethod
    async def _get_or_create_chat_log(
        db: AsyncSession, chat_id: int, model_id: int, user_id: int
    ) -> AiChatLog:
        """获取或创建聊天记录"""
        if chat_id > 0:
            # 已有 chat_id → 从数据库查询并校验归属
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

        # chat_id=0 → 创建新聊天记录
        now = datetime.now()
        chat = AiChatLog(
            user_id=user_id, model_id=model_id, chat=[], create_time=now, update_time=now
        )
        db.add(chat)
        await db.flush()
        await db.refresh(chat)
        return chat

    @staticmethod
    async def _get_existing_chat_log(db: AsyncSession, chat_id: int, user_id: int) -> AiChatLog:
        """获取当前用户已有对话"""
        result = await db.execute(
            select(AiChatLog).where(AiChatLog.id == chat_id, AiChatLog.user_id == user_id)
        )
        chat = result.scalar_one_or_none()
        if chat is None:
            raise AppException(msg="聊天记录不存在")
        return chat

    @staticmethod
    def _serialize_chat_log(chat: AiChatLog) -> dict[str, Any]:
        """序列化聊天记录"""
        return {
            "id": chat.id,
            "user_id": chat.user_id,
            "model_id": chat.model_id,
            "chat": AIService._load_history(chat.chat),
            "create_time": chat.create_time.strftime("%Y-%m-%d %H:%M:%S")
            if chat.create_time
            else None,
            "update_time": chat.update_time.strftime("%Y-%m-%d %H:%M:%S")
            if chat.update_time
            else None,
        }

    @staticmethod
    def _resolve_model_config(model_id: int, is_deep_reflection: int) -> dict[str, Any]:
        """解析模型配置"""
        # 1. 按 model_id 查询对应配置
        config = AIService.MODEL_CONFIGS.get(model_id)
        if config is None:
            raise AppException(msg="不支持的模型类型")

        # 2. 深度思考回退逻辑：模型1启用深度思考时替换为 deep_reflection_model
        resolved = dict(config)
        if model_id == 1 and is_deep_reflection == 1:
            resolved["upstream_model"] = config.get(
                "deep_reflection_model", config["upstream_model"]
            )
        return resolved

    @staticmethod
    def _prepare_messages(
        chat: AiChatLog, msg: str, restart: int, system: str
    ) -> list[dict[str, Any]]:
        """组装消息列表，兼容 restart 语义"""
        # 1. 以 system prompt 开头
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        # 2. 追加历史对话
        history = AIService._load_history(chat.chat)
        messages.extend(history)

        # 3. restart=1 → 移除上一条消息（重新回答）; 否则追加本轮用户消息
        if restart == 1:
            if len(messages) > 1:
                messages.pop()
        else:
            messages.append({"role": "user", "content": msg})

        return messages

    @staticmethod
    def _load_history(chat_json: Any) -> list[dict[str, Any]]:
        """读取历史消息"""
        # 已反序列化 → 直接返回（JSON 字段已自动解析）
        if isinstance(chat_json, list):
            return chat_json
        try:
            history = json.loads(chat_json or "[]")
        except json.JSONDecodeError:
            return []
        return history if isinstance(history, list) else []

    @staticmethod
    async def _save_chat_log(
        db: AsyncSession,
        chat: AiChatLog,
        messages: list[dict[str, Any]],
        assistant_content: str,
        reasoning_content: str,
    ) -> None:
        """保存聊天记录"""
        # 1. 去掉 system 消息，保留 user<->assistant 历史
        chat_messages = messages[1:]
        # 2. 追加 assistant 回复（含推理过程）
        chat_messages.append(
            {
                "role": "assistant",
                "reasoning_content": reasoning_content,
                "content": assistant_content,
            }
        )
        chat.chat = chat_messages
        chat.update_time = datetime.now()
        await db.flush()

    @staticmethod
    async def _generate_suggestions(
        messages: list[dict[str, Any]],
        upstream_model: str,
        enable_search: bool,
    ) -> list[str]:
        """并行生成推荐追问 — 暂未启用"""
        return []

    @staticmethod
    async def _request_completion(
        messages: list[dict[str, Any]],
        upstream_model: str,
        enable_search: bool,
        stream: bool,
    ) -> dict[str, Any]:
        """请求上游完整响应"""
        try:
            # 1. 向上游 LLM 发起 POST 请求
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                resp = await client.post(
                    settings.QWEN_CHAT_URL,
                    headers=AIService._build_headers(),
                    json={
                        "model": upstream_model,
                        "messages": messages,
                        "stream": stream,
                        "enable_search": enable_search,
                    },
                )
        except httpx.HTTPError as exc:
            raise AppException(msg=f"上游接口连接失败: {exc!s}") from exc

        # 2. 检查 HTTP 响应状态码
        if resp.status_code >= 400:
            raise AppException(msg=AIService._extract_error_message(resp))
        return resp.json()

    @staticmethod
    def _build_headers() -> dict[str, str]:
        """构建上游请求头"""
        if not settings.QWEN_API_KEY:
            raise AppException(msg="QWEN_API_KEY 未配置")
        return {
            "Authorization": f"Bearer {settings.QWEN_API_KEY}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _parse_stream_line(raw_line: str, chat_id: int) -> dict[str, Any] | None:
        """解析上游 SSE 单行数据"""
        # 1. 过滤无效行（空行 / 非 data: 开头）
        line = raw_line.strip()
        if not line or not line.startswith("data:"):
            return None

        # 2. 提取 payload
        payload = line[5:].strip()
        if payload == "[DONE]":
            return None

        # 3. 尝试 JSON 解析
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None

        # 4. 上游返回错误 → 包装为 error 类型
        if data.get("error"):
            return StreamChunk(
                type="error",
                chat_id=chat_id,
                content=data["error"].get("message")
                or data["error"].get("code", "服务错误，请稍后再试"),
            ).model_dump()

        choice = (data.get("choices") or [{}])[0]
        delta = choice.get("delta") or {}
        finish_reason = choice.get("finish_reason")
        usage = data.get("usage")

        # 5. 推理过程
        if delta.get("reasoning_content"):
            return StreamChunk(
                type="reasoning",
                chat_id=chat_id,
                content=delta["reasoning_content"],
            ).model_dump()

        # 6. 普通文本增量
        if delta.get("content"):
            return StreamChunk(
                type="delta",
                chat_id=chat_id,
                content=delta["content"],
            ).model_dump()

        # 7. 结束标记（含用量信息）
        if finish_reason or usage:
            return StreamChunk(
                type="end",
                chat_id=chat_id,
                content="",
                usage=usage,
            ).model_dump()

        return None

    @staticmethod
    def _extract_error_message(resp: httpx.Response, body: bytes | None = None) -> str:
        """提取上游错误信息"""
        # 1. 获取响应体（优先使用传入的 body）
        content = body if body is not None else resp.content
        # 2. 尝试 JSON 解析，提取 error.message 或 error.code
        try:
            data = json.loads(content.decode("utf-8"))
        except Exception:
            return f"上游接口调用失败，HTTP {resp.status_code}"

        error = data.get("error") or {}
        return (
            error.get("message")
            or error.get("code")
            or f"上游接口调用失败，HTTP {resp.status_code}"
        )
