"""
============================================
商品预算约束处理 - 预算提取与超支警告
============================================
从用户消息中提取预算金额，在总结阶段检查商品总价是否超支，
生成约束警告供总结模型参考。
"""

import re

from app.schemas.agent.goods_data import ProductDTO


class BudgetGuard:
    """预算约束提取与超支警告生成。"""

    @staticmethod
    def extract_budget(history: list) -> float | None:
        """
        从用户最新消息中提取预算约束。

        支持格式："5000元"、"预算5000"、"不超过3000"、"5000以内"
        """
        for message in reversed(history):
            if message.role == "user" and message.content:
                content = message.content
                patterns = [
                    r"预算[^\d]*(\d+)",
                    r"(\d+)\s*元",
                    r"不超过[^\d]*(\d+)",
                    r"(\d+)\s*以内",
                    r"(\d+)\s*以下",
                    r"(\d+)\s*左右",
                ]
                for pattern in patterns:
                    match = re.search(pattern, content)
                    if match:
                        try:
                            return float(match.group(1))
                        except (ValueError, IndexError):
                            continue
                return None
        return None

    @staticmethod
    def build_constraint_warning(products: list[ProductDTO], user_budget: float) -> str:
        """
        构建预算约束警告，供总结模型参考。

        计算每个商品最低价格总和，超支时生成警告文本。
        """
        if not products:
            return ""

        min_prices: list[tuple[str, float]] = []
        for product in products:
            if product.skus:
                lowest = min(float(sku.price) for sku in product.skus)
                min_prices.append((product.name, lowest))

        if not min_prices:
            return ""

        total = sum(price for _, price in min_prices)
        all_min = min(price for _, price in min_prices)

        warnings: list[str] = [f"【用户预算约束】用户预算为 {user_budget:.0f} 元。"]
        has_warning = False

        if total > user_budget:
            over_amount = total - user_budget
            over_percent = (over_amount / user_budget) * 100 if user_budget > 0 else 0
            warnings.append(
                f"注意：以上商品最低总价约 {total:.0f} 元，超出用户预算 {over_amount:.0f} 元 "
                f"({over_percent:.0f}%)，请在推荐中明确说明这一点，并建议用户调整预算或选择更经济的方案。"
            )
            has_warning = True
        elif all_min > user_budget:
            warnings.append(
                f"注意：部分商品最低售价超过 {user_budget:.0f} 元预算，"
                "请说明当前查询结果可能超出预算，建议用户调整需求。"
            )
            has_warning = True

        return "\n".join(warnings) if has_warning else ""
