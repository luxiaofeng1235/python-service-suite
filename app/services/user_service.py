"""
============================================
用户业务逻辑服务层
============================================
所有用户相关的业务逻辑（注册、查询、认证）都在此实现。
Controller 通过调用 Service 方法完成业务，不写任何逻辑代码。
"""

import base64
import random
import string
import uuid
from datetime import datetime, timedelta
from io import BytesIO

from captcha.image import ImageCaptcha
from fastapi import Request
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import AppException
from app.common.pagination import PageParams, paginate
from app.common.ratelimit import RateLimiter
from app.core.config import settings
from app.models.user import User
from app.models.user_token import UserToken
from app.models.verification_code import VerificationCode
from app.pkg.logging import request_logger
from app.pkg.redis_client import redis_client
from app.pkg.security import (
    create_short_token,
    get_password_hash,
    verify_password,
)
from app.schemas.user import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.utils.email import EmailUtil
from app.utils.time_ import TimeUtil
from app.utils.url_ import get_client_ip


class UserService:
    """用户业务逻辑服务"""

    # ==================== 速率限制器 ====================
    _register_limiter = RateLimiter(max_requests=3, window_seconds=600)  # 注册：3次/10分钟
    _login_limiter = RateLimiter(max_requests=5, window_seconds=300)  # 登录：5次/5分钟
    _forgot_limiter = RateLimiter(
        max_requests=settings.RATE_LIMIT_FORGOT_PASSWORD_MAX,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )
    _reset_limiter = RateLimiter(
        max_requests=settings.RATE_LIMIT_RESET_PASSWORD_MAX,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )

    # ==================== 注册 ====================

    @staticmethod
    async def register(
        db: AsyncSession, req: UserRegisterRequest, request: Request | None = None
    ) -> UserResponse:
        """
        用户注册

        Args:
            db: 数据库会话
            req: 注册请求体（用户名、密码、邮箱等）
            request: 请求对象（用于限流）

        Returns:
            注册成功的用户信息

        Raises:
            AppException: 用户名已存在 / 注册过于频繁
        """
        # 1. 速率限制
        client_ip = get_client_ip(request) if request else ""
        if client_ip and not await UserService._register_limiter.check(f"register:{client_ip}"):
            raise AppException(msg="注册过于频繁，请 10 分钟后再试")

        # 2. 检查用户名是否已存在
        stmt = select(User).where(User.username == req.username)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            raise AppException(msg=f"用户名 '{req.username}' 已被注册")

        # 2. 创建用户并入库
        user = User(
            username=req.username,
            password_hash=get_password_hash(req.password),
            nickname=req.nickname or req.username,
            email=req.email,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)  # 刷新所有字段（避免 async 延迟加载报错）

        return UserResponse(
            id=user.id,
            username=user.username,
            nickname=user.nickname,
            email=user.email,
            is_active=user.is_active,
            created_at=TimeUtil.format_datetime(user.created_at),
        )

    # ==================== 登录 ====================

    @staticmethod
    async def authenticate(
        db: AsyncSession, req: UserLoginRequest, request: Request | None = None
    ) -> str:
        """
        用户登录认证

        Args:
            db: 数据库会话
            req: 登录请求体（用户名、密码、验证码）
            request: 请求对象（用于限流及 IP 记录）

        Returns:
            短 Token 字符串

        Raises:
            AppException: 用户名或密码错误 / 登录过于频繁 / 验证码错误
        """
        client_ip = get_client_ip(request) if request else ""

        # 1. 校验图片验证码
        if req.captcha_id and req.captcha_code:
            cached_code = await redis_client.get(f"captcha_id:{req.captcha_id}")
            if not cached_code or cached_code != req.captcha_code.upper():
                raise AppException(msg="验证码错误")
            # 验证码使用后立即删除，防重复使用
            await redis_client.delete(f"captcha_id:{req.captcha_id}")
        elif not req.captcha_id and not req.captcha_code:
            # 兼容旧版本：不传验证码也放行（仅限登录接口）
            pass
        else:
            raise AppException(msg="验证码参数不完整")

        # 2. 速率限制
        if client_ip and not await UserService._login_limiter.check(
            f"login:{client_ip}:{req.username}"
        ):
            raise AppException(msg="登录过于频繁，请 5 分钟后再试")

        # 3. 按用户名查找用户
        stmt = select(User).where(User.username == req.username)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            raise AppException(msg="用户名或密码错误")

        # 4. 校验密码
        if not verify_password(req.password, user.password_hash):
            raise AppException(msg="用户名或密码错误")

        # 5. 更新登录 IP 和时间
        user.last_login_ip = client_ip
        user.last_login_at = datetime.now()

        # 6. 生成短 Token 并落库
        token = create_short_token()
        expires_at = datetime.now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        db.add(
            UserToken(
                user_id=user.id,
                token=token,
                expires_at=expires_at,
                is_active=True,
            )
        )
        await db.commit()
        return token

    # ==================== 退出登录 ====================

    @staticmethod
    async def logout(db: AsyncSession, token_id: int) -> dict:
        """退出登录，令当前 Token 失效"""
        await db.execute(
            update(UserToken)
            .where(UserToken.id == token_id)
            .values(is_active=False, updated_at=datetime.now())
        )
        await db.commit()
        return {"message": "退出登录成功"}

    @staticmethod
    async def cleanup_expired_tokens(db: AsyncSession) -> dict:
        """清理过期 Token"""
        result = await db.execute(delete(UserToken).where(UserToken.expires_at <= datetime.now()))
        await db.commit()
        return {"deleted": result.rowcount or 0}

    # ==================== 忘记密码 ====================

    @staticmethod
    def _generate_code(length: int = 6) -> str:
        """生成指定位数的数字验证码"""
        return "".join(random.choices(string.digits, k=length))

    @staticmethod
    async def generate_captcha() -> dict:
        """生成图片验证码，返回验证码 ID 和 base64 图片。"""
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        captcha_id = str(uuid.uuid4())

        await redis_client.set(f"captcha_id:{captcha_id}", code, ex=300)

        image = ImageCaptcha(width=160, height=80)
        buf = BytesIO()
        image.write(code, buf)
        buf.seek(0)

        return {
            "captcha_id": captcha_id,
            "image_base64": base64.b64encode(buf.getvalue()).decode(),
        }

    @staticmethod
    async def forgot_password(db: AsyncSession, req: ForgotPasswordRequest) -> dict:
        """
        忘记密码 — 如邮箱存在则发送验证码邮件

        安全设计：无论邮箱是否存在都返回同样提示，防止枚举注册邮箱。

        Args:
            db:  数据库会话
            req: 包含邮箱的请求体

        Returns:
            dict: 提示信息

            AppException: SMTP 未配置
        """
        uniform_msg = "如果该邮箱已注册，您将收到一封密码重置邮件"

        # 1. 速率限制 — 按邮箱防刷
        if not await UserService._forgot_limiter.check(f"forgot:{req.email}"):
            raise AppException(msg="请求过于频繁，请稍后再试")

        # 2. 检查 SMTP 是否配置（全局前置）
        if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
            raise AppException(msg="系统未配置邮件发送功能，请联系管理员")

        # 3. 查找用户 — 找不到也走统一消息
        stmt = select(User).where(User.email == req.email)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            return {"message": uniform_msg, "email": req.email}

        # 4. 生成 6 位验证码
        code = UserService._generate_code()

        # 5. 计算过期时间
        expire_minutes = settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
        expires_at = datetime.now() + timedelta(minutes=expire_minutes)

        # 6. 存储验证码到 Redis；数据库保留一份记录用于审计和兜底
        await UserService._cache_reset_code(user.email, code, expire_minutes * 60)

        vc = VerificationCode(
            email=user.email,
            code=code,
            purpose="password_reset",
            expires_at=expires_at,
        )
        db.add(vc)

        # 7. 发送验证码邮件
        success = await EmailUtil.send_verification_code_email(
            to_email=user.email,
            username=user.nickname or user.username,
            code=code,
            expire_minutes=expire_minutes,
        )

        if not success:
            raise AppException(msg="邮件发送失败，请稍后重试")

        await db.commit()

        return {
            "message": uniform_msg,
            "email": user.email,
        }

    # ==================== 重置密码 ====================

    @staticmethod
    async def reset_password(db: AsyncSession, req: ResetPasswordRequest) -> dict:
        """
        重置密码 — 通过验证码校验并更新新密码

        Args:
            db:  数据库会话
            req: 包含邮箱 + 验证码 + 新密码的请求体

        Returns:
            dict: 提示信息

        Raises:
            AppException: 验证码无效/过期 或 用户不存在
        """
        # 1. 速率限制 — 按邮箱防刷
        if not await UserService._reset_limiter.check(f"reset:{req.email}"):
            raise AppException(msg="操作过于频繁，请稍后再试")

        now = datetime.now()

        # 2. 优先使用 Redis 校验验证码；Redis 不可用或未命中时查数据库兜底
        redis_code = await UserService._get_cached_reset_code(req.email)
        if redis_code is not None and redis_code != req.code:
            raise AppException(msg="验证码无效或已过期，请重新申请")

        stmt = (
            select(VerificationCode)
            .where(
                VerificationCode.email == req.email,
                VerificationCode.code == req.code,
                VerificationCode.purpose == "password_reset",
                ~VerificationCode.used,
                VerificationCode.expires_at > now,
            )
            .order_by(VerificationCode.id.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        vc = result.scalar_one_or_none()

        if redis_code is None and not vc:
            raise AppException(msg="验证码无效或已过期，请重新申请")

        # 3. 标记验证码为已使用；删除 Redis 缓存，防止重复使用
        if vc:
            vc.used = True
        await UserService._remove_cached_reset_code(req.email)

        # 4. 查找用户
        stmt = select(User).where(User.email == req.email)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            raise AppException(msg="用户不存在")

        # 5. 更新密码
        user.password_hash = get_password_hash(req.password)
        await db.commit()

        return {"message": "密码重置成功，请使用新密码登录"}

    # ==================== 验证码缓存 ====================

    @staticmethod
    async def _cache_reset_code(email: str, code: str, ttl: int) -> None:
        """缓存重置密码验证码；Redis 不可用时仅记录日志，不影响数据库兜底"""
        try:
            await redis_client.set(f"code:{email}", code, ex=ttl)
        except Exception:
            request_logger.opt(exception=True).warning("Redis 验证码缓存写入失败 email={}", email)

    @staticmethod
    async def _get_cached_reset_code(email: str) -> str | None:
        """读取 Redis 中的重置密码验证码"""
        try:
            return await redis_client.get(f"code:{email}")
        except Exception:
            request_logger.opt(exception=True).warning("Redis 验证码缓存读取失败 email={}", email)
            return None

    @staticmethod
    async def _remove_cached_reset_code(email: str) -> None:
        """删除 Redis 中的重置密码验证码"""
        try:
            await redis_client.delete(f"code:{email}")
        except Exception:
            request_logger.opt(exception=True).warning("Redis 验证码缓存删除失败 email={}", email)

    # ==================== 用户列表 ====================

    @staticmethod
    async def get_user_list(db: AsyncSession, page_params: PageParams) -> dict:
        """
        获取用户列表（分页）

        Args:
            db: 数据库会话
            page_params: 分页参数

        Returns:
            dict: {"items": [...], "total": N, "page": P, "size": S, "total_page": TP}
        """
        stmt = select(User).order_by(User.id)
        data = await paginate(db, stmt, page_params)

        items = [
            UserResponse(
                id=u.id,
                username=u.username,
                nickname=u.nickname,
                email=u.email,
                is_active=u.is_active,
                created_at=TimeUtil.format_datetime(u.created_at),
            )
            for u in data["items"]
        ]

        return {**data, "items": items}

    # ==================== 获取单个用户 ====================

    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: int) -> UserResponse | None:
        """
        根据 ID 获取用户信息

        Args:
            db: 数据库会话
            user_id: 用户ID

        Returns:
            用户信息，不存在则返回 None
        """
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return None

        return UserResponse(
            id=user.id,
            username=user.username,
            nickname=user.nickname,
            email=user.email,
            is_active=user.is_active,
            created_at=TimeUtil.format_datetime(user.created_at),
        )

    # ==================== 账号注销 ====================

    @staticmethod
    async def delete_account(db: AsyncSession, user_id: int, username: str) -> dict:
        """
        账号注销（软删除）

        - 标记 is_deleted=True，记录 deleted_at
        - 使所有 Token 失效（删除 UserToken）
        - 记录操作日志

        Args:
            db: 数据库会话
            user_id: 用户ID
            username: 用户名（用于日志记录）

        Returns:
            dict: 提示信息
        """
        # 1. 查找用户
        result = await db.execute(select(User).where(User.id == user_id, ~User.is_deleted))
        user = result.scalar_one_or_none()
        if not user:
            raise AppException(msg="用户不存在或已注销")

        # 2. 软删除标记
        now = datetime.now()
        user.is_deleted = True
        user.deleted_at = now

        # 3. 使所有 Token 失效
        await db.execute(delete(UserToken).where(UserToken.user_id == user_id))

        # 4. 记录操作日志
        request_logger.warning(
            "账号注销 | user_id={} | username={} | deleted_at={}",
            user_id,
            username,
            TimeUtil.format_datetime(now),
        )

        await db.commit()

        return {"deleted": True, "deleted_at": TimeUtil.format_datetime(now)}
