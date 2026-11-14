"""
============================================
Agent 聊天服务 - 会话归属与消息持久化
============================================
通过短事务保存运行步骤，为各类 Agent 提供统一的会话、消息和流式事件管理。
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from time import monotonic
from uuid import uuid4

import anyio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.llm.base import LLMMessage, ToolCall
from app.agents.runtime import AgentRunner, AgentStep
from app.common.exception import AppException
from app.constants.chat import ChatMessageStatus
from app.core.config import settings
from app.database import async_session
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.user import User
from app.pkg.logging import app_logger
from app.schemas.agent.chat import AgentChatRequest, AgentStreamEvent
from app.utils.time_ import TimeUtil

MAX_MESSAGE_BYTES = 60000
LEASE_CLEANUP_SECONDS = 60


@dataclass
class _RunState:
    """Track only the records and partial text owned by one execution."""

    session_id: str
    run_id: str
    assistant_id: int | None = None
    tool_id: int | None = None
    last_message_id: int | None = None
    content: str = ""
    content_bytes: int = 0
    finished: bool = False


class AgentChatService:
    """Connect any Agent runner to owned MySQL conversation storage."""

    def __init__(
        self,
        runner: AgentRunner,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ):
        self.runner = runner
        self.session_factory = session_factory or async_session

    async def stream_chat(
        self,
        req: AgentChatRequest,
        user_id: int,
    ) -> AsyncIterator[AgentStreamEvent]:
        """Stream one owned turn and finalize partial records on disconnect."""
        state = None
        steps = None
        async with self.session_factory() as db:
            try:
                state, history = await self._start_run(db, req, user_id)
                deadline = monotonic() + settings.AGENT_RUN_TIMEOUT
                yield self._event(state, "session")
                steps = self.runner.run(history)
                while True:
                    # 超时只包住生成下一步，避免异步生成器暂停时取消调用方的其他工作。
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        raise TimeoutError
                    async with asyncio.timeout(remaining):
                        try:
                            step = await anext(steps)
                        except StopAsyncIteration:
                            break
                    event = await self._consume_step(db, state, step)
                    if event is not None:
                        yield event
                    if state.finished:
                        return
                raise AppException(msg="Agent 执行未正常结束")
            except (asyncio.CancelledError, GeneratorExit):
                await self._abort(db, state, ChatMessageStatus.INTERRUPTED)
                raise
            except Exception as exc:
                await self._abort(db, state, ChatMessageStatus.FAILED)
                if state is None:
                    raise
                if isinstance(exc, AppException):
                    message = exc.msg
                elif isinstance(exc, TimeoutError):
                    message = "Agent 执行超时，请重试"
                else:
                    app_logger.error(
                        "Agent 执行异常 agent={} error_type={}",
                        self.runner.name,
                        type(exc).__name__,
                    )
                    message = "Agent 执行失败，请稍后重试"
                yield self._event(state, "error", content=message)
            finally:
                if steps is not None and hasattr(steps, "aclose"):
                    with anyio.CancelScope(shield=True):
                        await steps.aclose()

    async def stream_sse(self, req: AgentChatRequest, user_id: int) -> AsyncIterator[str]:
        """Yield JSON data payloads for the existing SSEUtil.stream_response helper."""
        stream = self.stream_chat(req, user_id)
        try:
            async for event in stream:
                yield event.model_dump_json(exclude_none=True)
        finally:
            await stream.aclose()

    async def _start_run(
        self,
        db: AsyncSession,
        req: AgentChatRequest,
        user_id: int,
    ) -> tuple[_RunState, list[LLMMessage]]:
        """Claim the session lease and store the new user message atomically."""
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            raise AppException(msg="请先登录")
        user = await db.scalar(
            select(User.id).where(User.id == user_id, User.is_active, ~User.is_deleted)
        )
        if user is None:
            raise AppException(msg="用户不存在或已停用")
        now = TimeUtil.get_date()
        if req.session_id is not None:
            session = await db.scalar(
                select(ChatSession)
                .where(
                    ChatSession.id == str(req.session_id),
                    ChatSession.user_id == user_id,
                    ChatSession.agent == self.runner.name,
                )
                .with_for_update()
            )
            if session is None:
                raise AppException(msg="会话不存在或不属于当前 Agent")
            if session.active_run_id and session.run_expires_at and session.run_expires_at > now:
                raise AppException(msg="该会话正在生成中，请稍后重试")
            # 只有已有会话需要恢复遗留消息并读取历史。
            await db.execute(
                update(ChatMessage)
                .where(
                    ChatMessage.session_id == session.id,
                    ChatMessage.status == ChatMessageStatus.GENERATING,
                )
                .values(status=ChatMessageStatus.INTERRUPTED)
            )
            history = await self._load_history(db, session.id)
        else:
            session = ChatSession(user_id=user_id, agent=self.runner.name, title=req.message[:100])
            db.add(session)
            await db.flush()
            # 新会话没有历史，避免对空消息范围加锁后并发插入导致死锁。
            history = []
        run_id = str(uuid4())
        session.active_run_id = run_id
        session.run_expires_at = now + timedelta(
            seconds=settings.AGENT_RUN_TIMEOUT + LEASE_CLEANUP_SECONDS
        )
        session.updated_at = now
        db.add(ChatMessage(session_id=session.id, role="user", content=req.message))
        history.append(LLMMessage(role="user", content=req.message))
        await db.commit()
        return _RunState(session.id, run_id), history

    @staticmethod
    async def _load_history(db: AsyncSession, session_id: str) -> list[LLMMessage]:
        """Replay complete tool groups and discard incomplete or orphaned results."""
        rows = list(
            reversed(
                (
                    await db.scalars(
                        select(ChatMessage)
                        .where(ChatMessage.session_id == session_id)
                        .order_by(ChatMessage.id.desc())
                        .limit(settings.AGENT_MAX_HISTORY_MESSAGES)
                        .with_for_update()
                    )
                ).all()
            )
        )
        history: list[LLMMessage] = []
        group: list[LLMMessage] = []
        waiting: set[str] = set()
        for row in rows:
            if row.role == "user":
                group, waiting = [], set()
                history.append(LLMMessage(role="user", content=row.content))
                continue
            if not history:
                continue
            if row.role == "assistant" and row.status == ChatMessageStatus.COMPLETED:
                if waiting:
                    group, waiting = [], set()
                calls = [ToolCall.model_validate(call) for call in row.tool_calls or []]
                message = LLMMessage(
                    role="assistant", content=row.content, tool_calls=calls or None
                )
                if calls:
                    group = [message]
                    waiting = {call.id for call in calls}
                elif row.content:
                    history.append(message)
            elif (
                row.role == "tool"
                and row.tool_call_id in waiting
                and row.status
                in {
                    ChatMessageStatus.COMPLETED,
                    ChatMessageStatus.FAILED,
                }
            ):
                group.append(
                    LLMMessage(
                        role="tool",
                        content=row.content,
                        name=row.tool_name,
                        tool_call_id=row.tool_call_id,
                    )
                )
                waiting.remove(row.tool_call_id)
                if not waiting:
                    history.extend(group)
                    group = []
        # 按完整用户轮次裁剪，不能把 assistant 工具调用与 tool 返回拆开。
        starts = [index for index, message in enumerate(history) if message.role == "user"]
        end, size = len(history), 0
        for start in reversed(starts):
            turn_size = sum(len(message.model_dump_json()) for message in history[start:end])
            if size + turn_size > settings.AGENT_MAX_HISTORY_CHARS:
                break
            size += turn_size
            end = start
        return history[end:]

    @staticmethod
    async def _lock_run(db: AsyncSession, state: _RunState) -> None:
        """Fence stale executions before changing any message records."""
        owned = await db.scalar(
            select(ChatSession.id)
            .where(
                ChatSession.id == state.session_id,
                ChatSession.active_run_id == state.run_id,
            )
            .with_for_update()
        )
        if owned is None:
            raise AppException(msg="会话执行已结束或被新的请求接管")

    async def _consume_step(
        self,
        db: AsyncSession,
        state: _RunState,
        step: AgentStep,
    ) -> AgentStreamEvent | None:
        """先保存消息生命周期变化，再输出通知；文字和业务数据直接转发。"""
        if step.type == "delta":
            state.content_bytes += len(step.content.encode())
            if state.content_bytes > MAX_MESSAGE_BYTES:
                raise AppException(msg="Agent 回复内容过长，请缩小问题范围")
            state.content += step.content
            return self._event(state, "delta", content=step.content, message_id=state.assistant_id)
        if step.type == "reasoning":
            return self._event(
                state, "reasoning", content=step.content, message_id=state.assistant_id
            )
        if step.type == "data":
            # 数据由具体 Agent 组装；不拼入助手文本，避免前端从自然语言解析商品信息。
            if step.data is None:
                raise AppException(msg="Agent 业务数据为空")
            return self._event(state, "data", data=step.data, message_id=state.assistant_id)

        await self._lock_run(db, state)
        if step.type == "model_start":
            row = ChatMessage(
                session_id=state.session_id, role="assistant", status=ChatMessageStatus.GENERATING
            )
            db.add(row)
            await db.flush()
            state.assistant_id, state.content, state.content_bytes = row.id, "", 0
        elif step.type == "assistant":
            message = step.message
            if message is None or state.assistant_id is None:
                raise AppException(msg="Agent 消息状态异常")
            await db.execute(
                update(ChatMessage)
                .where(ChatMessage.id == state.assistant_id)
                .values(
                    content=message.content,
                    tool_calls=[call.model_dump() for call in message.tool_calls]
                    if message.tool_calls
                    else None,
                    status=ChatMessageStatus.COMPLETED,
                )
            )
        elif step.type == "tool_start":
            row = ChatMessage(
                session_id=state.session_id,
                role="tool",
                tool_name=step.tool_name,
                tool_call_id=step.tool_call_id,
                status=ChatMessageStatus.GENERATING,
            )
            db.add(row)
            await db.flush()
            state.tool_id = row.id
        elif step.type == "tool_end":
            if step.message is None or state.tool_id is None:
                raise AppException(msg="Agent 工具结果状态异常")
            await db.execute(
                update(ChatMessage)
                .where(ChatMessage.id == state.tool_id)
                .values(
                    content=step.message.content,
                    status=ChatMessageStatus.COMPLETED
                    if step.success
                    else ChatMessageStatus.FAILED,
                )
            )
        elif step.type == "done":
            await db.execute(
                update(ChatSession)
                .where(ChatSession.id == state.session_id)
                .values(
                    active_run_id=None,
                    run_expires_at=None,
                    updated_at=TimeUtil.get_date(),
                )
            )
        await db.commit()
        if step.type == "assistant":
            state.last_message_id, state.assistant_id = state.assistant_id, None
            state.content, state.content_bytes = "", 0
        elif step.type == "tool_end":
            state.tool_id = None
        if step.type == "done":
            state.finished = True
            return self._event(state, "done", message_id=state.last_message_id, usage=step.usage)
        if step.type in {"tool_start", "tool_end"}:
            return self._event(
                state,
                step.type,
                tool_name=step.tool_name,
                tool_call_id=step.tool_call_id,
                success=step.success if step.type == "tool_end" else None,
            )
        return None

    async def _abort(
        self,
        db: AsyncSession,
        state: _RunState | None,
        status: ChatMessageStatus,
    ) -> None:
        """Save partial output and release only the lease owned by this run."""
        with anyio.CancelScope(shield=True):
            await db.rollback()
            if state is None or state.finished:
                return
            try:
                await self._lock_run(db, state)
                if state.assistant_id is not None:
                    await db.execute(
                        update(ChatMessage)
                        .where(ChatMessage.id == state.assistant_id)
                        .values(
                            content=state.content or None,
                            status=status,
                        )
                    )
                if state.tool_id is not None:
                    await db.execute(
                        update(ChatMessage)
                        .where(ChatMessage.id == state.tool_id)
                        .values(status=status)
                    )
                await db.execute(
                    update(ChatSession)
                    .where(ChatSession.id == state.session_id)
                    .values(
                        active_run_id=None,
                        run_expires_at=None,
                        updated_at=TimeUtil.get_date(),
                    )
                )
                await db.commit()
            except Exception as exc:
                await db.rollback()
                app_logger.error(
                    "Agent 中断保存失败 agent={} error_type={}",
                    self.runner.name,
                    type(exc).__name__,
                )

    def _event(self, state: _RunState, event_type: str, **fields) -> AgentStreamEvent:
        """Create provider-independent events with mandatory conversation identity."""
        return AgentStreamEvent(
            type=event_type, session_id=state.session_id, agent=self.runner.name, **fields
        )
