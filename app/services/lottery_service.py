"""
============================================
抽奖业务服务
============================================
"""
import json
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import AppException
from app.core.lottery import draw, draw_batch


class LotteryConfigLoader:
    """抽奖配置加载器 — DB 优先，JSON 文件兜底"""

    JSON_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config" / "lottery"

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db

    async def load(self, key: str) -> Optional[dict]:
        """
        加载配置。
        支持 key 格式:
        - "sign_reward"       → DB → config/lottery/sign_reward.json
        - "file://sign_reward" → 强制读取 config/lottery/sign_reward.json
        - "db://sign_reward"  → 强制 DB
        """
        if "://" in key:
            scheme, name = key.split("://", 1)
            if scheme == "db":
                return await self._from_db(name)
            if scheme == "file":
                return self._from_json_file(name)
            raise AppException(code=10006, msg=f"不支持的抽奖配置来源: {scheme}")

        # DB 优先
        if self.db:
            cfg = await self._from_db(key)
            if cfg:
                return cfg
        return self._from_json_file(key)

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
    def _from_json_file(key: str) -> Optional[dict]:
        """从 config/lottery/{key}.json 加载"""
        if "/" in key or "\\" in key or ".." in key:
            raise AppException(code=10006, msg=f"非法抽奖配置标识: {key}")

        file_path = LotteryConfigLoader.JSON_CONFIG_DIR / f"{key}.json"
        if not file_path.exists():
            return None

        with file_path.open("r", encoding="utf-8") as f:
            cfg = json.load(f)

        if isinstance(cfg.get("level_rewards"), dict):
            cfg["level_rewards"] = {
                int(k): v for k, v in cfg["level_rewards"].items()
            }
        return cfg


class LotteryDrawService:
    """抽奖流程封装 加载 → 校验 → 抽取 → 返回"""

    @staticmethod
    async def draw_result(
        db: AsyncSession,
        config_key: str,
        options: Optional[dict] = None,
    ) -> list[dict]:
        """纯抽奖入口，只按奖池概率返回奖品结果，不落库。"""
        opts = LotteryDrawService._sanitize_options(options)
        #加载配置 根据指定的配置来加载，默认DB->config
        config = await LotteryDrawService._load_config(db, config_key)

        if opts["batch_count"] > 1:
            #批量抽奖
            results = draw_batch(config, opts)
        else:
            #单次抽奖
            result = draw(config, opts)
            results = [result] if result else []

        if not results:
            raise AppException(code=10005, msg="抽奖失败")
        if any((not result) or result.get("type") == "none" for result in results):
            raise AppException(code=10005, msg="奖池过滤后为空")

        return results

    @staticmethod
    async def draw_once(
        db: AsyncSession,
        config_key: str,
        options: Optional[dict] = None,
    ) -> dict:
        """单次抽奖算法调试入口，不做用户记录。"""
        opts = LotteryDrawService._sanitize_options(options)
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
        opts = LotteryDrawService._sanitize_options(options)
        config = await LotteryDrawService._load_config(db, config_key)
        return draw_batch(config, opts)

    @staticmethod
    async def _load_config(db: AsyncSession, config_key: str) -> dict:
        """加载并校验配置"""
        loader = LotteryConfigLoader(db)
        config = await loader.load(config_key)
        if not config:
            raise AppException(code=10001, msg=f"获取不到奖池配置，请先配置 场景标识: {config_key}")
        if not config.get("level_rewards") and not config.get("reward_pool") and not config.get("pool"):
            raise AppException(code=10003, msg="配置结构无法识别")
        return config

    @staticmethod
    def _sanitize_options(options: Optional[dict] = None) -> dict:
        """只保留后端允许控制的运行参数。"""
        opts = dict(options or {})
        batch_count = int(opts.get("batch_count") or 1)
        if batch_count < 1 or batch_count > 10:
            raise AppException(code=10004, msg="batch_count 允许范围为 1-10")

        return {
            "level": int(opts.get("level") or 1),
            "batch_count": batch_count,
            "no_duplicate": True,
        }
