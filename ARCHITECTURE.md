# OmniCore Platform — 架构说明

> 更新日期：2026-11-14

---

## 一、当前运行架构

项目由一个 FastAPI 应用同时提供前台 API 和后台管理 API，共用数据库、公共服务与统一响应。

### 路由组织

```text
app/setup/routes.py
  └── register_routes(app)
       ├── app/routes/api.py    → /api/*，用户、AI、Agent、附件等前台接口
       └── app/routes/admin.py  → /admin/*，管理员认证、用户管理、RBAC、CMS
```

两个路由聚合器分别挂载控制器，共享一个应用实例和端口。业务接口的认证与权限通过依赖显式声明；路由使用 `/admin` 前缀本身不会自动产生保护。

### 认证方式

| 场景 | 依赖 | 数据来源 |
|------|------|----------|
| 前台用户 | `get_current_user` | `user_tokens` + `users` |
| 后台管理员 | `get_current_admin_user` | `admin_tokens` + `auth_admins` |
| 指定后台权限 | `require_permission(Perm.XXX)` | 后台身份 + 数据库角色策略 |
| 仅限超管 | `require_super_admin` | `auth_admins.is_super` |

登录使用数据库保存的短 Token，通过 `Authorization: Bearer <token>` 传入。鉴权检查 Token 有效性、过期时间和账号状态；前台还检查账号是否注销。前后台 Token 独立，不能相互替代。

`AUTH_WHITE_LIST` 用于已接入前台鉴权依赖的公开路径及验签豁免，不会自动替代后台鉴权。后台登录公开，其余管理接口按职责声明依赖；CMS 分类列表要求 `cms:list`。

### 启动

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 二、目录分层与模块复用

```text
app/
├── api/controllers/       # 前台路由与请求响应
├── api/services/          # 前台专用业务
├── admin/controllers/     # 后台路由与请求响应
├── admin/services/        # 后台专用业务
├── services/              # 跨模块公共业务，包括附件、AI、RBAC 和 Agent
├── agents/                # Agent 编排、工具注册及 LLM 适配
├── core/                  # 配置、身份依赖和权限依赖
├── models/                # SQLAlchemy 数据库映射
├── schemas/               # 请求验证与响应模型
├── common/                # 统一响应、异常、分页等
├── pkg/                   # 日志、Redis、模型客户端等基础设施
├── storage/               # 本地文件和 OSS 存储
├── routes/                # 前后台路由聚合
└── setup/                 # 应用组装、生命周期及中间件注册
```

控制器接收参数、注入可信身份、调用服务、返回统一响应。SQL 查询、授权范围判断和业务事务放在服务层；Model 只映射表结构，Schema 负责参数约束与响应字段。

跨前后台复用的能力放在 `app/services/`，例如附件服务和 RBAC。前后台各自的账户业务分别放在 `app/api/services/` 与 `app/admin/services/`。所有路由由 `app/setup/routes.py` 集中挂载。

---

## 三、接口级 RBAC 与授权范围

### 3.1 当前实现

当前使用 SQLAlchemy 直接查询 MySQL 策略表，未引入 PyCasbin、Casbin Adapter 或 Enforcer。`auth_casbin_rule` 保留历史命名，以 `p`、`g` 区分两种关系。

| 表 | 职责 |
|----|------|
| `auth_permissions` | 可分配权限目录，使用 `resource + action` 表示权限 |
| `auth_roles` | 角色定义 |
| `auth_casbin_rule` | `g: 管理员 ID → 角色名`，`p: 角色名 → 资源 + 动作` |

`app/core/permissions.py` 的 `Perm` 集中维护执行点使用的权限名，如 `user:list`、`cms:list`。资源名是业务资源，不是 URL；动作也不直接等同于 HTTP 方法。

### 3.2 请求校验

```text
请求 → require_permission(Perm.XXX)
          └── get_current_admin_user：校验后台 Token 和账号
                ├── is_super=True：放行
                └── 普通管理员：RbacService.check_permission
                      ├── 查询 g 关系，取得管理员的角色
                      └── 查询 p 策略，匹配资源和动作
```

缺少身份返回 HTTP 401，缺少接口权限返回 HTTP 403，由统一异常处理器输出错误。策略在请求时查询数据库，没有进程内 Enforcer 策略缓存；提交角色或权限变更后，后续请求即可读取。

### 3.3 分配权限与角色

接口权限和可授予范围分两步校验：

1. `require_permission` 校验操作者能否访问分配接口，例如 `permission:assign` 或 `user_role:assign`。
2. `RbacService` 从数据库核实操作者账号，再校验具体授权内容。普通管理员只能授予自身已持有的权限；分配整个角色时，该角色的全部权限都必须包含在操作者的现有权限中。超管可授予任意目录权限和角色。

操作者 ID 来自后台鉴权依赖，不能由请求体指定。目录中存在某权限，仅表示该权限可被管理，不代表任意拥有分配接口权限的管理员都能授予它。

### 3.4 初始化与迁移

`sql/init.sql` 为手动建库提供权限种子。Alembic 通过 `20261114_0001` 补齐历史遗漏的权限目录、默认 `admin` / `editor` 角色及基础策略，与手动初始化保持一致；不覆盖已有描述、自定义权限或管理员角色绑定。

该迁移会补回默认角色缺失的基础权限。已有数据库执行：

```bash
alembic upgrade head
```

新增执行点权限时，应同时更新 `Perm`、初始化 SQL，并为已有数据库增加数据迁移，避免只有代码认识权限、数据库目录却无法分配的情况。

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
| 认证与授权分层 | 接口准入走 `Depends`；服务层使用可信操作者 ID 校验具体授权范围 |
