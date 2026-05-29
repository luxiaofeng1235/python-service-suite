"""
Quick local connectivity test for database and Redis.

Usage:
    python test_python.py

The script reads project settings from .env through app.core.config.settings.
It does not start FastAPI.
"""

from __future__ import annotations

import asyncio
import sys
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings


def mask_url(url: str | None) -> str:
    """Hide password/token-like data in a URL before printing."""
    if not url:
        return "not configured"

    parsed = urlsplit(url)
    if not parsed.netloc:
        return url

    netloc = parsed.netloc
    if "@" in netloc:
        userinfo, hostinfo = netloc.rsplit("@", 1)
        if ":" in userinfo:
            username, _password = userinfo.split(":", 1)
            userinfo = f"{username}:***"
        else:
            userinfo = "***"
        netloc = f"{userinfo}@{hostinfo}"

    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def engine_kwargs(database_url: str) -> dict:
    """SQLite async driver does not support MySQL-style pool arguments."""
    if database_url.startswith("sqlite"):
        return {"echo": False}

    return {
        "echo": False,
        "pool_size": 3,
        "max_overflow": 2,
        "pool_recycle": 1800,
        "pool_pre_ping": True,
    }


async def test_database() -> bool:
    print(f"[DB] url: {mask_url(settings.DATABASE_URL)}")
    engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs(settings.DATABASE_URL))

    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            value = result.scalar_one()
            print(f"[DB] SELECT 1 => {value}")

            if settings.DATABASE_URL.startswith("mysql"):
                db_result = await conn.execute(text("SELECT DATABASE()"))
                print(f"[DB] current database => {db_result.scalar_one()}")

        print("[DB] OK")
        return True
    except Exception as exc:
        print(f"[DB] FAILED: {exc!r}")
        return False
    finally:
        await engine.dispose()


async def test_redis() -> bool:
    redis_url = settings.REDIS_URL
    print(f"[Redis] url: {mask_url(redis_url)}")

    if not redis_url:
        print("[Redis] SKIPPED: REDIS_URL is not configured")
        return True

    try:
        from redis.asyncio import Redis
    except Exception as exc:
        print(f"[Redis] FAILED: redis package is not installed: {exc!r}")
        return False

    client = Redis.from_url(redis_url, decode_responses=True)
    key = "health:test_python"
    value = "ok"

    try:
        pong = await client.ping()
        print(f"[Redis] ping => {pong}")

        await client.set(key, value, ex=30)
        cached = await client.get(key)
        print(f"[Redis] set/get => {cached}")

        if cached != value:
            print("[Redis] FAILED: cached value mismatch")
            return False

        await client.delete(key)
        print("[Redis] OK")
        return True
    except Exception as exc:
        print(f"[Redis] FAILED: {exc!r}")
        return False
    finally:
        await client.aclose()


async def main() -> int:
    print("== FastAPI service dependency check ==")

    db_ok = await test_database()
    redis_ok = await test_redis()

    if db_ok and redis_ok:
        print("== Result: OK ==")
        return 0

    print("== Result: FAILED ==")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
