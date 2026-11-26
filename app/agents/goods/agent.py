"""
============================================
商品智能体定义 - 只读工具与商品咨询规则
============================================
注册商品语义检索和实时规格查询，先介绍商品知识，再查询并展示本轮平台商品。
"""

from collections.abc import Awaitable, Callable

from pydantic import JsonValue

from app.agents.goods.prompts import (
    GOODS_INTRODUCTION_PROMPT,
    GOODS_SUMMARY_PROMPT,
    GOODS_SYSTEM_PROMPT,
)
from app.agents.goods.runner import (
    PRICE_TOOL_NAME,
    PRODUCT_TOOL_NAME,
    SEARCH_TOOL_NAME,
    GoodsRunner,
)
from app.agents.llm import create_llm
from app.agents.llm.base import LLMAdapter
from app.agents.runtime import AgentTool, FunctionCallingRunner
from app.core.config import settings
from app.schemas.agent.goods import (
    GoodsPriceSearchToolRequest,
    GoodsProductToolRequest,
    GoodsSearchToolRequest,
)


def create_goods_agent(
    search_handler: Callable[..., Awaitable[JsonValue]],
    product_handler: Callable[..., Awaitable[JsonValue]],
    price_handler: Callable[..., Awaitable[JsonValue]],
    *,
    llm: LLMAdapter | None = None,
) -> GoodsRunner:
    """复用同一模型适配器，依次执行商品知识介绍、平台查询和结果总结。"""
    adapter = (
        llm
        if llm is not None
        else create_llm(model=settings.GOODS_AGENT_MODEL, enable_search=False)
    )
    introduction = FunctionCallingRunner(
        name="goods",
        system_prompt=GOODS_INTRODUCTION_PROMPT,
        llm=adapter,
        tools=(),
        max_tool_rounds=0,
    )
    decision = FunctionCallingRunner(
        name="goods",
        system_prompt=GOODS_SYSTEM_PROMPT,
        llm=adapter,
        tools=(
            AgentTool(
                SEARCH_TOOL_NAME,
                "按照商品需求语义查找在售商品；用户明确指定品牌时传品牌名称，不可省略该约束。结果包含本轮 MySQL 核验的规格、售价和库存。",
                GoodsSearchToolRequest,
                search_handler,
            ),
            AgentTool(
                PRODUCT_TOOL_NAME,
                "根据已知商品 ID 重新查询当前在售状态、规格、价格和库存；每次追问都要重新查询，不能复用历史价格库存。",
                GoodsProductToolRequest,
                product_handler,
            ),
            AgentTool(
                PRICE_TOOL_NAME,
                "按售价区间筛选在售商品，至少提供最低或最高价格之一，可叠加用户明确指定的品牌；"
                "当需要先按品类筛选再按价格过滤时，将语义搜索返回的商品 ID 传入 product_ids 参数，"
                "确保只返回同品类且符合价格区间的商品；结果包含本轮 MySQL 核验的售价和库存。",
                GoodsPriceSearchToolRequest,
                price_handler,
            ),
        ),
    )
    summary = FunctionCallingRunner(
        name="goods",
        system_prompt=GOODS_SUMMARY_PROMPT,
        llm=adapter,
        tools=(),
        max_tool_rounds=0,
    )
    # 任务规划运行器：分析复杂需求，生成分步执行计划
    planning = FunctionCallingRunner(
        name="goods_planning",
        system_prompt="你是商品查询任务规划助手。分析用户需求，分解为具体的工具调用步骤。只输出 JSON 数组，不要其他文字。",
        llm=adapter,
        tools=(),
        max_tool_rounds=0,
    )
    return GoodsRunner(
        decision,
        summary,
        introduction_runner=introduction,
        planning_runner=planning,
    )
