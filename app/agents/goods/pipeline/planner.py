"""
============================================
商品任务规划器 - 复杂需求分步计划生成
============================================
判断是否需要启用任务规划，调用 LLM 生成分步执行计划，
解析并校验计划结构。规划失败时返回 None 由调用方降级。
"""

import json

from app.agents.llm.base import LLMMessage
from app.agents.runtime import FunctionCallingRunner
from app.pkg.logging import app_logger

SEARCH_TOOL_NAME = "tool_semantic_product_search"
PRODUCT_TOOL_NAME = "tool_check_sku_stock_and_price"
PRICE_TOOL_NAME = "tool_search_products_by_price"
GOODS_TOOL_NAMES = frozenset({SEARCH_TOOL_NAME, PRODUCT_TOOL_NAME, PRICE_TOOL_NAME})

MAX_PLAN_STEPS = 5


class TaskPlanner:
    """分析复杂需求并生成分步工具调用计划。"""

    def __init__(self, planning_runner: FunctionCallingRunner | None = None):
        self.planning_runner = planning_runner

    @staticmethod
    def should_use_planning(user_message: str) -> bool:
        """
        判断是否需要启用任务规划。

        使用多维度评估：组合意图关键词、多品类连接词数量、消息复杂度。
        """
        combo_patterns = [
            "配一台", "配一套", "组合", "搭配", "一套",
            "分别买", "每个都", "各种", "多个",
            "比较", "对比", "哪个好", "哪个合适",
        ]
        if any(pattern in user_message for pattern in combo_patterns):
            app_logger.info("检测到组合意图，启用任务规划: {}", user_message[:50])
            return True

        connector_count = (
            user_message.count("和")
            + user_message.count("以及")
            + user_message.count("还有")
            + user_message.count("另外")
        )
        if connector_count >= 2:
            app_logger.info("检测到多品类连接词({}个)，启用任务规划: {}", connector_count, user_message[:50])
            return True

        if len(user_message) > 30 and user_message.count("的") >= 2:
            app_logger.info("检测到长消息多修饰，启用任务规划: {}", user_message[:50])
            return True

        return False

    async def generate_plan(self, history: list[LLMMessage]) -> list[dict] | None:
        """调用 LLM 生成执行计划，失败返回 None。"""
        if self.planning_runner is None:
            app_logger.warning("未配置规划运行器，跳过任务规划")
            return None

        plan_prompt_content = """请分析用户需求，分解为具体的工具调用步骤。

可用工具：
1. tool_semantic_product_search - 语义搜索商品，参数: query(搜索词), brand(品牌名,可选), limit(数量,可选)
2. tool_search_products_by_price - 按价格筛选，参数: min_price(最低价), max_price(最高价), brand(品牌), product_ids(限定商品ID列表)
3. tool_check_sku_stock_and_price - 查询商品详情，参数: product_ids(商品ID列表)

输出要求：
- 输出 JSON 数组，每个元素包含: {"tool": "工具名", "args": {参数}, "reason": "原因"}
- 最多 """ + str(MAX_PLAN_STEPS) + """ 个步骤
- 如果需求简单（单一品类查询），直接输出空数组 []
- 只输出 JSON，不要其他文字

预算约束说明：
- 用户提到"预算XX元"时，只按品类做语义搜索，不加价格筛选步骤。后端自动处理预算超支提醒。

示例：
用户需求: "帮我配一台5000元的游戏电脑"
输出: [
  {"tool": "tool_semantic_product_search", "args": {"query": "游戏CPU"}, "reason": "搜索CPU"},
  {"tool": "tool_semantic_product_search", "args": {"query": "游戏显卡"}, "reason": "搜索显卡"},
  {"tool": "tool_semantic_product_search", "args": {"query": "内存条"}, "reason": "搜索内存"}
]
"""

        try:
            llm_adapter = getattr(self.planning_runner, "llm", None)
            if llm_adapter is None:
                app_logger.warning("无法获取 LLM 适配器，跳过任务规划")
                return None

            app_logger.info("开始调用 LLM 生成规划...")
            plan_messages = [
                LLMMessage(role=msg.role, content=msg.content or "") for msg in history
            ]
            plan_messages.append(LLMMessage(role="user", content=plan_prompt_content))

            plan_text = ""
            async for chunk in llm_adapter.stream(plan_messages, []):
                if chunk.content:
                    plan_text += chunk.content

            raw_plan = plan_text.strip()
            app_logger.info("规划原始输出长度: {}, 内容: {}", len(raw_plan), raw_plan[:500] if raw_plan else "(空)")

            if not raw_plan:
                app_logger.warning("规划输出为空，降级为直接决策")
                return None

            result = self.parse_plan(raw_plan)
            app_logger.info("规划解析结果: {}", "成功" if result else "失败")
            return result

        except KeyError as exc:
            app_logger.warning("任务规划 KeyError: {} - 降级为直接决策", exc)
            return None
        except Exception as exc:
            app_logger.warning("任务规划失败: {} - {} - 降级为直接决策", type(exc).__name__, exc)
            return None

    @staticmethod
    def parse_plan(raw_plan: str) -> list[dict] | None:
        """解析 LLM 输出的执行计划，格式无效返回 None。"""
        if not raw_plan or raw_plan == "[]":
            return None

        json_start = raw_plan.find("[")
        json_end = raw_plan.rfind("]") + 1
        if json_start == -1 or json_end == 0:
            app_logger.warning("规划输出无有效 JSON: {}", raw_plan[:100])
            return None

        try:
            plan = json.loads(raw_plan[json_start:json_end])
        except json.JSONDecodeError as exc:
            app_logger.warning("规划 JSON 解析失败: {}", exc)
            return None

        if not isinstance(plan, list):
            return None
        if len(plan) > MAX_PLAN_STEPS:
            app_logger.warning("规划步骤过多({}>)，截断为{}", len(plan), MAX_PLAN_STEPS)
            plan = plan[:MAX_PLAN_STEPS]

        valid_steps = []
        for step in plan:
            if not isinstance(step, dict):
                continue
            tool = step.get("tool")
            args = step.get("args") or {}
            reason = step.get("reason") or ""
            if tool not in GOODS_TOOL_NAMES:
                app_logger.warning("规划包含无效工具: {}", tool)
                continue
            if not isinstance(args, dict):
                continue
            valid_steps.append({"tool": tool, "args": args, "reason": reason})

        if not valid_steps:
            return None

        app_logger.info("任务规划成功，共{}步: {}", len(valid_steps), [s["tool"] for s in valid_steps])
        return valid_steps
