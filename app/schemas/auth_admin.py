"""
============================================
后台管理员 Pydantic 模型
============================================
"""

from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    """管理员登录请求"""

    username: str = Field(..., min_length=1, max_length=50, description="用户名")
    password: str = Field(..., min_length=1, max_length=128, description="密码")

    model_config = {
        "json_schema_extra": {
            "examples": [{"username": "admin", "password": "123456"}]
        }
    }


class AdminRegisterRequest(BaseModel):
    """管理员注册请求（需超管操作）"""

    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    nickname: str = Field("", max_length=50, description="昵称")

    model_config = {
        "json_schema_extra": {
            "examples": [{"username": "editor01", "password": "123456", "nickname": "编辑员"}]
        }
    }


class AdminTokenResponse(BaseModel):
    """管理员 Token 响应"""

    access_token: str = Field(..., description="访问 Token")
    token_type: str = Field("bearer", description="Token 类型")


class AdminUserResponse(BaseModel):
    """管理员信息响应"""

    id: int = Field(..., description="管理员ID")
    username: str = Field(..., description="用户名")
    nickname: str = Field(..., description="昵称")
    avatar: str | None = Field(None, description="头像URL")
    mobile: str | None = Field(None, description="手机号")
    email: str | None = Field(None, description="邮箱")
    sex: int | None = Field(0, description="性别 0=保密 1=男 2=女")
    remark: str | None = Field(None, description="备注")
    is_super: bool = Field(False, description="是否超管")
    is_active: bool = Field(True, description="是否启用")
    created_at: str | None = Field(None, description="创建时间")
    updated_at: str | None = Field(None, description="更新时间")


class AdminProfileUpdateRequest(BaseModel):
    """管理员修改资料请求体"""

    nickname: str | None = Field(None, max_length=50, description="昵称")
    avatar: str | None = Field(None, max_length=500, description="头像URL")
    mobile: str | None = Field(None, max_length=20, description="手机号")
    email: str | None = Field(None, max_length=255, description="邮箱")
    sex: int | None = Field(None, ge=0, le=2, description="性别 0=保密 1=男 2=女")
    remark: str | None = Field(None, max_length=500, description="备注")
