"""
============================================
RBAC 权限常量定义
============================================
所有后台权限集中定义，避免硬编码字符串散落在各 Controller 中。
"""

from enum import StrEnum


class Perm(StrEnum):
    """权限常量枚举

    格式：``{resource}:{action}``

    用法:
        require_permission(Perm.ADMIN_LIST)
        或 require_permission(Perm.ADMIN_LIST.resource, Perm.ADMIN_LIST.action)
    """

    # ==================== 管理员 ====================
    ADMIN_LIST = "admin:list"
    """管理员：列表"""
    ADMIN_CREATE = "admin:create"
    """管理员：创建"""
    ADMIN_TOGGLE = "admin:toggle"
    """管理员：禁用/启用"""

    # ==================== CMS 文章 ====================
    CMS_CREATE = "cms:create"
    """CMS：创建文章/标签"""
    CMS_LIST = "cms:list"
    """CMS：列表"""
    CMS_READ = "cms:read"
    """CMS：详情"""
    CMS_UPDATE = "cms:update"
    """CMS：更新/发布/下架"""
    CMS_DELETE = "cms:delete"
    """CMS：删除"""

    # ==================== 权限目录 ====================
    PERMISSION_LIST = "permission:list"
    """权限：列表"""
    PERMISSION_CREATE = "permission:create"
    """权限：创建"""
    PERMISSION_DELETE = "permission:delete"
    """权限：删除"""
    PERMISSION_ASSIGN = "permission:assign"
    """权限：分配（给角色加/移权限）"""

    # ==================== 角色 ====================
    ROLE_CREATE = "role:create"
    """角色：创建"""
    ROLE_LIST = "role:list"
    """角色：列表"""
    ROLE_READ = "role:read"
    """角色：详情"""
    ROLE_UPDATE = "role:update"
    """角色：更新"""
    ROLE_DELETE = "role:delete"
    """角色：删除"""

    # ==================== 用户管理 ====================
    USER_LIST = "user:list"
    """用户：列表"""
    USER_READ = "user:read"
    """用户：详情"""
    USER_UPDATE = "user:update"
    """用户：更新"""
    USER_DELETE = "user:delete"
    """用户：强制注销"""
    USER_DISABLE = "user:disable"
    """用户：禁用"""
    USER_ENABLE = "user:enable"
    """用户：启用"""
    USER_CLEANUP = "user:cleanup"
    """用户：清理过期 Token"""

    # ==================== 管理员-角色关联 ====================
    USER_ROLE_LIST = "user_role:list"
    """管理员角色：查看"""
    USER_ROLE_ASSIGN = "user_role:assign"
    """管理员角色：分配/移除"""

    @property
    def resource(self) -> str:
        """获取资源名（冒号前部分）"""
        return self.value.split(":")[0]

    @property
    def action(self) -> str:
        """获取操作名（冒号后部分）"""
        return self.value.split(":", 1)[1]

    @classmethod
    def split(cls, perm: "Perm") -> tuple[str, str]:
        """拆分为 (resource, action) 元组"""
        return perm.resource, perm.action
