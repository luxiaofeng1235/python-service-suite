"""
============================================
抽奖 API 路由
============================================
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import Response
from app.database import get_session
from app.schemas.lottery import LotteryDrawRequest
from app.services.lottery_service import LotteryDrawService

router = APIRouter(prefix="/api/lottery", tags=["抽奖"])


@router.post("/draw", summary="抽奖")
async def lottery_draw(
    req: LotteryDrawRequest,
    db: AsyncSession = Depends(get_session),
):
    """
    抽奖接口。
    请求体示例:
    批量抽奖：
    {

        "config_key": "sign_reward", #场景标识
        "level": 1,
        "batch_count": 1
    }
    """
    opts = {
        "level": req.level,
        "batch_count": req.batch_count,
    }
    results = await LotteryDrawService.draw_result(
        db,
        config_key=req.config_key,
        options=opts,
    )

    return Response.success(data=results, msg="抽奖成功")
