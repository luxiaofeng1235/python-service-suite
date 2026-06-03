"""
============================================
抽奖 API 路由
============================================
"""
from fastapi import APIRouter, Depends

from app.common.response import Response
from app.database import get_session
from app.schemas.lottery import LotteryDrawRequest
from app.services.lottery_service import LotteryDrawService

router = APIRouter(prefix="/api/lottery", tags=["抽奖"])


@router.post("/draw", summary="抽奖")
async def lottery_draw(
    req: LotteryDrawRequest,
    db=Depends(get_session),
):
    """
    抽奖接口。
    请求体示例:
    批量抽奖：
    {

        "config_key": "sign_reward", #场景标识
        "options": { 
            "level": 1, #层级
            "exclude_cash": false, 排除的奖励类型列表，如 ["cash", "prop"]，默认false
            "batch_count": 1 #批量抽奖次数，>1 走批量模式，默认 1
        }
    }
    单层抽奖：
    {"config_key": "default", "options": {"batch_count": 1}}
    """
    opts = req.options.dict() if req.options else {}
    batch_count = opts.get("batch_count", 1)
    opts["batch_count"] = batch_count

    if batch_count > 1:
        results = await LotteryDrawService.draw_batch(db, req.config_key, opts)
    else:
        result = await LotteryDrawService.draw_once(db, req.config_key, opts)
        results = [result]

    return Response.success(data=results, msg="抽奖成功")
