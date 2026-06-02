"""
============================================
RBAC 鉴权依赖
============================================
提供 require_permission 依赖工厂，用于后台管理接口权限控制。
使用后台管理员鉴权（admin_tokens + auth_admins），
完全独立于前台用户的 users + user_tokens 体系。
超管（is_super=True）自动跳过权限校验。
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_auth import get_current_admin_user
from app.database import get_session
from app.services.rbac_service import RbacService


def require_permission(resource: str, action: str):
    """
    权限校验依赖工厂

    用法：
        @router.get("/admin/users/list",
            dependencies=[Depends(require_permission("user", "list"))],
        )

    鉴权走后台管理员表（auth_admins），不走前台 users 表。

    Args:
        resource: 资源名（如 "user"、"role"、"permission"）
        action: 操作名（如 "list"、"create"、"delete"）

    Returns:
        FastAPI Depends 可调用对象
    """

    async def _check(
        current_admin: dict = Depends(get_current_admin_user),
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        # 超管直通
        if current_admin.get("is_super"):
            return current_admin

        admin_id = current_admin.get("user_id")
        if not admin_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限访问",
            )

        has_perm = await RbacService.check_permission(
            db, user_id=admin_id, resource=resource, action=action,
        )
        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"无权限：需要 {resource}:{action}",
            )

        return current_admin

    return _check
