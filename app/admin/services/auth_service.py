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
from app.pkg.security import create_short_token, get_password_hash, verify_password
from app.models.admin_token import AdminToken
from app.models.auth_admin import AuthAdmin


class AdminAuthService:
    """管理员认证服务"""

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
        result = await db.execute(
            select(AuthAdmin).where(AuthAdmin.username == username)
        )
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
        result = await db.execute(
            select(AuthAdmin).where(AuthAdmin.username == username)
        )
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
