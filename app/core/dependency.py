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

# ==================== Token 提取方案 ====================
bearer_scheme = HTTPBearer(auto_error=False)
"""
auto_error=False：让依赖自行处理错误，避免白名单路由因无 Token 直接 403
"""

# ==================== 白名单配置 ====================
WHITE_LIST: list[str] = [
    item.strip() for item in settings.AUTH_WHITE_LIST.split(",") if item.strip()
]
"""无需鉴权的白名单路由前缀"""


def check_white_list(request: Request) -> bool:
    """检查当前请求路径是否在白名单中"""
    path = request.url.path
    for white_path in WHITE_LIST:
        if path == white_path:
            return True
        if white_path == "/":
            continue
        if path.startswith(f"{white_path.rstrip('/')}/"):
            return True
    return False


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
            UserToken.is_active == True,  # noqa: E712
            UserToken.expires_at > datetime.now(),
            User.is_active == True,  # noqa: E712
            User.is_deleted == False,  # noqa: E712
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
        "token_id": token.id,
        "token": credentials.credentials,
    }



