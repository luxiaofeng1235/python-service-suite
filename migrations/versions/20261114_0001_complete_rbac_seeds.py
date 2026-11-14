"""
============================================
RBAC 初始化数据补齐 - 权限目录与默认角色策略
============================================
补齐历史建库遗漏的权限和默认角色，仅添加缺失记录，保留已有描述和自定义策略。
本迁移固定保存当前权限清单，不依赖应用后续版本中的枚举或配置。
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261114_0001"
down_revision: str | None = "20261112_0001"
branch_labels: str | None = None
depends_on: str | None = None


PERMISSIONS: tuple[tuple[str, str, str], ...] = (
    ("user", "list", "查看用户列表"),
    ("user", "read", "查看用户详情"),
    ("user", "update", "更新用户信息"),
    ("user", "delete", "强制注销用户"),
    ("user", "disable", "禁用用户"),
    ("user", "enable", "启用用户"),
    ("user", "cleanup", "清理过期Token"),
    ("role", "list", "查看角色列表"),
    ("role", "read", "查看角色详情"),
    ("role", "create", "创建角色"),
    ("role", "update", "更新角色"),
    ("role", "delete", "删除角色"),
    ("permission", "list", "查看权限目录"),
    ("permission", "create", "创建权限条目"),
    ("permission", "delete", "删除权限条目"),
    ("permission", "assign", "分配/移除角色权限"),
    ("user_role", "list", "查看用户角色"),
    ("user_role", "assign", "分配/移除用户角色"),
    ("admin", "create", "创建管理员"),
    ("admin", "list", "查看管理员列表"),
    ("admin", "toggle", "禁用/启用管理员"),
    ("cms", "create", "创建文章/标签"),
    ("cms", "list", "查看文章/分类/标签列表"),
    ("cms", "read", "查看文章详情"),
    ("cms", "update", "更新文章/标签及发布状态"),
    ("cms", "delete", "删除文章/标签"),
)


def upgrade() -> None:
    """补齐权限目录、默认角色及策略，兼容两种历史建库路径。"""
    for resource, action, description in PERMISSIONS:
        op.execute(
            sa.text(
                "INSERT INTO auth_permissions (resource, action, description) "
                "SELECT :resource, :action, :description "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM auth_permissions WHERE resource = :resource AND action = :action)"
            ).bindparams(resource=resource, action=action, description=description)
        )

    for name, description, is_system in (
        ("admin", "超级管理员（拥有全部权限）", 1),
        ("editor", "内容编辑员", 0),
    ):
        op.execute(
            sa.text(
                "INSERT INTO auth_roles (name, description, is_system) "
                "SELECT :name, :description, :is_system "
                "WHERE NOT EXISTS (SELECT 1 FROM auth_roles WHERE name = :name)"
            ).bindparams(name=name, description=description, is_system=is_system)
        )

    grants = [("admin", resource, action) for resource, action, _ in PERMISSIONS]
    grants.extend((("editor", "user", "list"), ("editor", "user", "read")))
    for role, resource, action in grants:
        op.execute(
            sa.text(
                "INSERT INTO auth_casbin_rule (ptype, sub, obj, act) "
                "SELECT 'p', :role, :resource, :action "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM auth_casbin_rule "
                "WHERE ptype = 'p' AND sub = :role AND obj = :resource AND act = :action)"
            ).bindparams(role=role, resource=resource, action=action)
        )


def downgrade() -> None:
    """保留权限数据，避免误删迁移前已有或后来被使用的授权。"""
    raise RuntimeError("权限补齐迁移无法自动区分原有授权，回退请使用数据库备份")
