"""
============================================
抽奖核心引擎 — 纯函数，无状态
============================================
"""
import random
from typing import Any, Callable, Optional

from app.utils.time_ import TimeUtil


# ==================== 权重归一化（最大余额法） ====================


# ==================== 权重归一化（最大余额法） ====================

def normalize_weights(items: list[dict]) -> list[dict]:
    """
    最大余额法将权重归一化到 100，避免浮点误差集中。
    输入: [{"v": 50}, {"v": 30}, {"v": 20}]
    输出权重总和 = 100
    """
    total = sum(item.get("v", 0) for item in items)
    if total <= 0:
        return items

    exact_vals = []
    floor_sum = 0
    for item in items:
        exact = (item["v"] / total) * 100
        floor_val = int(exact)
        remainder = exact - floor_val
        exact_vals.append((floor_val, remainder, item))
        floor_sum += floor_val

    remainder_to_distribute = 100 - floor_sum
    if remainder_to_distribute > 0:
        sorted_by_remainder = sorted(exact_vals, key=lambda x: x[1], reverse=True)
        for i in range(min(remainder_to_distribute, len(sorted_by_remainder))):
            idx = items.index(sorted_by_remainder[i][2])
            exact_vals[idx] = (exact_vals[idx][0] + 1, exact_vals[idx][1], exact_vals[idx][2])

    result = []
    for i, item in enumerate(items):
        normalized_item = dict(item)
        normalized_item["v"] = exact_vals[i][0]
        result.append(normalized_item)

    return result


# ==================== 按权重选取 ====================

def pick_by_weight(items: list[dict]) -> Optional[dict]:
    """
    原始权重抽选，直接 random(1, total) 递减。
    返回选中项的深拷贝，不修改原数据。
    """
    if not items:
        return None
    total = sum(item.get("v", 0) for item in items)
    if total <= 0:
        return random.choice(items) if items else None
    rand = random.randint(1, total)
    for item in items:
        rand -= item["v"]
        if rand <= 0:
            return dict(item)
    return dict(items[-1]) if items else None


def pick_index_by_weight(items: list[dict]) -> int:
    """按权重返回选中项的索引"""
    if not items:
        return -1
    total = sum(item.get("v", 0) for item in items)
    if total <= 0:
        return random.randint(0, len(items) - 1)
    rand = random.randint(1, total)
    for i, item in enumerate(items):
        rand -= item["v"]
        if rand <= 0:
            return i
    return len(items) - 1


# ==================== 金额区间随机 ====================

def random_amount(min_val: float, max_val: float) -> float:
    """浮点金额，保留 2 位小数"""
    if min_val > max_val:
        min_val, max_val = max_val, min_val
    min_int = round(min_val * 100)
    max_int = round(max_val * 100)
    return random.randint(min_int, max_int) / 100


# ==================== 二级嵌套抽奖 ====================

def raffle_nested(items: list[dict]) -> Optional[dict]:
    """
    二级嵌套抽奖:
    1. normalize_weights → 归一化到 100
    2. pick_by_weight → 按权重取一项
    3. 检查结果:
       - money 是嵌套数组 → 递归 raffle_nested
       - money 是 [min, max] → 随机金额
       - 否则 → 返回固定值
    """
    if not items:
        return None
    normalized = normalize_weights(items)
    picked = pick_by_weight(normalized)
    if not picked:
        return None

    result = dict(picked)
    money = result.get("money")
    if isinstance(money, list) and money and isinstance(money[0], dict):
        # 二级嵌套：递归抽选
        sub_result = raffle_nested(money)
        if sub_result:
            result.update(sub_result)
    elif isinstance(money, list) and len(money) == 2 and isinstance(money[0], (int, float)):
        # 金额区间 [min, max]
        result["amount"] = random_amount(float(money[0]), float(money[1]))
    elif isinstance(money, (int, float)):
        result["amount"] = float(money)

    # 处理 items 子项（多个奖品随机选一个）
    if picked.get("items") and isinstance(picked["items"], list) and picked["items"]:
        result["props"] = random.choice(picked["items"])

    return result


# ==================== 奖池过滤 ====================

def filter_pool_items(
    items: list[dict],
    exclude_types: Optional[list[str]] = None,
    exclude_props: Optional[list] = None,
    exclude_cash: bool = False,
    custom_filter: Optional[Callable[[dict], bool]] = None,
) -> list[dict]:
    """
    多维度过滤奖池项。
    返回过滤后的新列表。
    """
    result = list(items)

    if exclude_types:
        result = [item for item in result if item.get("type") not in exclude_types]

    if exclude_props:
        result = [
            item for item in result
            if item.get("props") is None or item["props"] not in exclude_props
        ]

    if exclude_cash:
        result = [item for item in result if item.get("type") != "cash"]

    if custom_filter:
        result = [item for item in result if custom_filter(item)]

    return result


# ==================== 权重修改器 ====================

def apply_weight_modifier(
    items: list[dict],
    cash_factor: float = 1.0,
    type_factor_map: Optional[dict[str, float]] = None,
    custom_modifier: Optional[Callable[[dict], int]] = None,
) -> list[dict]:
    """
    动态调整权重，返回新列表。
    cash_factor: 现金权重倍率
    type_factor_map: {"cash": 2.0, "prop": 0.5} 类型倍率
    custom_modifier: 自定义修改函数
    """
    result = []
    for item in items:
        new_item = dict(item)
        v = item.get("v", 1)

        if custom_modifier:
            v = custom_modifier(new_item)
        else:
            # 现金权重翻倍
            if item.get("type") == "cash" and cash_factor != 1.0:
                v = round(v * cash_factor)
            # 类型倍率
            if type_factor_map and item.get("type") in type_factor_map:
                v = round(v * type_factor_map[item["type"]])

        new_item["v"] = max(1, v)
        result.append(new_item)

    return result


# ==================== Tiered 模式 ====================

def draw_tiered(config: dict, options: Optional[dict] = None) -> Optional[dict]:
    """
    Tiered（层级抽奖）：
    - 根据 level 选对应的等级奖池
    - 有 odds 走嵌套抽奖 raffle_nested
    - 无 odds 走简单奖励列表 pick_by_weight
    """
    opts = options or {}
    level = opts.get("level", 1)

    level_rewards = config.get("level_rewards", {})
    reward_config = level_rewards.get(level)
    if not reward_config:
        return None

    # 1. 选择奖池方式
    odds = reward_config.get("odds")
    rewards = reward_config.get("rewards")

    if odds:
        # 嵌套抽奖
        items = list(odds)

        # 过滤 cash
        if opts.get("exclude_cash"):
            items = [item for item in items if item.get("type") != "cash"]

        if not items:
            return {"type": "none", "amount": 0, "props": None, "desc": "奖池为空"}

        result = raffle_nested(items)
    elif rewards:
        # 简单权重抽奖
        items = list(rewards)

        if opts.get("exclude_cash"):
            items = [item for item in items if item.get("type") != "cash"]

        # 权重修改器
        cash_factor = opts.get("cash_weight_factor", 1.0)
        if cash_factor != 1.0:
            items = apply_weight_modifier(items, cash_factor=cash_factor)

        if not items:
            return {"type": "none", "amount": 0, "props": None, "desc": "奖池为空"}

        picked_items = [{"v": item.get("weight", 1), **item} for item in items]
        picked = pick_by_weight(picked_items)
        if not picked:
            return {"type": "none", "amount": 0, "props": None, "desc": "抽取失败"}

        result = picked
        # 处理现金金额
        min_c = reward_config.get("min_cash", picked.get("min_cash"))
        max_c = reward_config.get("max_cash", picked.get("max_cash"))
        if picked.get("type") == "cash" and min_c is not None and max_c is not None:
            result["amount"] = random_amount(min_c, max_c)
        elif "money" not in picked:
            result["amount"] = 0
    else:
        return {"type": "none", "amount": 0, "props": None, "desc": "配置结构无法识别"}

    return {
        "type": result.get("type", ""),
        "amount": result.get("amount", 0),
        "props": result.get("props"),
        "desc": result.get("desc", ""),
    }


# ==================== Pool 模式 ====================

def draw_pool(config: dict, options: Optional[dict] = None) -> Optional[dict]:
    """
    Pool（单层奖池抽奖）：
    - 根据 pool_key 选择奖池
    - 可选择嵌套或简单权重
    """
    opts = options or {}
    pool_key = opts.get("pool_key", "reward_pool")

    items = config.get(pool_key) or config.get("pool") or config.get("reward_pool")
    if not items:
        return None

    items = list(items)

    # 过滤
    items = filter_pool_items(
        items,
        exclude_types=opts.get("exclude_types"),
        exclude_cash=opts.get("exclude_cash", False),
    )

    if not items:
        return {"type": "none", "amount": 0, "props": None, "desc": "过滤后奖池为空"}

    # 权重修改器
    cash_factor = opts.get("cash_weight_factor", 1.0)
    if cash_factor != 1.0:
        items = apply_weight_modifier(items, cash_factor=cash_factor)

    # 执行抽奖
    int_amount_types = opts.get("int_amount_types") or ["yl", "yq"]

    # 检查是否有嵌套结构
    has_nested = any(
        isinstance(item.get("money"), list)
        and len(item["money"]) > 0
        and isinstance(item["money"][0], dict)
        for item in items
    )

    if has_nested:
        result = raffle_nested(items)
    else:
        picked = pick_by_weight(items)
        if not picked:
            return {"type": "none", "amount": 0, "props": None, "desc": "抽取失败"}
        result = picked

        # 处理金额
        money = picked.get("money")
        if isinstance(money, list) and len(money) == 2:
            min_v, max_v = float(money[0]), float(money[1])
            if picked.get("type") in int_amount_types:
                result["amount"] = random.randint(int(min_v), int(max_v))
            else:
                result["amount"] = random_amount(min_v, max_v)
        elif isinstance(money, (int, float)):
            result["amount"] = float(money)

        # items 子项随机
        if picked.get("items") and isinstance(picked["items"], list) and picked["items"]:
            result["props"] = random.choice(picked["items"])

    return {
        "type": result.get("type", ""),
        "amount": result.get("amount", 0),
        "props": result.get("props"),
        "desc": result.get("desc", ""),
    }


# ==================== 批量抽奖 ====================

def draw_batch(config: dict, options: Optional[dict] = None) -> list[dict]:
    """
    批量抽奖：
    - no_duplicate=True: 抽中后从池中排除
    - 奖池抽空提前返回
    """
    opts = dict(options or {})
    batch_count = opts.get("batch_count", 1)
    no_duplicate = opts.get("no_duplicate", True)
    mode = (opts.get("mode") or config.get("mode") or "pool").lower()

    results = []
    excluded_types = list(opts.get("exclude_types") or [])

    for _ in range(batch_count):
        batch_opts = dict(opts)
        if excluded_types:
            batch_opts["exclude_types"] = list(excluded_types)

        if mode == "tiered":
            result = draw_tiered(config, batch_opts)
        else:
            result = draw_pool(config, batch_opts)

        if not result or result.get("type") == "none":
            break

        results.append(result)

        # 去重：将抽中类型加入排除列表
        if no_duplicate and result.get("type"):
            excluded_types.append(result["type"])

    return results


# ==================== 统一入口 ====================

def draw(config: dict, options: Optional[dict] = None) -> Optional[dict]:
    """
    统一抽奖入口，自动识别配置结构。
    返回 {"type": ..., "amount": ..., "props": ..., "desc": ...}
    """
    opts = options or {}

    # 手动指定 mode
    mode = opts.get("mode") or config.get("mode") or ""

    if mode == "tiered" or config.get("level_rewards"):
        return draw_tiered(config, opts)

    return draw_pool(config, opts)
