"""add RBAC tables (permissions, casbin_rule, roles)

Revision ID: 20260601_0001
Revises: 20260713_0001
Create Date: 2026-06-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = "20260601_0001"
down_revision: Union[str, None] = "20260713_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==================== permissions 权限目录表 ====================
    op.create_table(
        "auth_permissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="权限ID"),
        sa.Column("resource", sa.String(length=50), nullable=False, comment="资源名（如 user / role / permission）"),
        sa.Column("action", sa.String(length=50), nullable=False, comment="操作名（如 list / create / delete）"),
        sa.Column("description", sa.String(length=255), nullable=True, comment='中文说明（如 "查看用户列表"）'),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="创建时间",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("resource", "action", name="uk_resource_action"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_comment="权限目录表",
    )

    # ==================== casbin_rule 策略规则表 ====================
    op.create_table(
        "auth_casbin_rule",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("ptype", sa.String(length=10), nullable=False, comment="策略类型：p=权限, g=角色归属"),
        sa.Column("v0", sa.String(length=100), nullable=False, comment="sub（角色名 或 用户ID）"),
        sa.Column("v1", sa.String(length=100), nullable=False, comment="obj（资源 或 角色名）"),
        sa.Column("v2", sa.String(length=100), nullable=False, server_default="", comment="act（动作）"),
        sa.Column("v3", sa.String(length=100), nullable=False, server_default="", comment="预留"),
        sa.Column("v4", sa.String(length=100), nullable=False, server_default="", comment="预留"),
        sa.Column("v5", sa.String(length=100), nullable=False, server_default="", comment="预留"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ptype", "v0", "v1", "v2", "v3", "v4", "v5", name="uk_casbin_rule"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_comment="Casbin 策略规则表",
    )
    op.create_index("idx_ptype", "auth_casbin_rule", ["ptype"])
    op.create_index("idx_v0", "auth_casbin_rule", ["v0"])

    # ==================== roles 角色定义表 ====================
    op.create_table(
        "auth_roles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="角色ID"),
        sa.Column("name", sa.String(length=50), nullable=False, comment="角色名（与 casbin_rule.v0 对应）"),
        sa.Column("description", sa.String(length=255), nullable=True, comment="角色描述"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("0"), comment="系统内置角色（不可删除）"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
            comment="更新时间",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uk_name"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        mysql_comment="角色定义表",
    )

    # ==================== 默认数据 ====================

    # 1. 插入默认权限目录
    op.execute(
        "INSERT INTO auth_permissions (resource, action, description) VALUES\n"
        "('user',       'list',     '查看用户列表'),\n"
        "('user',       'read',     '查看用户详情'),\n"
        "('user',       'update',   '更新用户信息'),\n"
        "('user',       'delete',   '强制注销用户'),\n"
        "('user',       'disable',  '禁用用户'),\n"
        "('user',       'enable',   '启用用户'),\n"
        "('user',       'cleanup',  '清理过期Token'),\n"
        "('role',       'list',     '查看角色列表'),\n"
        "('role',       'read',     '查看角色详情'),\n"
        "('role',       'create',   '创建角色'),\n"
        "('role',       'update',   '更新角色'),\n"
        "('role',       'delete',   '删除角色'),\n"
        "('permission', 'list',     '查看权限目录'),\n"
        "('permission', 'create',   '创建权限条目'),\n"
        "('permission', 'delete',   '删除权限条目'),\n"
        "('permission', 'assign',   '分配/移除角色权限'),\n"
        "('user_role',  'list',     '查看用户角色'),\n"
        "('user_role',  'assign',   '分配/移除用户角色')"
    )

    # 2. 创建 admin 角色
    op.execute(
        "INSERT INTO auth_roles (name, description, is_system) "
        "VALUES ('admin', '超级管理员', 1)"
    )

    # 3. admin 角色拥有所有权限
    op.execute(
        "INSERT INTO auth_casbin_rule (ptype, v0, v1, v2) "
        "SELECT 'p', 'admin', resource, action FROM auth_permissions"
    )


def downgrade() -> None:
    op.drop_table("auth_roles")
    op.drop_index("idx_v0", table_name="auth_casbin_rule")
    op.drop_index("idx_ptype", table_name="auth_casbin_rule")
    op.drop_table("auth_casbin_rule")
    op.drop_table("auth_permissions")
