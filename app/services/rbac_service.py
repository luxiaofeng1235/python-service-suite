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

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import AppException
from app.models.auth_admin import AuthAdmin
from app.models.auth_casbin_rule import CasbinRule
from app.models.auth_permission import Permission
from app.models.auth_role import Role


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
            select(CasbinRule.obj).where(
                CasbinRule.ptype == "g",
                CasbinRule.sub == str(user_id),
            )
        )
        role_names = [row[0] for row in result.all()]
        if not role_names:
            return False

        # 2. 查这些角色是否有对应的权限规则
        result = await db.execute(
            select(CasbinRule).where(
                CasbinRule.ptype == "p",
                CasbinRule.sub.in_(role_names),
                CasbinRule.obj == resource,
                CasbinRule.act == action,
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
        await db.commit()
        await db.refresh(perm)
        return perm

    @staticmethod
    async def delete_permission(db: AsyncSession, permission_id: int) -> None:
        """删除权限目录条目（同步回收已分配给各角色的该权限策略）"""
        result = await db.execute(
            select(Permission).where(Permission.id == permission_id)
        )
        perm = result.scalar_one_or_none()
        if not perm:
            raise AppException(msg="权限不存在")

        # 级联清理：删掉所有角色对该 resource:action 的 p 策略，
        # 否则目录里看不到该权限，角色却仍持有它（check_permission 照样放行）
        await db.execute(
            delete(CasbinRule).where(
                CasbinRule.ptype == "p",
                CasbinRule.obj == perm.resource,
                CasbinRule.act == perm.action,
            )
        )
        await db.delete(perm)
        await db.commit()

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
        await db.commit()
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

            old_name = role.name
            role.name = name

            # 角色名是 casbin_rule 的关联键，改名必须同步迁移所有引用，
            # 否则该角色的权限策略（p.sub）和用户绑定（g.obj）会全部失效，留下孤儿数据
            await db.execute(
                update(CasbinRule)
                .where(CasbinRule.ptype == "p", CasbinRule.sub == old_name)
                .values(sub=name)
            )
            await db.execute(
                update(CasbinRule)
                .where(CasbinRule.ptype == "g", CasbinRule.obj == old_name)
                .values(obj=name)
            )

        if description is not None:
            role.description = description

        await db.commit()
        await db.refresh(role)
        return role

    @staticmethod
    async def delete_role(db: AsyncSession, role_id: int) -> None:
        """删除角色（系统内置角色不可删除）"""
        role = await RbacService.get_role_by_id(db, role_id)
        if role.is_system:
            raise AppException(msg="系统内置角色不可删除")

        # 精确清理 casbin_rule：
        #   p 策略的 sub 是角色名（obj 是资源名，不能误删）
        #   g 关系的 obj 是角色名（sub 是用户ID）
        # 用 ptype 区分，避免角色名恰好与某资源名相同时误删权限策略
        await db.execute(
            delete(CasbinRule).where(
                ((CasbinRule.ptype == "p") & (CasbinRule.sub == role.name))
                | ((CasbinRule.ptype == "g") & (CasbinRule.obj == role.name))
            )
        )
        await db.delete(role)
        await db.commit()

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
                CasbinRule.sub == role.name,
                CasbinRule.act != "",
            )
        )
        rules = result.scalars().all()

        # 关联 permissions 表获取中文描述
        items = []
        for r in rules:
            desc_result = await db.execute(
                select(Permission.description).where(
                    Permission.resource == r.obj,
                    Permission.action == r.act,
                ).limit(1)
            )
            description = desc_result.scalar_one_or_none()
            items.append({
                "resource": r.obj,
                "action": r.act,
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
                CasbinRule.sub == role.name,
                CasbinRule.obj == resource,
                CasbinRule.act == action,
            ).limit(1)
        )
        if result.first():
            return  # 已存在，幂等

        rule = CasbinRule(
            ptype="p",
            sub=role.name,
            obj=resource,
            act=action,
        )
        db.add(rule)
        await db.commit()

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
                CasbinRule.sub == role.name,
                CasbinRule.obj == resource,
                CasbinRule.act == action,
            )
        )
        await db.commit()

    # ==================== 用户-角色绑定 ====================

    @staticmethod
    async def get_user_roles(db: AsyncSession, user_id: int) -> list[dict]:
        """
        获取用户的所有角色

        Returns:
            [{"role_id": 1, "name": "admin", "description": "管理员"}, ...]
        """
        result = await db.execute(
            select(CasbinRule.obj).where(
                CasbinRule.ptype == "g",
                CasbinRule.sub == str(user_id),
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
                CasbinRule.sub == str(user_id),
                CasbinRule.obj == role.name,
            ).limit(1)
        )
        if result.first():
            return  # 幂等

        rule = CasbinRule(
            ptype="g",
            sub=str(user_id),
            obj=role.name,
        )
        db.add(rule)
        await db.commit()

    @staticmethod
    async def remove_user_role(
        db: AsyncSession,
        user_id: int,
        role_id: int,
        operator_is_super: bool = False,
    ) -> None:
        """
        移除用户的某个角色

        Args:
            db: 数据库会话
            user_id: 目标管理员 ID
            role_id: 要移除的角色 ID
            operator_is_super: 操作人是否为超管

        Raises:
            AppException: 超管或 admin 账户的角色不可移除
        """
        role = await RbacService.get_role_by_id(db, role_id)

        # 非超管不能移除超管的角色
        if not operator_is_super:
            result = await db.execute(
                select(AuthAdmin).where(
                    AuthAdmin.id == user_id,
                    AuthAdmin.is_super == True,  # noqa: E712
                )
            )
            if result.scalar_one_or_none():
                raise AppException(msg="无权操作超管管理员的角色")

        # admin 账户的角色不可移除
        result = await db.execute(
            select(AuthAdmin).where(
                AuthAdmin.id == user_id,
                AuthAdmin.username == "admin",
            )
        )
        if result.scalar_one_or_none():
            raise AppException(msg="admin 账户的角色不可移除")

        await db.execute(
            delete(CasbinRule).where(
                CasbinRule.ptype == "g",
                CasbinRule.sub == str(user_id),
                CasbinRule.obj == role.name,
            )
        )
        await db.commit()
