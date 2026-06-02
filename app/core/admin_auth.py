"""
============================================
后台管理员鉴权依赖
============================================
提供 get_current_admin_user 依赖，用于后台接口鉴权。
从 admin_tokens + auth_admins 表校验 Token，独立于前台用户体系。
"""

from datetime import datetime

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependency import bearer_scheme
from app.database import get_session
from app.models.admin_token import AdminToken
from app.models.auth_admin import AuthAdmin


async def get_current_admin_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """
    后台接口鉴权依赖：校验 Bearer Token 并返回当前管理员信息。

    Returns:
        dict: 管理员信息（含 admin_id, username, nickname, is_super 等）

    Raises:
        HTTPException 401: Token 缺失或无效/已过期
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭证，请先登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(
        select(AdminToken, AuthAdmin)
        .join(AuthAdmin, AuthAdmin.id == AdminToken.admin_id)
        .where(
            AdminToken.token == credentials.credentials,
            AdminToken.is_active == True,  # noqa: E712
            AdminToken.expires_at > datetime.now(),
            AuthAdmin.is_active == True,  # noqa: E712
        )
    )
    row = result.first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token, admin = row
    return {
        "user_id": admin.id,
        "sub": str(admin.id),
        "username": admin.username,
        "nickname": admin.nickname,
        "is_super": bool(admin.is_super),
        "token_id": token.id,
        "token": credentials.credentials,
    }


async def require_super_admin(
    current_admin: dict = Depends(get_current_admin_user),
) -> dict:
    """超管依赖：仅允许 is_super 管理员访问"""
    if not current_admin.get("is_super"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无管理员权限",
        )
    return current_admin
