"""
============================================
全局鉴权依赖模块
============================================
提供 get_current_user 依赖注入，所有接口默认需要登录。
通过 WHITE_LIST 配置白名单路由，无需 Token 即可访问。
"""

from datetime import datetime

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.config import settings
from app.database import get_session
from app.models.user import User
from app.models.user_token import UserToken
from app.utils.time_ import TimeUtil

# ==================== Token 提取方案 ====================
bearer_scheme = HTTPBearer(auto_error=False)
"""
auto_error=False：让依赖自行处理错误，避免白名单路由因无 Token 直接 403
"""

# ==================== 白名单配置 ====================
WHITE_LIST: list[str] = settings.white_list
"""无需鉴权的白名单路由前缀"""


def match_white_list(path: str) -> bool:
    """
    纯路径白名单匹配。

    把传入的 ASGI/HTTP path 与 ``settings.white_list`` 比对：
    路径完全等于某条配置，或属于该配置的子路径
    （即 ``prefix.rstrip('/') + '/'`` 是其前缀）时，判定为白名单命中。
    单独的 ``/`` 条目主动忽略，避免根条目把整个站点放行。

    给 ``check_white_list``（FastAPI Request 依赖使用）和
    encrypt 中间件（拿到的是裸 ASGI ``scope['path']``）共用，
    避免两边各写一遍后悄悄走形 —— 缺了 ``/`` 边界，
    ``/api/user/login`` 会被 ``/api/user/loginabc`` 误命中。
    """
    for white_path in WHITE_LIST:
        if not white_path or white_path == "/":
            continue
        if path == white_path:
            return True
        if path.startswith(f"{white_path.rstrip('/')}/"):
            return True
    return False


def check_white_list(request: Request) -> bool:
    """检查当前请求路径是否在白名单中"""
    return match_white_list(request.url.path)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """
    全局依赖：获取当前登录用户信息

    白名单路径自动跳过鉴权。
    其他路径必须携带有效的 Bearer Token，否则抛出 401。

    Returns:
        解码后的用户信息 dict（含 user_id 等）

    Raises:
        HTTPException 401: Token 缺失或无效
    """
    # 白名单路径允许匿名访问；如果主动携带 Token，则仍解析用户信息，便于可选登录接口做用户隔离。
    if check_white_list(request) and credentials is None:
        return {"user_id": None, "username": "anonymous"}

    # 检查 Token 是否存在
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭证，请先登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    result = await db.execute(
        select(UserToken, User)
        .join(User, User.id == UserToken.user_id)
        .where(
            UserToken.token == credentials.credentials,
            UserToken.is_active,
            UserToken.expires_at > datetime.now(),
            User.is_active,
            ~User.is_deleted,
        )
    )
    row = result.first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token, user = row
    return {
        "user_id": user.id,
        "sub": str(user.id),
        "username": user.username,
        "nickname": user.nickname,
        "email": user.email or "",
        "created_at": TimeUtil.format_datetime(user.created_at, default=""),
        "token_id": token.id,
        "token": credentials.credentials,
    }
