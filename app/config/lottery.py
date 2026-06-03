"""
============================================
抽奖配置 — 示例奖池定义
============================================
"""

# 通用奖池（Pool 模式）
DEFAULT_POOL = {
    "mode": "pool",
    "reward_pool": [
        {"type": "cash",     "v": 40, "money": [0.5, 5],                                     "desc": "现金红包"},
        {"type": "prop",     "v": 30, "props": "gift_001",                                   "desc": "金币"},
        {"type": "score",    "v": 20, "money": [10, 100],                                    "desc": "积分"},
        {"type": "physical", "v": 5,  "props": {"name": "蓝牙音箱", "image": "https://...", "need_address": True}, "desc": "蓝牙音箱"},
        {"type": "coupon",   "v": 5,  "props": {"coupon_id": 1001, "amount": 10},            "desc": "10元优惠券"},
    ],
}

# 签到奖励（Tiered 模式，含二级嵌套）
SIGN_REWARD = {
    "mode": "tiered",
    "level_rewards": {
        1: {
            "odds": [
                {
                    "type": "cash", "v": 40, "desc": "现金红包",
                    "money": [
                        {"type": "小额现金", "v": 70, "money": [0.1, 0.5], "desc": "小额现金"},
                        {"type": "大额现金", "v": 30, "money": [0.5, 2], "desc": "大额现金"},
                    ],
                },
                {"type": "prop", "v": 30, "props": "sign_card", "desc": "签到卡"},
                {"type": "score", "v": 30, "money": [5, 50], "desc": "积分"},
            ],
        },
        2: {
            "rewards": [
                {"type": "cash", "weight": 50, "min_cash": 0.5, "max_cash": 3, "desc": "现金红包"},
                {"type": "prop", "weight": 30, "props": "sign_card", "desc": "签到卡"},
                {"type": "score", "weight": 20, "money": [10, 100], "desc": "积分"},
            ],
            "min_cash": 0.1,
            "max_cash": 1,
        },
    },
}
