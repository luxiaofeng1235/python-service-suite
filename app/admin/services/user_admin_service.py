"""
============================================
后台用户管理业务逻辑
============================================
职责：管理员专属的用户管理操作，不依赖前台 UserService。
"""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.user_admin import AdminUserResponse, AdminUserUpdateRequest
from app.common.exception import AppException
from app.common.pagination import PageParams, paginate
from app.common.logging import get_logger
from app.models.user import User
from app.models.user_token import UserToken


class UserAdminService:
    """后台用户管理服务"""

    logger = get_logger(__name__)

    # ==================== 用户列表（含已注销） ====================

    @staticmethod
    async def get_user_list(
        db: AsyncSession,
        page_params: PageParams,
        is_deleted: bool | None = None,
    ) -> dict:
        """
        获取用户列表（后台管理，可包含已注销用户）

        Args:
            db: 数据库会话
            page_params: 分页参数
            is_deleted: 过滤已注销（None=全部, True=仅已注销, False=仅未注销）

        Returns:
            dict: {"items": [...], "total": N, "page": P, "size": S}
        """
        stmt = select(User).order_by(User.id)

        if is_deleted is not None:
            stmt = stmt.where(User.is_deleted == is_deleted)

        return await paginate(db, stmt, page_params)

    # ==================== 用户详情 ====================

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: int) -> AdminUserResponse:
        """
        根据 ID 获取用户详情（后台管理用，含 is_deleted 字段）

        Args:
            db: 数据库会话
            user_id: 用户ID

        Raises:
            AppException: 用户不存在
        """
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise AppException(msg="用户不存在")

        return AdminUserResponse(
            id=user.id,
            username=user.username,
            nickname=user.nickname,
            email=user.email,
            is_super=user.is_super,
            is_active=user.is_active,
            is_deleted=user.is_deleted,
            created_at=user.created_at.strftime("%Y-%m-%d %H:%M:%S") if user.created_at else None,
            deleted_at=user.deleted_at.strftime("%Y-%m-%d %H:%M:%S") if user.deleted_at else None,
        )

    # ==================== 更新用户 ====================

    @staticmethod
    async def update_user(
        db: AsyncSession,
        user_id: int,
        req: AdminUserUpdateRequest,
    ) -> AdminUserResponse:
        """
        更新用户信息（后台管理）

        Args:
            db: 数据库会话
            user_id: 用户ID
            req: 更新字段

        Raises:
            AppException: 用户不存在
        """
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise AppException(msg="用户不存在")

        update_data = req.model_dump(exclude_none=True)
        for field, value in update_data.items():
            setattr(user, field, value)

        await db.flush()
        await db.refresh(user)

        return AdminUserResponse(
            id=user.id,
            username=user.username,
            nickname=user.nickname,
            email=user.email,
            is_super=user.is_super,
            is_active=user.is_active,
            is_deleted=user.is_deleted,
            created_at=user.created_at.strftime("%Y-%m-%d %H:%M:%S") if user.created_at else None,
            deleted_at=user.deleted_at.strftime("%Y-%m-%d %H:%M:%S") if user.deleted_at else None,
        )

    # ==================== 删除用户（管理员强制注销） ====================

    @staticmethod
    async def delete_user(
        db: AsyncSession,
        user_id: int,
        operator_username: str,
    ) -> dict:
        """
        管理员强制注销用户（软删除，不依赖前台 UserService）

        - 标记 is_deleted=True，记录 deleted_at
        - 使所有 Token 失效
        - 记录操作日志

        Args:
            db: 数据库会话
            user_id: 要注销的用户ID
            operator_username: 操作的管理员用户名

        Raises:
            AppException: 用户不存在或已注销
        """
        result = await db.execute(
            select(User).where(User.id == user_id, User.is_deleted == False)  # noqa: E712
        )
        user = result.scalar_one_or_none()
        if not user:
            raise AppException(msg="用户不存在或已注销")

        now = datetime.now()
        user.is_deleted = True
        user.deleted_at = now

        # 使所有 Token 失效
        await db.execute(delete(UserToken).where(UserToken.user_id == user_id))

        UserAdminService.logger.warning(
            "管理员强制注销 | user_id=%s | operator=%s | deleted_at=%s",
            user_id,
            operator_username,
            now.strftime("%Y-%m-%d %H:%M:%S"),
        )

        return {"deleted": True, "deleted_at": now.strftime("%Y-%m-%d %H:%M:%S")}

    # ==================== 清理过期 Token ====================

    @staticmethod
    async def cleanup_expired_tokens(db: AsyncSession) -> dict:
        """
        清理过期 Token（后台管理，独立实现不依赖前台 UserService）

        Args:
            db: 数据库会话

        Returns:
            dict: {"deleted": N}
        """
        result = await db.execute(delete(UserToken).where(UserToken.expires_at <= datetime.now()))
        return {"deleted": result.rowcount or 0}

    # ==================== 禁用 / 启用 ====================

    @staticmethod
    async def set_user_active(db: AsyncSession, user_id: int, is_active: bool) -> AdminUserResponse:
        """
        禁用/启用用户账户

        Args:
            db: 数据库会话
            user_id: 用户ID
            is_active: True=启用, False=禁用

        Raises:
            AppException: 用户不存在或已注销
        """
        from app.models.user import User

        result = await db.execute(
            select(User).where(User.id == user_id, User.is_deleted == False)  # noqa: E712
        )
        user = result.scalar_one_or_none()
        if not user:
            raise AppException(msg="用户不存在或已注销")

        user.is_active = is_active
        await db.flush()
        await db.refresh(user)

        return AdminUserResponse(
            id=user.id,
            username=user.username,
            nickname=user.nickname,
            email=user.email,
            is_super=user.is_super,
            is_active=user.is_active,
            is_deleted=user.is_deleted,
            created_at=user.created_at.strftime("%Y-%m-%d %H:%M:%S") if user.created_at else None,
            deleted_at=user.deleted_at.strftime("%Y-%m-%d %H:%M:%S") if user.deleted_at else None,
        )
