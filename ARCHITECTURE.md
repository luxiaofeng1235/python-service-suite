# FastAPI AI Service — 架构说明

> 更新日期：2026-06-01

---

## 一、当前现状

整个项目是**一个 FastAPI 应用实例**，只服务前端（SPA / 移动端）。

### 路由组织

```
routes/api.py
  └── api_router (无前缀)
       ├── user_controller  →  /api/user/*
       ├── ai_controller    →  /api/ai/*
       ├── file_controller  →  /api/file/*
       └── test_controller  →  /api/test/*

setup/routes.py
  └── register_routes(app) → app.include_router(api_router)
```

### 认证方式

- 普通接口：`Depends(get_current_user)` — JWT Token 校验
- 管理员接口：`Depends(get_current_admin)` — 校验 `is_super=True`
- 白名单路径：`AUTH_WHITE_LIST` 配置，免登录

> 当前授权只有「普通用户 / 超管」两级（`is_super` 布尔位），无细粒度权限。
> 接口级 RBAC 的引入方案见 [第三章](#三接口级-rbac基于-casbin-二开)。

### 部署

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

一个进程、一个端口。

---

## 二、加入后台管理的实际改动

### 2.1 新增 `app/admin/` 模块

```
app/admin/
├── controllers/          # 后台控制器，prefix="/admin/xxx"
├── services/             # 后台业务逻辑（可复用前台 service，也可写独立的）
├── schemas/              # 后台专属请求/响应模型（可选）
└── routes.py             # 聚合 admin_router
```

### 2.2 现有文件改动

| 文件 | 改动 |
|------|------|
| `setup/routes.py` | 增加 `app.include_router(admin_router)`，共两行 |
| `core/dependency.py` | 已有 `get_current_admin`，不动，后台直接复用 |
| `controllers/*` | **不动** — 前台接口维持现有路径不变 |
| `services/*` | **不动** — 后台若需相同逻辑，在 admin service 里调 `UserService.xxx()` 复用 |

### 2.3 当前 controller 里已有管理员接口怎么处理

现有 `user_controller.py` 里的：

| 路由 | 权限 | 归谁 |
|------|------|------|
| `/api/user/login` | 免登录 | 前台，不动 |
| `/api/user/register` | 免登录 | 前台，不动 |
| `/api/user/forgot-password` | 免登录 | 前台，不动 |
| `/api/user/reset-password` | 免登录 | 前台，不动 |
| `/api/user/logout` | 普通用户 | 前台，不动 |
| `/api/user/center` | 普通用户 | 前台，不动 |
| `/api/user/list` | 普通用户 | 前台，不动 |
| `/api/user/delete` | 普通用户 | 前台，不动 |
| `/api/user/tokens/expired` | **管理员** | **方案见下文** |

两个方案：

**方案 A（推荐）：保持现状，管理员接口留在前台不动**

- `cleanup_expired_tokens` 是系统功能接口，放在前台 `/api/user/tokens/expired` 给前端管理面板调
- 后台新增的管理功能写在自己的 controller 下，如 `/admin/users/*`
- 优点：无需迁移旧接口，不改动稳定代码
- 缺点：前台 API 文档里能看到管理员接口

**方案 B：迁移到后台**

- 将 `cleanup_expired_tokens` 从 `user_controller.py` 移到 `admin/controllers/` 下
- 前台 `user_controller.py` 移除该路由
- 优点：前后接口各归其位
- 缺点：改了现有代码，需要重新测试

### 2.4 后端最终路由总览

```
setup/routes.py
  └── register_routes(app)
       ├── app.include_router(api_router)     # /api/* 前端
       └── app.include_router(admin_router)   # /admin/* 后台
```

两个 `APIRouter` 独立，共享同一个 `FastAPI` 实例、同一个端口。

---

## 三、接口级 RBAC（基于 Casbin 二开）

### 3.1 选型结论

接口级 RBAC（角色 → 接口）选用 **Casbin** 生态，二开接入现有鉴权链路：

| 组件 | 作用 |
|------|------|
| `casbin` (PyCasbin) | 权限决策引擎，`subject-object-action` 模型 |
| `casbin-async-sqlalchemy-adapter` | 策略存入现有 MySQL，复用 async 引擎，不用 CSV |

Casbin 的 `sub(角色) - obj(URL 路径) - act(HTTP 方法)` 模型天然就是接口级 RBAC，无需自造轮子。

> **不直接用 `fastapi-authz` 中间件**。它依赖 Starlette `AuthenticationMiddleware` 注入身份，与本项目「依赖注入式」鉴权（`get_current_user` 查 `UserToken` 表）机制不一致。本项目只引入 `casbin` 内核，鉴权入口仍走依赖注入。

### 3.2 模型分层

权限决策属于「鉴权」基础设施，**不下沉到业务 Service**，与 `get_current_user` 同层：

```
core/
├── dependency.py        # 已有 get_current_user / get_current_admin
├── rbac.py              # 新增 — Casbin enforcer 单例 + require_permission 依赖工厂
└── ...
```

| 文件 | 改动 | 说明 |
|------|------|------|
| `core/rbac.py` | **新增** | 初始化 enforcer（async adapter），暴露 `require_permission()` 依赖工厂 |
| `core/dependency.py` | **不动** | RBAC 复用 `get_current_user` 拿到的 `user_id` / `is_super` 作为 subject |
| `services/rbac_service.py` | **新增** | 角色/权限/分配的 CRUD（管理后台用），是策略表的唯一数据源 |
| `controllers/*` | 仅在需要鉴权的路由加 `dependencies=[Depends(require_permission(...))]` | 不动既有业务逻辑 |

### 3.3 与现有鉴权的衔接（二开胶水点）

1. **subject 来源**：`require_permission` 内部 `Depends(get_current_user)`，用返回的角色/`user_id` 作为 Casbin 的 `sub`，不引入 Casbin 自带认证。
2. **超管直通**：`is_super=True` 跳过 Casbin 校验，与现有 `get_current_admin` 语义一致。
3. **白名单不变**：`AUTH_WHITE_LIST` 仍在 `get_current_user` 层生效，RBAC 只管「已登录用户能否访问该接口」。
4. **失败响应统一**：鉴权不通过抛 `AppException`（或 403 `HTTPException`），由现有全局异常处理器转成统一 `Response.fail` 格式，不暴露 Casbin 默认 403。

### 3.4 用法示例

```python
from app.core.rbac import require_permission

@router.delete(
    "/api/user/delete",
    dependencies=[Depends(require_permission("user", "delete"))],
)
async def delete_user(...):
    ...
```

策略与角色分配通过 `RbacService` 落库，运行时可动态变更、无需重启。

### 3.5 待确认 / 实现时再定

- 角色与权限表结构（`roles` / `role_permissions` / `user_roles`，或直接用 Casbin 的 `casbin_rule` 表 + 一张角色表）
- `obj` 用 URL 路径还是抽象资源名（`user`/`order`）—— 影响策略可读性
- 策略缓存与热更新策略（多进程部署下 enforcer 一致性）

---

## 四、部署建议

### 默认：一个服务

```
Nginx (可选)
  └─→ FastAPI (1 进程, port 8000)
       ├── /api/*      → 前端 API
       └── /admin/*    → 后台 API
```

### 什么情况下拆两个服务

| 场景 | 做法 |
|------|------|
| 后台内网、前端外网 | 拆分，不同网卡暴露 |
| 两套负载策略不同 | 拆分为两个 `uvicorn` 进程 |
| 运维规范强制要求 | 拆 |
| 以上都没有 | **不拆** |

---

## 五、不变原则

| 原则 | 说明 |
|------|------|
| 路由只挂载 | `setup/routes.py` 只做 include_router，不写业务 |
| 控制器只处理请求 | 不写 SQL，不写业务判断 |
| 服务层是唯一数据源 | 所有 DB 操作经过 Service |
| 统一响应 | `Response.success()` / `Response.fail()` |
| 全局异常 | 不允许 try/catch 吞错误 |
| 鉴权在依赖层 | 认证/权限校验走 `Depends`，不渗进业务 Service；Service 只信任已注入的 `user_id` |
