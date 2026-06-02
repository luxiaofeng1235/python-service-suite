"""
============================================
后台用户管理 Pydantic 模型
============================================
"""

from pydantic import BaseModel, Field


# ==================== 请求体 ====================


class AdminUserUpdateRequest(BaseModel):
    """管理后台 - 更新用户信息"""

    nickname: str | None = Field(None, max_length=50, description="昵称")
    is_super: bool | None = Field(None, description="是否管理员")
    is_active: bool | None = Field(None, description="是否启用")


# ==================== 响应体 ====================


class AdminUserResponse(BaseModel):
    """管理后台 - 用户信息响应（比前台多 is_deleted 等字段）"""

    id: int = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    nickname: str | None = Field(None, description="昵称")
    email: str | None = Field(None, description="邮箱")
    is_super: bool = Field(False, description="是否管理员")
    is_active: bool = Field(True, description="是否启用")
    is_deleted: bool = Field(False, description="是否已注销")
    created_at: str | None = Field(None, description="创建时间")
    deleted_at: str | None = Field(None, description="注销时间")

    model_config = {"from_attributes": True}
