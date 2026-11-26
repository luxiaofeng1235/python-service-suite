"""
============================================
商品搜索策略 - 联合搜索与细化搜索判断
============================================
判断两次搜索是联合搜索（不同品类，追加结果）还是细化搜索（同品类，清空旧结果），
避免多品类查询时后一次搜索覆盖前一次结果。
"""

from pydantic import JsonValue


class SearchStrategy:
    """联合搜索与细化搜索的判断逻辑。"""

    @staticmethod
    def extract_search_query(result: dict[str, JsonValue] | None) -> str | None:
        """从工具结果中提取搜索查询词。"""
        if result is None:
            return None
        query = result.get("query")
        if isinstance(query, str) and query.strip():
            return query.strip()
        return None

    @staticmethod
    def is_joint_search(last_query: str, current_query: str) -> bool:
        """
        判断两次搜索是否为联合搜索（查询不同品类）vs 细化搜索（同品类缩小范围）。

        联合搜索：查询词无重叠，如"帐篷"→"睡袋"，应保留之前结果。
        细化搜索：查询词有重叠，如"耳机"→"索尼耳机"，应清空旧结果。
        """
        if last_query == current_query:
            return False
        if last_query in current_query or current_query in last_query:
            return False

        last_tokens = {last_query[i:i + 2] for i in range(len(last_query) - 1)}
        current_tokens = {current_query[i:i + 2] for i in range(len(current_query) - 1)}
        last_tokens = {t for t in last_tokens if not all(c in "，。、！？ " for c in t)}
        current_tokens = {t for t in current_tokens if not all(c in "，。、！？ " for c in t)}

        if not last_tokens or not current_tokens:
            return True

        overlap = last_tokens & current_tokens
        return len(overlap) == 0
