"""
============================================
抽奖系统 Pydantic 模型
============================================
"""
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class LotteryMode(str, Enum):
    """抽奖模式"""
    TIERED = "tiered"
    POOL = "pool"


class PoolItem(BaseModel):
    """奖池单项"""
    type: str
    v: int = 1
    money: Optional[Any] = None
    props: Optional[Any] = None
    items: Optional[list] = None
    desc: Optional[str] = None
    min_cash: Optional[float] = None
    max_cash: Optional[float] = None
    weight: Optional[int] = None  # tiered rewards 用


class NestedPoolItem(BaseModel):
    """二级嵌套奖池项（tiered odds 结构）"""
    type: str
    v: int = 1
    money: Optional[Any] = None
    props: Optional[Any] = None


class LevelReward(BaseModel):
    """层级奖励配置"""
    odds: Optional[list[NestedPoolItem]] = None
    rewards: Optional[list[PoolItem]] = None
    min_cash: Optional[float] = None
    max_cash: Optional[float] = None


class LotteryConfig(BaseModel):
    """完整抽奖配置"""
    mode: Optional[str] = None
    level_rewards: Optional[dict[int, LevelReward]] = None
    reward_pool: Optional[list[PoolItem]] = None
    free_reward_pool: Optional[list[PoolItem]] = None
    paid_reward_pool: Optional[list[PoolItem]] = None
    pool: Optional[list[PoolItem]] = None


class LotteryOptions(BaseModel):
    """运行时参数"""
    mode: Optional[LotteryMode] = Field(default=None, description="抽奖模式，强制指定 tiered / pool，默认自动识别")
    level: int = Field(default=1, description="等级（tiered 模式必填，对应 level_rewards 的 key）")
    pool_key: str = Field(default="reward_pool", description="奖池 key（pool 模式用，可选 reward_pool / free_reward_pool / paid_reward_pool / pool）")
    batch_count: int = Field(default=1, description="批量抽奖次数，>1 走批量模式，默认 1")
    no_duplicate: bool = Field(default=True, description="批量时是否去重，true=抽过的不再出现")
    exclude_types: Optional[list[str]] = Field(default=None, description="排除的奖励类型列表，如 ['cash', 'prop']")
    exclude_cash: bool = Field(default=False, description="是否排除现金类奖励")
    cash_weight_factor: float = Field(default=1.0, description="现金权重倍率，活动翻倍用，范围 [0, 10]")
    int_amount_types: Optional[list[str]] = Field(default=None, description="整数金额类型列表（默认 yl/yq），匹配的类型金额取整")


class LotteryResult(BaseModel):
    """抽奖结果"""
    type: str = Field(default="", description="奖励类型 cash/prop/score/physical/coupon 等")
    amount: float = Field(default=0, description="金额（现金/积分类）")
    props: Any = Field(default=None, description="附加信息（道具ID/实物信息/优惠券信息等）")
    desc: str = Field(default="", description="描述")


class LotteryDrawRequest(BaseModel):
    """抽奖请求"""
    config_key: str = Field(default="", description="配置场景标识，如 default / sign_reward / recharge，对应 DB lottery_configs.scene_key")
    options: Optional[LotteryOptions] = Field(default=None, description="运行时参数（可选）")


class LotteryDrawResponse(BaseModel):
    """抽奖响应"""
    code: int = 1
    msg: str = "抽奖成功"
    data: Optional[list[LotteryResult]] = None
