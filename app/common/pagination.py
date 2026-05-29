"""
============================================
通用分页工具模块
============================================
标准化分页查询参数和结果返回，避免每个 Service 重复手写 offset/limit/count。

控制器用法：
    @router.get("/list")
    async def list_items(
        page_params: PageParams = Depends(),
        db: AsyncSession = Depends(get_session),
    ):
        stmt = select(MyModel).where(...).order_by(MyModel.id)
        data = await paginate(db, stmt, page_params)
        return Response.success(data)

Service 用法：
    async def get_list(db, page_params: PageParams, ...) -> dict:
        stmt = select(MyModel).where(...).order_by(MyModel.id.desc())
        return await paginate(db, stmt, page_params)
"""

from typing import Any, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

# ==================== 分页参数（FastAPI 依赖注入用） ====================


class PageParams:
    """
    分页查询参数 — 可直接用于 FastAPI Depends()

    用法:
        @router.get("/list")
        async def list_items(p: PageParams = Depends()):
            ...

    Query 参数:
        - page: 页码，从 1 开始（默认 1）
        - size: 每页条数（默认 10，最大 100）
    """

    def __init__(
        self,
        page: int = Query(1, ge=1, description="页码，从 1 开始"),
        size: int = Query(10, ge=1, le=100, description="每页条数"),
    ):
        self.page = page
        self.size = size

    @property
    def offset(self) -> int:
        """SQL OFFSET 值"""
        return (self.page - 1) * self.size

    @property
    def limit(self) -> int:
        """SQL LIMIT 值"""
        return self.size

    def to_dict(self) -> dict[str, int]:
        return {"page": self.page, "size": self.size}


# ==================== 分页结果 Pydantic 模型 ====================

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    """
    通用分页结果模型

    用法:
        class MyItem(BaseModel):
            id: int
            name: str

        class MyListResponse(PageResult[MyItem]):
            pass  # 自动拥有 items: list[MyItem], total, page, size
    """

    items: list[T]
    total: int
    page: int
    size: int


# ==================== 通用分页查询函数 ====================


async def paginate(
    db: AsyncSession,
    stmt: Select,
    page_params: PageParams,
    count_stmt: Select | None = None,
) -> dict[str, Any]:
    """
    通用分页查询 — 执行 COUNT + 分页 SELECT 两条 SQL

    Args:
        db: 数据库会话
        stmt: 数据查询语句（已包含 WHERE、ORDER BY）
        page_params: 分页参数
        count_stmt: 计数查询语句（不传则自动从 stmt 推导）

    Returns:
        {"items": [ORM 实例列表], "total": int, "page": int, "size": int}

    示例:
        stmt = select(User).where(User.is_active == 1).order_by(User.id)
        data = await paginate(db, stmt, PageParams(page=1, size=20))
        # => {"items": [User(...)], "total": 100, "page": 1, "size": 20}
    """
    # 1. 计数
    if count_stmt is None:
        count_stmt = select(func.count()).select_from(
            stmt.order_by(None).subquery()
        )
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # 2. 分页取数据
    result = await db.execute(
        stmt.offset(page_params.offset).limit(page_params.limit)
    )
    items = list(result.scalars().all())

    return {
        "items": items,
        "total": total,
        "page": page_params.page,
        "size": page_params.size,
    }
