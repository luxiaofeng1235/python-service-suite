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
    is_super: bool = Field(False, description="是否超管")
    is_active: bool = Field(True, description="是否启用")
    created_at: str | None = Field(None, description="创建时间")
