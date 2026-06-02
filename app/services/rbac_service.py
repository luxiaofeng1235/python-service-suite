"""
============================================
RBAC 业务逻辑层
============================================
职责：
  1. 权限校验（check_permission）
  2. 权限目录 CRUD（permissions 表）
  3. 角色 CRUD
  4. 权限分配（角色 ↔ 资源+动作，需校验权限目录）
  5. 用户-角色绑定
"""

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import AppException
from app.models.rbac import CasbinRule, Permission, Role


class RbacService:
    """RBAC 核心服务（不依赖 FastAPI，纯数据层）"""

    # ==================== 权限校验 ====================

    @staticmethod
    async def check_permission(
        db: AsyncSession,
        user_id: int,
        resource: str,
        action: str,
    ) -> bool:
        """
        检查用户是否拥有指定资源的操作权限

        Args:
            db: 数据库会话
            user_id: 用户ID
            resource: 资源名（如 "user"）
            action: 操作名（如 "delete"）

        Returns:
            True=有权限, False=无权限
        """
        # 1. 查用户的所有角色（casbin_rule g 关系）
        result = await db.execute(
            select(CasbinRule.v1).where(
                CasbinRule.ptype == "g",
                CasbinRule.v0 == str(user_id),
            )
        )
        role_names = [row[0] for row in result.all()]
        if not role_names:
            return False

        # 2. 查这些角色是否有对应的权限规则
        result = await db.execute(
            select(CasbinRule).where(
                CasbinRule.ptype == "p",
                CasbinRule.v0.in_(role_names),
                CasbinRule.v1 == resource,
                CasbinRule.v2 == action,
            ).limit(1)
        )
        return result.first() is not None

    # ==================== 权限目录管理 ====================

    @staticmethod
    async def list_permissions(db: AsyncSession) -> list[Permission]:
        """获取权限目录列表"""
        result = await db.execute(
            select(Permission).order_by(Permission.resource, Permission.action)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_permission(
        db: AsyncSession,
        resource: str,
        action: str,
        description: str | None = None,
    ) -> Permission:
        """创建权限目录条目"""
        result = await db.execute(
            select(Permission).where(
                Permission.resource == resource,
                Permission.action == action,
            ).limit(1)
        )
        if result.first():
            raise AppException(msg=f"权限 '{resource}:{action}' 已存在")

        perm = Permission(resource=resource, action=action, description=description)
        db.add(perm)
        await db.flush()
        await db.refresh(perm)
        return perm

    @staticmethod
    async def delete_permission(db: AsyncSession, permission_id: int) -> None:
        """删除权限目录条目"""
        result = await db.execute(
            select(Permission).where(Permission.id == permission_id)
        )
        perm = result.scalar_one_or_none()
        if not perm:
            raise AppException(msg="权限不存在")

        await db.delete(perm)

    @staticmethod
    async def get_permission_by_id(db: AsyncSession, permission_id: int) -> Permission:
        """获取权限目录条目"""
        result = await db.execute(
            select(Permission).where(Permission.id == permission_id)
        )
        perm = result.scalar_one_or_none()
        if not perm:
            raise AppException(msg="权限不存在")
        return perm

    # ==================== 角色管理 ====================

    @staticmethod
    async def create_role(db: AsyncSession, name: str, description: str | None = None) -> Role:
        """创建角色"""
        result = await db.execute(select(Role).where(Role.name == name))
        if result.scalar_one_or_none():
            raise AppException(msg=f"角色名 '{name}' 已存在")

        role = Role(name=name, description=description)
        db.add(role)
        await db.flush()
        await db.refresh(role)
        return role

    @staticmethod
    async def list_roles(db: AsyncSession) -> list[Role]:
        """获取所有角色列表"""
        result = await db.execute(select(Role).order_by(Role.id))
        return list(result.scalars().all())

    @staticmethod
    async def get_role_by_id(db: AsyncSession, role_id: int) -> Role:
        """获取角色详情"""
        result = await db.execute(select(Role).where(Role.id == role_id))
        role = result.scalar_one_or_none()
        if not role:
            raise AppException(msg="角色不存在")
        return role

    @staticmethod
    async def update_role(
        db: AsyncSession,
        role_id: int,
        name: str | None = None,
        description: str | None = None,
    ) -> Role:
        """更新角色信息"""
        role = await RbacService.get_role_by_id(db, role_id)

        if name is not None and name != role.name:
            result = await db.execute(select(Role).where(Role.name == name))
            if result.scalar_one_or_none():
                raise AppException(msg=f"角色名 '{name}' 已存在")
            role.name = name

        if description is not None:
            role.description = description

        await db.flush()
        await db.refresh(role)
        return role

    @staticmethod
    async def delete_role(db: AsyncSession, role_id: int) -> None:
        """删除角色（系统内置角色不可删除）"""
        role = await RbacService.get_role_by_id(db, role_id)
        if role.is_system:
            raise AppException(msg="系统内置角色不可删除")

        # 删除 casbin_rule 中所有跟该角色相关的策略
        await db.execute(
            delete(CasbinRule).where(
                (CasbinRule.v0 == role.name) | (CasbinRule.v1 == role.name)
            )
        )
        await db.delete(role)

    # ==================== 权限分配（校验权限目录） ====================

    @staticmethod
    async def get_role_permissions(db: AsyncSession, role_id: int) -> list[dict]:
        """
        获取角色的权限列表（含中文描述）

        Returns:
            [{"resource": "user", "action": "delete", "description": "删除用户"}, ...]
        """
        role = await RbacService.get_role_by_id(db, role_id)

        result = await db.execute(
            select(CasbinRule).where(
                CasbinRule.ptype == "p",
                CasbinRule.v0 == role.name,
                CasbinRule.v2 != "",
            )
        )
        rules = result.scalars().all()

        # 关联 permissions 表获取中文描述
        items = []
        for r in rules:
            desc_result = await db.execute(
                select(Permission.description).where(
                    Permission.resource == r.v1,
                    Permission.action == r.v2,
                ).limit(1)
            )
            description = desc_result.scalar_one_or_none()
            items.append({
                "resource": r.v1,
                "action": r.v2,
                "description": description or "",
            })
        return items

    @staticmethod
    async def add_role_permission(
        db: AsyncSession,
        role_id: int,
        resource: str,
        action: str,
    ) -> None:
        """
        为角色添加一条权限（校验权限目录）

        策略语义：role_name 可以对 resource 执行 action
        """
        # 校验：该权限必须在 permissions 目录中
        result = await db.execute(
            select(Permission).where(
                Permission.resource == resource,
                Permission.action == action,
            ).limit(1)
        )
        if not result.first():
            raise AppException(msg=f"权限 '{resource}:{action}' 不在权限目录中，请先添加")

        role = await RbacService.get_role_by_id(db, role_id)

        # 检查是否已存在
        result = await db.execute(
            select(CasbinRule).where(
                CasbinRule.ptype == "p",
                CasbinRule.v0 == role.name,
                CasbinRule.v1 == resource,
                CasbinRule.v2 == action,
            ).limit(1)
        )
        if result.first():
            return  # 已存在，幂等

        rule = CasbinRule(
            ptype="p",
            v0=role.name,
            v1=resource,
            v2=action,
        )
        db.add(rule)

    @staticmethod
    async def remove_role_permission(
        db: AsyncSession,
        role_id: int,
        resource: str,
        action: str,
    ) -> None:
        """移除角色的一条权限"""
        role = await RbacService.get_role_by_id(db, role_id)

        await db.execute(
            delete(CasbinRule).where(
                CasbinRule.ptype == "p",
                CasbinRule.v0 == role.name,
                CasbinRule.v1 == resource,
                CasbinRule.v2 == action,
            )
        )

    # ==================== 用户-角色绑定 ====================

    @staticmethod
    async def get_user_roles(db: AsyncSession, user_id: int) -> list[dict]:
        """
        获取用户的所有角色

        Returns:
            [{"role_id": 1, "name": "admin", "description": "管理员"}, ...]
        """
        result = await db.execute(
            select(CasbinRule.v1).where(
                CasbinRule.ptype == "g",
                CasbinRule.v0 == str(user_id),
            )
        )
        role_names = [row[0] for row in result.all()]
        if not role_names:
            return []

        result = await db.execute(
            select(Role).where(Role.name.in_(role_names))
        )
        roles = result.scalars().all()
        return [
            {"role_id": r.id, "name": r.name, "description": r.description}
            for r in roles
        ]

    @staticmethod
    async def assign_user_role(db: AsyncSession, user_id: int, role_id: int) -> None:
        """
        为用户分配角色
        在 casbin_rule 中添加一条 g 关系：user_id → role_name
        """
        role = await RbacService.get_role_by_id(db, role_id)

        result = await db.execute(
            select(CasbinRule).where(
                CasbinRule.ptype == "g",
                CasbinRule.v0 == str(user_id),
                CasbinRule.v1 == role.name,
            ).limit(1)
        )
        if result.first():
            return  # 幂等

        rule = CasbinRule(
            ptype="g",
            v0=str(user_id),
            v1=role.name,
        )
        db.add(rule)

    @staticmethod
    async def remove_user_role(db: AsyncSession, user_id: int, role_id: int) -> None:
        """移除用户的某个角色"""
        role = await RbacService.get_role_by_id(db, role_id)

        await db.execute(
            delete(CasbinRule).where(
                CasbinRule.ptype == "g",
                CasbinRule.v0 == str(user_id),
                CasbinRule.v1 == role.name,
            )
        )
