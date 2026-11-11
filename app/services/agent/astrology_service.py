"""
============================================
Astrology Business Service - Profiles, cache and Agent binding
============================================
Implements trusted tools using backend user identity and short database sessions.
"""

from collections.abc import AsyncIterator
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.astrology import create_astrology_agent
from app.agents.llm.base import LLMAdapter
from app.common.exception import AppException
from app.core.config import settings
from app.database import async_session
from app.models.horoscope_cache import HoroscopeCache
from app.models.user import User
from app.models.user_astrology_profile import UserAstrologyProfile
from app.schemas.agent.astrology import (
    AstrologyProfileUpdateRequest,
    HoroscopeCacheRequest,
    HoroscopeToolRequest,
)
from app.schemas.agent.chat import AgentChatRequest, AgentStreamEvent
from app.services.agent.chat_service import AgentChatService


class AstrologyService:
    """Expose astrology tools and bind them to an authenticated user."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        llm: LLMAdapter | None = None,
    ):
        self.session_factory = session_factory or async_session
        self.llm = llm

    def _chat_service(self, user_id: int) -> AgentChatService:
        """Bind tool ownership to backend context rather than model parameters."""

        async def profile_handler() -> JsonValue:
            async with self.session_factory() as db:
                return await self.get_profile(db, user_id)

        async def horoscope_handler(**parameters) -> JsonValue:
            async with self.session_factory() as db:
                return await self.get_horoscope(db, user_id, HoroscopeToolRequest(**parameters))

        runner = create_astrology_agent(profile_handler, horoscope_handler, llm=self.llm)
        return AgentChatService(runner, session_factory=self.session_factory)

    async def stream_chat(
        self,
        req: AgentChatRequest,
        user_id: int,
    ) -> AsyncIterator[AgentStreamEvent]:
        """Execute an astrology turn without depending on an HTTP controller."""
        stream = self._chat_service(user_id).stream_chat(req, user_id)
        try:
            async for event in stream:
                yield event
        finally:
            await stream.aclose()

    async def stream_sse(self, req: AgentChatRequest, user_id: int) -> AsyncIterator[str]:
        """Produce JSON data payloads compatible with the existing SSE utility."""
        stream = self._chat_service(user_id).stream_sse(req, user_id)
        try:
            async for payload in stream:
                yield payload
        finally:
            await stream.aclose()

    @staticmethod
    async def get_profile(db: AsyncSession, user_id: int) -> dict[str, JsonValue]:
        """Read only the current user's birth profile."""
        row = await db.scalar(
            select(UserAstrologyProfile).where(UserAstrologyProfile.user_id == user_id)
        )
        if row is None:
            return {"found": False, "message": "尚未设置星座档案"}
        return {
            "found": True,
            "profile": {
                "birthday": row.birthday.isoformat() if row.birthday else None,
                "birth_time": row.birth_time.isoformat() if row.birth_time else None,
                "birth_timezone": row.birth_timezone,
                "birth_place": row.birth_place,
                "birth_latitude": str(row.birth_latitude)
                if row.birth_latitude is not None
                else None,
                "birth_longitude": str(row.birth_longitude)
                if row.birth_longitude is not None
                else None,
                "constellation": row.constellation,
            },
        }

    @staticmethod
    async def update_profile(
        db: AsyncSession,
        user_id: int,
        req: AstrologyProfileUpdateRequest,
    ) -> dict[str, JsonValue]:
        """Save explicitly supplied fields with one profile per existing user."""
        user = await db.scalar(
            select(User.id)
            .where(
                User.id == user_id,
                User.is_active,
                ~User.is_deleted,
            )
            .with_for_update()
        )
        if user is None:
            raise AppException(msg="用户不存在或已停用")
        row = await db.scalar(
            select(UserAstrologyProfile).where(UserAstrologyProfile.user_id == user_id)
        )
        if row is None:
            row = UserAstrologyProfile(user_id=user_id)
            db.add(row)
        for name, value in req.model_dump(exclude_unset=True).items():
            setattr(row, name, value)
        await db.commit()
        return await AstrologyService.get_profile(db, user_id)

    @staticmethod
    async def get_horoscope(
        db: AsyncSession,
        user_id: int,
        req: HoroscopeToolRequest,
    ) -> dict[str, JsonValue]:
        """Return a shared fortune cache hit or an explicit missing-data result."""
        constellation = req.constellation
        if constellation is None:
            constellation = await db.scalar(
                select(UserAstrologyProfile.constellation).where(
                    UserAstrologyProfile.user_id == user_id,
                )
            )
        if not constellation:
            return {"found": False, "message": "请提供星座或先完善星座档案"}
        fortune_date = req.fortune_date or datetime.now(ZoneInfo(settings.AGENT_TIMEZONE)).date()
        row = await db.scalar(
            select(HoroscopeCache).where(
                HoroscopeCache.constellation == constellation,
                HoroscopeCache.fortune_date == fortune_date,
                HoroscopeCache.aspect == req.aspect,
            )
        )
        result: dict[str, JsonValue] = {
            "constellation": constellation,
            "fortune_date": fortune_date.isoformat(),
            "aspect": req.aspect,
        }
        if row is None or (row.expires_at is not None and row.expires_at <= datetime.now()):
            return {**result, "found": False, "message": "暂无对应日期和领域的运势数据"}
        return {
            **result,
            "found": True,
            "score": row.score,
            "data": row.raw_data,
            "source": row.source,
            "updated_at": row.updated_at.isoformat(),
        }

    @staticmethod
    async def save_horoscope_cache(db: AsyncSession, req: HoroscopeCacheRequest) -> None:
        """Upsert data supplied by a backend source; this is not a model tool."""
        from sqlalchemy.dialects.mysql import insert

        values = req.model_dump()
        stmt = insert(HoroscopeCache).values(**values)
        stmt = stmt.on_duplicate_key_update(
            score=stmt.inserted.score,
            raw_data=stmt.inserted.raw_data,
            source=stmt.inserted.source,
            expires_at=stmt.inserted.expires_at,
            updated_at=datetime.now(),
        )
        await db.execute(stmt)
        await db.commit()
