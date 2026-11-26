"""
============================================
商品 Agent 流水线阶段模块
============================================
将 runner 的各阶段职责拆分为独立模块：规划、预算、搜索策略、事实格式化。
runner 只负责串联流程，各阶段可独立测试和修改。
"""

from app.agents.goods.pipeline.budget import BudgetGuard
from app.agents.goods.pipeline.facts import FactsFormatter
from app.agents.goods.pipeline.planner import TaskPlanner
from app.agents.goods.pipeline.search_strategy import SearchStrategy

__all__ = ["BudgetGuard", "FactsFormatter", "TaskPlanner", "SearchStrategy"]
