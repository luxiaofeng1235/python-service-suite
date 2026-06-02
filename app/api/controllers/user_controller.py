"""
============================================
用户接口控制器层
============================================
职责：只负责路由定义、接收请求、参数校验、返回响应。
严禁在此写任何业务逻辑——所有业务逻辑下沉到 Service 层。
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.user import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    UserLoginRequest,
    UserRegisterRequest,
)
from app.common.pagination import PageParams
from app.common.response import Response
from app.core.dependency import get_current_user
from app.database import get_session
from app.services.user_service import UserService

# ==================== 路由定义 ====================
router = APIRouter(prefix="/api/user", tags=["用户管理"])


# ==================== 注册 ====================


@router.post("/register", summary="用户注册")
async def register(
    req: UserRegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    """
    用户注册接口

    - 用户名唯一校验
    - 密码自动加密存储
    """
    data = await UserService.register(db, req, request=request)
    return Response.success(data, msg="注册成功")


# ==================== 登录 ====================


@router.post("/login", summary="用户登录")
async def login(
    req: UserLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    """
    用户登录接口

    - 校验用户名和密码
    - 签发短 Token
    - 记录登录 IP 和时间到用户表
    """
    token = await UserService.authenticate(db, req, request=request)
    return Response.success(
        data={"access_token": token, "token_type": "bearer"},
        msg="登录成功",
    )


@router.post("/logout", summary="退出登录")
async def logout(
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """退出登录，使当前 Token 立即失效"""
    data = await UserService.logout(db, current_user["token_id"])
    return Response.success(data=data, msg="退出成功")


# ==================== 忘记密码 ====================


@router.post("/forgot-password", summary="忘记密码（发送验证码邮件）")
async def forgot_password(req: ForgotPasswordRequest, db: AsyncSession = Depends(get_session)):
    """
    忘记密码 — 发送验证码到邮箱

    - 根据邮箱查找用户
    - 生成 6 位数字验证码并存储到数据库
    - 发送带验证码的 HTML 邮件
    """
    data = await UserService.forgot_password(db, req)
    return Response.success(data)


# ==================== 重置密码 ====================


@router.post("/reset-password", summary="重置密码（通过验证码设置新密码）")
async def reset_password(req: ResetPasswordRequest, db: AsyncSession = Depends(get_session)):
    """
    重置密码 — 使用邮箱和验证码设置新密码

    - 验证邮箱 + 验证码匹配
    - 更新用户密码
    """
    data = await UserService.reset_password(db, req)
    return Response.success(data)


# ==================== 用户列表 ====================


@router.get("/list", summary="用户列表（分页）")
async def list_users(
    page_params: PageParams = Depends(),
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """
    获取用户列表（需登录）

    - 分页查询
    - 默认每页 10 条
    """
    data = await UserService.get_user_list(db, page_params)
    return Response.success(data)


# ==================== 当前用户信息 ====================


@router.get("/center", summary="获取当前登录用户信息")
async def get_me(current_user: dict = Depends(get_current_user)):
    """
    获取当前登录用户信息（根据 Token）
    """
    return Response.success(data=current_user)


# ==================== 账号注销 ====================


@router.delete("/delete", summary="注销当前账号")
async def delete_account(
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
):
    """
    注销当前登录账号（软删除）

    - 标记 is_deleted=True
    - 清空该用户所有 Token，强制下线
    """
    data = await UserService.delete_account(
        db,
        user_id=current_user["user_id"],
        username=current_user["username"],
    )
    return Response.success(data=data, msg="账号已注销")
