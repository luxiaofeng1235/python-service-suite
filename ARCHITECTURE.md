# FastAPI AI Service — 架构说明

> 更新日期：2026-06-02

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

## 三、部署建议

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

## 四、不变原则

| 原则 | 说明 |
|------|------|
| 路由只挂载 | `setup/routes.py` 只做 include_router，不写业务 |
| 控制器只处理请求 | 不写 SQL，不写业务判断 |
| 服务层是唯一数据源 | 所有 DB 操作经过 Service |
| 统一响应 | `Response.success()` / `Response.fail()` |
| 全局异常 | 不允许 try/catch 吞错误 |
