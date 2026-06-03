"""
============================================
抽奖业务服务
============================================
"""
import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import AppException
from app.config import lottery as config_lottery
from app.core.lottery import draw, draw_batch


class LotteryConfigLoader:
    """抽奖配置加载器 — DB 优先，文件兜底"""

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db

    async def load(self, key: str) -> Optional[dict]:
        """
        加载配置。
        支持 key 格式:
        - "sign_reward"       → DB → 文件
        - "file://sign_reward" → 强制文件
        - "db://sign_reward"  → 强制 DB
        """
        if "://" in key:
            scheme, name = key.split("://", 1)
            if scheme == "db":
                return await self._from_db(name)
            return self._from_file(name)

        # DB 优先
        if self.db:
            cfg = await self._from_db(key)
            if cfg:
                return cfg
        return self._from_file(key)

    async def _from_db(self, key: str) -> Optional[dict]:
        """从 lottery_configs 表加载"""
        from app.models import LotteryConfig  # noqa

        result = await self.db.execute(
            select(LotteryConfig).where(
                LotteryConfig.scene_key == key,
                LotteryConfig.status == 1,
            ).limit(1)
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        if isinstance(row.config_json, str):
            cfg = json.loads(row.config_json)
        else:
            cfg = dict(row.config_json)

        # JSON 不支持整数 key，level_rewards 的 key 从字符串转整数
        if isinstance(cfg.get("level_rewards"), dict):
            cfg["level_rewards"] = {
                int(k): v for k, v in cfg["level_rewards"].items()
            }
        return cfg

    @staticmethod
    def _from_file(key: str) -> Optional[dict]:
        """从 config/lottery.py 的内置配置加载"""
        name = key.replace("/", "_")
        return getattr(config_lottery, name.upper(), None)


class LotteryDrawService:
    """抽奖流程封装 加载 → 校验 → 抽取 → 返回"""

    @staticmethod
    async def draw_once(
        db: AsyncSession,
        config_key: str,
        options: Optional[dict] = None,
    ) -> dict:
        """单次抽奖"""
        opts = options or {}
        config = await LotteryDrawService._load_config(db, config_key)
        result = draw(config, opts)
        if not result or result.get("type") == "none":
            raise AppException(code=10005, msg="奖池过滤后为空" if result else "抽奖失败")
        return result

    @staticmethod
    async def draw_batch(
        db: AsyncSession,
        config_key: str,
        options: Optional[dict] = None,
    ) -> list[dict]:
        """批量抽奖"""
        opts = options or {}
        config = await LotteryDrawService._load_config(db, config_key)
        return draw_batch(config, opts)

    @staticmethod
    async def _load_config(db: AsyncSession, config_key: str) -> dict:
        """加载并校验配置"""
        loader = LotteryConfigLoader(db)
        config = await loader.load(config_key)
        if not config:
            raise AppException(code=10001, msg=f"抽奖配置不存在: {config_key}")
        if not config.get("level_rewards") and not config.get("reward_pool") and not config.get("pool"):
            raise AppException(code=10003, msg="配置结构无法识别")
        return config
