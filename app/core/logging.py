"""
============================================
日志配置模块 — 基于 loguru
============================================
对标 Go 版多个全局 Logger 的写法，按业务域分流到独立文件。

使用方式：
    from app.core.logging import pay_logger
    pay_logger.info("订单 {} 支付成功", order_id)

    from app.core.logging import app_logger
    app_logger.error("数据库错误: {}", err)

    from app.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("通用日志")
"""

import os
import sys

from loguru import logger

from app.core.config import settings

# ============================================================
# 预定义的业务日志文件映射
# ============================================================
# 新增业务只需在此加一行，然后 logger.bind(biz="xxx") 即可
LOG_FILES: dict[str, str] = {
    "app":      "app.log",           # 通用/杂项
    "request":  "request.log",       # HTTP 请求日志
    "slow":     "slow_request.log",  # 慢请求（>= SLOW_REQUEST_MS）
    "pay":      "pay.log",           # 支付业务
    "sql":      "sql.log",           # SQL 审计
    "ws":       "ws.log",            # WebSocket
    "collect":  "collect.log",       # 采集/爬虫
    "task":     "task.log",          # 定时任务
}


def _biz_filter(name: str):
    """生成 filter 闭包，只放行指定 biz 的日志"""
    return lambda record: record["extra"].get("biz", "app") == name


def setup_logging() -> None:
    """初始化 loguru 日志配置（应用启动时调用一次）"""
    log_dir = settings.LOG_DIR
    os.makedirs(log_dir, exist_ok=True)

    log_level = settings.LOG_LEVEL.upper()

    # 清除默认 sink（否则控制台会重复输出）
    logger.remove()

    # ==================== 控制台输出（彩色） ====================
    logger.add(
        sys.stderr,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> "
            "| <level>{level:7}</level> "
            "| <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
            "| <level>{message}</level>"
        ),
        colorize=True,
    )

    # ==================== 按业务域分文件 ====================
    for biz_name, filename in LOG_FILES.items():
        # 慢请求单独用 WARNING 级别
        lvl = "WARNING" if biz_name == "slow" else log_level

        logger.add(
            os.path.join(log_dir, filename),
            filter=_biz_filter(biz_name),
            level=lvl,
            rotation="1 day",
            retention="14 days",
            encoding="utf-8",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level:7} | {message}",
            # 慢请求日志额外记录调用位置
            **(  # type: ignore[arg-type]
                {"backtrace": True, "diagnose": False}
                if biz_name == "slow"
                else {}
            ),
        )


# ============================================================
# 对外暴露的全局 Logger（对标 Go 版全局变量）
# ============================================================
# 用法：from app.core.logging import pay_logger
#       pay_logger.info("回调处理完成")

app_logger     = logger.bind(biz="app")
request_logger = logger.bind(biz="request")
slow_logger    = logger.bind(biz="slow")
pay_logger     = logger.bind(biz="pay")
sql_logger     = logger.bind(biz="sql")
ws_logger      = logger.bind(biz="ws")
collect_logger = logger.bind(biz="collect")
task_logger    = logger.bind(biz="task")


def get_logger(name: str | None = None) -> "logger":  # type: ignore[type-arg]
    """供 utils / services 等通用模块使用的简便方法

    用法：
        from app.core.logging import get_logger
        logger = get_logger(__name__)
        logger.info("任意日志")
    """
    return logger.bind(biz="app", module=name or "unknown")
