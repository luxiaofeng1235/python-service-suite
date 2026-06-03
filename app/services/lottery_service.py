"""
============================================
抽奖业务服务
============================================
"""
import json
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import AppException
from app.config import lottery as config_lottery
from app.core.config import settings
from app.core.lottery import draw, draw_batch
from app.models.lottery_record import LotteryRecord


class LotteryConfigLoader:
    """抽奖配置加载器 — DB 优先，文件兜底"""

    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db

    async def load(self, key: str) -> Optional[dict]:
        """
        加载配置。
        支持 key 格式:
        - "sign_reward"       → DB；开启 LOTTERY_ALLOW_FILE_FALLBACK 后可文件兜底
        - "file://sign_reward" → 强制文件，仅 LOTTERY_ALLOW_FILE_FALLBACK=true 可用
        - "db://sign_reward"  → 强制 DB
        """
        if "://" in key:
            scheme, name = key.split("://", 1)
            if scheme == "db":
                return await self._from_db(name)
            if scheme == "file" and settings.LOTTERY_ALLOW_FILE_FALLBACK:
                return self._from_file(name)
            if scheme == "file":
                raise AppException(code=10006, msg="当前环境不允许读取文件抽奖配置")
            raise AppException(code=10006, msg=f"不支持的抽奖配置来源: {scheme}")

        # DB 优先
        if self.db:
            cfg = await self._from_db(key)
            if cfg:
                return cfg
        if settings.LOTTERY_ALLOW_FILE_FALLBACK:
            return self._from_file(key)
        return None

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
    async def draw_for_user(
        db: AsyncSession,
        config_key: str,
        user_id: Optional[int],
        options: Optional[dict] = None,
        request_id: Optional[str] = None,
    ) -> list[dict]:
        """抽奖入口，负责配置加载、抽奖记录与幂等；登录用户可校验次数。"""
        opts = LotteryDrawService._sanitize_options(options)
        config = await LotteryDrawService._load_config(db, config_key)

        record_user_id = user_id or 0
        if request_id:
            existed = await LotteryDrawService._get_records_by_request_id(db, config_key, record_user_id, request_id)
            if existed:
                return [json.loads(record.result_json) for record in existed]

        if user_id is not None:
            await LotteryDrawService._check_daily_limit(db, config, config_key, user_id, opts["batch_count"])

        if opts["batch_count"] > 1:
            results = draw_batch(config, opts)
        else:
            result = draw(config, opts)
            results = [result] if result else []

        if not results:
            raise AppException(code=10005, msg="抽奖失败")
        if any((not result) or result.get("type") == "none" for result in results):
            raise AppException(code=10005, msg="奖池过滤后为空")

        try:
            return await LotteryDrawService._save_records(db, config_key, record_user_id, results, request_id)
        except IntegrityError:
            if not request_id:
                raise
            await db.rollback()
            existed = await LotteryDrawService._get_records_by_request_id(db, config_key, record_user_id, request_id)
            if existed:
                return [json.loads(record.result_json) for record in existed]
            raise

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
            raise AppException(code=10001, msg=f"抽奖配置不存在: {config_key}")
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

    @staticmethod
    async def _check_daily_limit(
        db: AsyncSession,
        config: dict,
        config_key: str,
        user_id: int,
        batch_count: int,
    ) -> None:
        """按配置 daily_limit 校验用户每日抽奖次数。"""
        daily_limit = config.get("daily_limit")
        if daily_limit is None:
            raise AppException(code=10009, msg="抽奖配置缺少 daily_limit")

        daily_limit = int(daily_limit)
        if daily_limit <= 0:
            raise AppException(code=10007, msg="当前活动不允许抽奖")

        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        result = await db.execute(
            select(LotteryRecord).where(
                LotteryRecord.scene_key == config_key,
                LotteryRecord.user_id == user_id,
                LotteryRecord.created_at >= today,
                LotteryRecord.created_at < tomorrow,
            )
        )
        used_count = len(result.scalars().all())
        if used_count + batch_count > daily_limit:
            raise AppException(code=10008, msg="今日抽奖次数不足")

    @staticmethod
    async def _get_records_by_request_id(
        db: AsyncSession,
        config_key: str,
        user_id: int,
        request_id: str,
    ) -> list[LotteryRecord]:
        result = await db.execute(
            select(LotteryRecord)
            .where(
                LotteryRecord.scene_key == config_key,
                LotteryRecord.user_id == user_id,
                LotteryRecord.request_id == request_id,
            )
            .order_by(LotteryRecord.draw_index.asc(), LotteryRecord.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def _save_records(
        db: AsyncSession,
        config_key: str,
        user_id: int,
        results: list[dict],
        request_id: Optional[str] = None,
    ) -> list[dict]:
        saved_results = []
        for index, result in enumerate(results):
            record = LotteryRecord(
                user_id=user_id,
                scene_key=config_key,
                request_id=request_id,
                draw_index=index,
                prize_type=result.get("type", ""),
                prize_id=result.get("prize_id"),
                amount=str(result.get("amount", 0)),
                props_json=json.dumps(result.get("props"), ensure_ascii=False),
                result_json=json.dumps(result, ensure_ascii=False),
                grant_status="pending",
            )
            db.add(record)
            await db.flush()

            saved_result = dict(result)
            saved_result["record_id"] = record.id
            saved_results.append(saved_result)

            record.result_json = json.dumps(saved_result, ensure_ascii=False)

        return saved_results
