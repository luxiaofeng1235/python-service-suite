"""
============================================
后台管理员认证服务
============================================
提供管理员登录、退出登录功能，独立于前台用户认证。
"""

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import AppException
from app.core.config import settings
from app.models.admin_token import AdminToken
from app.models.auth_admin import AuthAdmin
from app.pkg.security import create_short_token, get_password_hash, verify_password
from app.schemas.auth_admin import AdminUserResponse
from app.utils.time_ import TimeUtil


class AdminAuthService:
    """管理员认证服务"""

    @staticmethod
    def _to_admin_response(admin: AuthAdmin) -> AdminUserResponse:
        """序列化管理员响应，避免暴露敏感字段。"""
        return AdminUserResponse(
            id=admin.id,
            username=admin.username,
            nickname=admin.nickname,
            avatar=admin.avatar,
            mobile=admin.mobile,
            email=admin.email,
            sex=admin.sex,
            remark=admin.remark,
            is_super=bool(admin.is_super),
            is_active=bool(admin.is_active),
            created_at=TimeUtil.format_datetime(admin.created_at),
            updated_at=TimeUtil.format_datetime(admin.updated_at),
        )

    @staticmethod
    async def register(
        db: AsyncSession,
        username: str,
        password: str,
        nickname: str = "",
    ) -> AuthAdmin:
        """
        注册新管理员（需超管操作）

        Args:
            db: 数据库会话
            username: 用户名
            password: 明文密码
            nickname: 昵称

        Raises:
            AppException: 用户名已存在
        """
        # 检查用户名是否已存在
        result = await db.execute(select(AuthAdmin).where(AuthAdmin.username == username))
        if result.scalar_one_or_none():
            raise AppException(msg="用户名已存在")

        admin = AuthAdmin(
            username=username,
            password_hash=get_password_hash(password),
            nickname=nickname or username,
            is_super=False,
            is_active=True,
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        return admin

    @staticmethod
    async def authenticate(db: AsyncSession, username: str, password: str) -> str:
        """
        管理员登录认证

        Args:
            db: 数据库会话
            username: 管理员用户名
            password: 明文密码

        Returns:
            短 Token 字符串

        Raises:
            AppException: 用户名或密码错误 / 账号已禁用
        """
        # 1. 按用户名查找管理员
        result = await db.execute(select(AuthAdmin).where(AuthAdmin.username == username))
        admin = result.scalar_one_or_none()
        if not admin:
            raise AppException(msg="用户名或密码错误")

        # 2. 校验密码
        if not verify_password(password, admin.password_hash):
            raise AppException(msg="用户名或密码错误")

        # 3. 检查是否启用
        if not admin.is_active:
            raise AppException(msg="账号已禁用，请联系超管")

        # 4. 生成短 Token 并落库（立即提交，否则后续请求查不到）
        token = create_short_token()
        expires_at = datetime.now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        db.add(
            AdminToken(
                admin_id=admin.id,
                token=token,
                expires_at=expires_at,
                is_active=True,
            )
        )
        await db.commit()
        return token

    @staticmethod
    async def logout(db: AsyncSession, token_id: int) -> dict:
        """退出登录，令当前 Token 失效"""
        await db.execute(
            update(AdminToken)
            .where(AdminToken.id == token_id)
            .values(is_active=False, updated_at=datetime.now())
        )
        await db.commit()
        return {"message": "退出登录成功"}

    @staticmethod
    async def get_admin_info(db: AsyncSession, admin_id: int) -> AuthAdmin:
        """
        获取管理员完整信息

        Raises:
            AppException: 管理员不存在
        """
        result = await db.execute(select(AuthAdmin).where(AuthAdmin.id == admin_id))
        admin = result.scalar_one_or_none()
        if not admin:
            raise AppException(msg="管理员不存在")
        return admin

    @staticmethod
    async def get_admin_response(db: AsyncSession, admin_id: int) -> AdminUserResponse:
        """获取管理员响应体。"""
        admin = await AdminAuthService.get_admin_info(db, admin_id)
        return AdminAuthService._to_admin_response(admin)

    @staticmethod
    async def update_profile(
        db: AsyncSession, admin_id: int, update_data: dict
    ) -> AdminUserResponse:
        """
        修改管理员个人资料

        Raises:
            AppException: 管理员不存在
        """
        if not update_data:
            raise AppException(msg="没有需要修改的字段")

        result = await db.execute(select(AuthAdmin).where(AuthAdmin.id == admin_id))
        admin = result.scalar_one_or_none()
        if not admin:
            raise AppException(msg="管理员不存在")

        for field, value in update_data.items():
            setattr(admin, field, value)
        await db.commit()
        await db.refresh(admin)
        return AdminAuthService._to_admin_response(admin)

    @staticmethod
    async def update_avatar(db: AsyncSession, admin_id: int, avatar_url: str) -> AdminUserResponse:
        """
        更新管理员头像

        Raises:
            AppException: 管理员不存在
        """
        result = await db.execute(select(AuthAdmin).where(AuthAdmin.id == admin_id))
        admin = result.scalar_one_or_none()
        if not admin:
            raise AppException(msg="管理员不存在")

        admin.avatar = avatar_url
        await db.commit()
        await db.refresh(admin)
        return AdminAuthService._to_admin_response(admin)

    @staticmethod
    async def list_admins(
        db: AsyncSession,
        page_params,
    ) -> dict:
        """分页获取管理员列表。"""
        from app.common.pagination import paginate

        result = await paginate(
            db,
            select(AuthAdmin).order_by(AuthAdmin.id),
            page_params,
        )
        return {
            **result,
            "items": [AdminAuthService._to_admin_response(admin) for admin in result["items"]],
        }

    @staticmethod
    async def toggle_admin_active(
        db: AsyncSession,
        admin_id: int,
        operator_admin_id: int,
    ) -> dict:
        """切换管理员启用状态。"""
        if operator_admin_id == admin_id:
            raise AppException(msg="不能对自己操作")

        result = await db.execute(select(AuthAdmin).where(AuthAdmin.id == admin_id))
        admin = result.scalar_one_or_none()
        if not admin:
            raise AppException(msg="管理员不存在")

        if admin.is_super:
            raise AppException(msg="不能操作超管账号")

        admin.is_active = not admin.is_active
        await db.commit()
        await db.refresh(admin)

        return {
            "is_active": bool(admin.is_active),
            "status": "启用" if admin.is_active else "禁用",
        }
