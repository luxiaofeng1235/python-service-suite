"""
============================================
用户数据模型模块
============================================
定义用户相关的 Pydantic 请求体、响应体、数据校验。
使用 Pydantic v2 语法。
"""

from pydantic import BaseModel, EmailStr, Field

# ==================== 请求体 ====================


class UserRegisterRequest(BaseModel):
    """用户注册请求体"""

    username: str = Field(..., min_length=2, max_length=50, description="用户名，2-50字符")
    password: str = Field(..., min_length=6, max_length=128, description="密码，6-128字符")
    email: EmailStr | None = Field(None, description="电子邮箱")
    nickname: str | None = Field(None, max_length=50, description="昵称")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "username": "test_user",
                    "password": "12345677",
                    "email": "test@example.com",
                    "nickname": "测试用户",
                }
            ]
        }
    }


class UserLoginRequest(BaseModel):
    """用户登录请求体"""

    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "username": "test_user",
                    "password": "12345677",
                }
            ]
        }
    }


class ForgotPasswordRequest(BaseModel):
    """忘记密码 - 请求发送重置邮件"""

    email: str = Field(..., description="注册时使用的邮箱地址")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "email": "test@example.com",
                }
            ]
        }
    }


class ResetPasswordRequest(BaseModel):
    """重置密码 - 验证码 + 新密码"""

    email: str = Field(..., description="注册时使用的邮箱地址")
    code: str = Field(..., min_length=6, max_length=6, description="邮件中收到的 6 位验证码")
    password: str = Field(..., min_length=6, max_length=128, description="新密码，6-128字符")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "email": "test@example.com",
                    "code": "123456",
                    "password": "new123456",
                }
            ]
        }
    }


# ==================== 响应体 ====================


class UserResponse(BaseModel):
    """用户信息响应体"""

    id: int = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    nickname: str | None = Field(None, description="昵称")
    email: str | None = Field(None, description="邮箱")
    is_super: bool = Field(False, description="是否管理员")
    is_active: bool = Field(True, description="是否启用")
    created_at: str | None = Field(None, description="创建时间")

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """Token 响应体"""

    access_token: str = Field(..., description="32位登录Token")
    token_type: str = Field("bearer", description="Token 类型")


class UserListResponse(BaseModel):
    """用户列表响应体"""

    items: list[UserResponse] = Field(..., description="用户列表")
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    size: int = Field(..., description="每页条数")
