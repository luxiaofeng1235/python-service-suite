"""
============================================
权限与响应回归测试 - 授权边界及初始化数据
============================================
使用内存数据库验证后台真实鉴权依赖、权限分配范围、失败响应和权限种子迁移。
不连接项目数据库、Redis 或外部模型服务。
"""

import importlib.util
import json
import re
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.admin.controllers.cms_article_controller import router as cms_router
from app.admin.controllers.rbac_controller import router as rbac_router
from app.common.exception import AppException
from app.common.response import Response
from app.core.permissions import Perm
from app.database import get_session
from app.models.admin_token import AdminToken
from app.models.auth_admin import AuthAdmin
from app.models.auth_casbin_rule import CasbinRule
from app.models.auth_permission import Permission
from app.models.auth_role import Role
from app.services.rbac_service import RbacService
from app.setup.exception import register_exception_handlers
from app.utils.time_ import TimeUtil

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ResponsePayload(BaseModel):
    """覆盖 Pydantic 模型中的日期和金额字段。"""

    created_at: datetime
    amount: Decimal


@pytest.fixture
async def api() -> AsyncIterator[tuple[AsyncSession, httpx.AsyncClient]]:
    """准备独立管理员、短 Token、角色及内存 API。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for model in (AuthAdmin, AdminToken, Role, Permission, CasbinRule):
            await connection.run_sync(model.__table__.create)

    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            for admin_id, name, is_super in (
                (1, "super", True), (2, "operator", False),
                (3, "viewer", False), (4, "recipient", False),
            ):
                db.add(AuthAdmin(
                    id=admin_id, username=name, password_hash="测试占位值", is_super=is_super,
                ))
                db.add(AdminToken(
                    admin_id=admin_id, token=f"test-{name}",
                    expires_at=TimeUtil.get_date() + timedelta(hours=1),
                ))
            for role_id, name in ((1, "operator"), (2, "viewer"), (3, "privileged"), (4, "empty")):
                db.add(Role(id=role_id, name=name, is_system=False))
            for resource, action in (
                ("permission", "assign"), ("user_role", "assign"),
                ("user", "list"), ("user", "delete"), ("cms", "list"),
            ):
                db.add(Permission(resource=resource, action=action))
            for role, resource, action in (
                ("operator", "permission", "assign"), ("operator", "user_role", "assign"),
                ("operator", "user", "list"), ("viewer", "user", "list"),
                ("privileged", "user", "delete"),
            ):
                db.add(CasbinRule(ptype="p", sub=role, obj=resource, act=action))
            for admin_id, role in ((2, "operator"), (3, "viewer")):
                db.add(CasbinRule(ptype="g", sub=str(admin_id), obj=role, act=""))
            await db.commit()

            async def override_session() -> AsyncIterator[AsyncSession]:
                """让鉴权依赖与控制器使用同一个测试会话。"""
                try:
                    yield db
                finally:
                    await db.rollback()

            app = FastAPI()
            app.include_router(cms_router)
            app.include_router(rbac_router)
            register_exception_handlers(app)
            app.dependency_overrides[get_session] = override_session
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test.local",
            ) as client:
                yield db, client
    finally:
        await engine.dispose()


@pytest.mark.parametrize("role_id", [1, 4])
async def test_cannot_grant_unowned_permission(api, role_id: int) -> None:
    """不能向自己或其他角色授予未持有权限，请求体也不能伪造操作者。"""
    db, client = api
    response = await client.post(
        f"/admin/roles/{role_id}/permissions",
        headers={"Authorization": "Bearer test-operator"},
        json={"resource": "user", "action": "delete", "operator_id": 1, "is_super": True},
    )
    assert response.json()["code"] == 403
    assert "自身未持有" in response.json()["msg"]
    assert not await RbacService.check_permission(db, 2, "user", "delete")
    assert await db.scalar(sa.select(sa.func.count()).select_from(CasbinRule).where(
        CasbinRule.ptype == "p", CasbinRule.sub.in_(("operator", "empty")),
        CasbinRule.obj == "user", CasbinRule.act == "delete",
    )) == 0


@pytest.mark.parametrize("actor,action", [("operator", "list"), ("super", "delete")])
async def test_allowed_permission_assignment_is_idempotent(api, actor: str, action: str) -> None:
    """普通管理员可分配已有权限，超管可分配任意目录权限，重复调用不重复写入。"""
    db, client = api
    for _ in range(2):
        response = await client.post(
            "/admin/roles/4/permissions", headers={"Authorization": f"Bearer test-{actor}"},
            json={"resource": "user", "action": action},
        )
        assert response.json()["code"] == 1
    assert await db.scalar(sa.select(sa.func.count()).select_from(CasbinRule).where(
        CasbinRule.ptype == "p", CasbinRule.sub == "empty",
        CasbinRule.obj == "user", CasbinRule.act == action,
    )) == 1


@pytest.mark.parametrize("recipient", [2, 4])
async def test_cannot_bypass_grant_scope_by_assigning_role(api, recipient: int) -> None:
    """角色分配不能绕过单条权限的授权边界。"""
    db, client = api
    response = await client.post(
        f"/admin/admins/{recipient}/roles", headers={"Authorization": "Bearer test-operator"},
        json={"role_id": 3},
    )
    assert response.json()["code"] == 403
    assert not await RbacService.check_permission(db, recipient, "user", "delete")


@pytest.mark.parametrize("actor,role_id,action", [("operator", 2, "list"), ("super", 3, "delete")])
async def test_allowed_role_assignment_is_idempotent(api, actor: str, role_id: int, action: str) -> None:
    """可分配授权范围内的角色，超管无需持有对应的角色策略。"""
    db, client = api
    for _ in range(2):
        response = await client.post(
            "/admin/admins/4/roles", headers={"Authorization": f"Bearer test-{actor}"},
            json={"role_id": role_id},
        )
        assert response.json()["code"] == 1
    assert await RbacService.check_permission(db, 4, "user", action)
    assert await db.scalar(sa.select(sa.func.count()).select_from(CasbinRule).where(
        CasbinRule.ptype == "g", CasbinRule.sub == "4",
    )) == 1


async def test_grant_checks_directory_and_active_operator(api) -> None:
    """超管仍受权限目录和账号状态约束。"""
    db, client = api
    response = await client.post(
        "/admin/roles/4/permissions", headers={"Authorization": "Bearer test-super"},
        json={"resource": "missing", "action": "delete"},
    )
    assert response.json()["code"] == 0
    assert "不在权限目录" in response.json()["msg"]
    operator = await db.get(AuthAdmin, 1)
    operator.is_active = False
    await db.commit()
    with pytest.raises(AppException, match="已禁用"):
        await RbacService.add_role_permission(db, 4, "user", "delete", operator_id=1)


async def test_missing_endpoint_permission_is_forbidden(api) -> None:
    """普通登录身份不能替代接口要求的权限。"""
    _, client = api
    response = await client.post(
        "/admin/roles/4/permissions", headers={"Authorization": "Bearer test-viewer"},
        json={"resource": "user", "action": "list"},
    )
    assert response.status_code == 403


async def test_categories_require_admin_auth_and_cms_permission(api) -> None:
    """分类列表拒绝匿名及缺少 CMS 权限者，允许超管和有权限的管理员。"""
    db, client = api
    assert (await client.get("/admin/cms/categories")).status_code == 401
    assert (await client.get(
        "/admin/cms/categories", headers={"Authorization": "Bearer test-operator"},
    )).status_code == 403
    assert (await client.get(
        "/admin/cms/categories", headers={"Authorization": "Bearer test-super"},
    )).status_code == 200
    db.add(CasbinRule(ptype="p", sub="operator", obj="cms", act="list"))
    await db.commit()
    response = await client.get(
        "/admin/cms/categories", headers={"Authorization": "Bearer test-operator"},
    )
    assert response.status_code == 200
    assert response.json()["code"] == 1


@pytest.mark.parametrize("response_method", [Response.success, Response.fail])
def test_response_serializes_nested_values(response_method) -> None:
    """成功与失败响应均支持嵌套模型、日期、金额、ORM 和元组。"""
    now = datetime(2026, 11, 14, 12, 30)
    value = {
        "time": now, "date": date(2026, 11, 14), "price": Decimal("12.50"),
        "nested": (ResponsePayload(created_at=now, amount=Decimal("2.50")),),
        "orm": Role(id=1, name="测试角色", is_system=False, created_at=now, updated_at=now),
    }
    response = response_method(data=value)
    data = json.loads(response.body)["data"]
    assert data["time"] == "2026-11-14 12:30:00"
    assert data["date"] == "2026-11-14"
    assert data["price"] == 12.5
    assert data["nested"][0]["created_at"] == "2026-11-14T12:30:00"
    assert data["orm"]["created_at"] == "2026-11-14 12:30:00"


async def test_app_exception_data_does_not_become_500() -> None:
    """完整异常处理链应保留业务错误码并正确序列化附加数据。"""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/failure")
    async def failure() -> None:
        """模拟携带日期与金额的业务异常。"""
        raise AppException(msg="测试业务错误", code=1001, data={"price": Decimal("1.50")})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test.local",
    ) as client:
        response = await client.get("/failure")
    assert response.status_code == 200
    assert response.json() == {"code": 1001, "msg": "测试业务错误", "data": {"price": 1.5}}


@pytest.mark.parametrize("unique_constraints", [False, True])
def test_seed_migration_is_complete_and_idempotent(unique_constraints: bool) -> None:
    """兼容手动 SQL 与 Alembic 的约束差异，保留原记录并避免重复添加。"""
    path = PROJECT_ROOT / "migrations/versions/20261114_0001_complete_rbac_seeds.py"
    spec = importlib.util.spec_from_file_location("rbac_seed_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    permission_pairs = {(resource, action) for resource, action, _ in migration.PERMISSIONS}
    assert permission_pairs == {(perm.resource, perm.action) for perm in Perm}

    sql = (PROJECT_ROOT / "sql/init.sql").read_text()
    seed = sql.split('INSERT INTO `auth_permissions`', 1)[1].split('ON DUPLICATE KEY', 1)[0]
    assert set(re.findall(r"\('([^']+)'\s*,\s*'([^']+)'", seed)) == permission_pairs
    admin_grants = re.findall(r"\('p',\s*'admin',\s*'([^']+)',\s*'([^']+)'", sql)
    assert set(admin_grants) == permission_pairs

    engine = sa.create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE auth_permissions (resource TEXT, action TEXT, description TEXT"
                + (", UNIQUE(resource, action))" if unique_constraints else ")")
            )
            connection.exec_driver_sql(
                "CREATE TABLE auth_roles (name TEXT UNIQUE, description TEXT, is_system INTEGER)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE auth_casbin_rule (ptype TEXT, sub TEXT, obj TEXT, act TEXT"
                + (", UNIQUE(ptype, sub, obj, act))" if unique_constraints else ")")
            )
            connection.exec_driver_sql(
                "INSERT INTO auth_permissions VALUES ('user', 'list', '保留原描述')"
            )
            connection.exec_driver_sql(
                "INSERT INTO auth_casbin_rule VALUES ('g', '42', 'custom', '')"
            )
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                migration.upgrade()
            assert connection.execute(sa.text(
                "SELECT COUNT(*) FROM auth_permissions"
            )).scalar_one() == len(Perm)
            assert connection.execute(sa.text(
                "SELECT description FROM auth_permissions WHERE resource='user' AND action='list'"
            )).scalar_one() == "保留原描述"
            assert connection.execute(sa.text(
                "SELECT COUNT(*) FROM auth_roles"
            )).scalar_one() == 2
            assert connection.execute(sa.text(
                "SELECT COUNT(*) FROM auth_casbin_rule"
            )).scalar_one() == len(Perm) + 3
    finally:
        engine.dispose()
