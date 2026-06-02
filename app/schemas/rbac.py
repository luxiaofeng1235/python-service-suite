"""
============================================
RBAC 管理 Pydantic 模型
============================================
"""

from pydantic import BaseModel, Field


# ==================== 角色 ====================


class RoleCreateRequest(BaseModel):
    """创建角色"""

    name: str = Field(..., min_length=2, max_length=50, description="角色名")
    description: str | None = Field(None, max_length=255, description="角色描述")

    model_config = {
        "json_schema_extra": {
            "examples": [{"name": "editor", "description": "内容编辑员"}]
        }
    }


class RoleUpdateRequest(BaseModel):
    """更新角色"""

    name: str | None = Field(None, min_length=2, max_length=50, description="角色名")
    description: str | None = Field(None, max_length=255, description="角色描述")


class RoleResponse(BaseModel):
    """角色响应"""

    id: int = Field(..., description="角色ID")
    name: str = Field(..., description="角色名")
    description: str | None = Field(None, description="角色描述")
    is_system: bool = Field(False, description="系统内置")
    created_at: str | None = Field(None, description="创建时间")

    model_config = {"from_attributes": True}


# ==================== 权限目录 ====================


class PermissionCreateRequest(BaseModel):
    """创建权限目录条目"""

    resource: str = Field(..., min_length=1, max_length=50, description="资源名（如 user）")
    action: str = Field(..., min_length=1, max_length=50, description="操作名（如 list）")
    description: str | None = Field(None, max_length=255, description="中文说明")


class PermissionResponse(BaseModel):
    """权限目录条目响应"""

    id: int = Field(..., description="权限ID")
    resource: str = Field(..., description="资源名")
    action: str = Field(..., description="操作名")
    description: str | None = Field(None, description="中文说明")

    model_config = {"from_attributes": True}


# ==================== 角色-权限分配 ====================


class PermissionAssignRequest(BaseModel):
    """添加/移除角色权限"""

    resource: str = Field(..., min_length=1, max_length=50, description="资源名（如 user）")
    action: str = Field(..., min_length=1, max_length=50, description="操作名（如 delete）")

    model_config = {
        "json_schema_extra": {
            "examples": [{"resource": "user", "action": "delete"}]
        }
    }


class RolePermissionResponse(BaseModel):
    """角色拥有的权限（含描述）"""

    resource: str = Field(..., description="资源名")
    action: str = Field(..., description="操作名")
    description: str = Field("", description="中文说明")


# ==================== 用户-角色 ====================


class UserRoleRequest(BaseModel):
    """为用户分配角色"""

    role_id: int = Field(..., gt=0, description="角色ID")


class UserRoleResponse(BaseModel):
    """用户角色响应"""

    role_id: int = Field(..., description="角色ID")
    name: str = Field(..., description="角色名")
    description: str | None = Field(None, description="角色描述")
