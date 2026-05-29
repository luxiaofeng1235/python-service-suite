from fastapi import APIRouter

from app.common import response
from app.common.response import Response

#初始化API的整体路由
router = APIRouter(prefix="/api/test",tags=["api测试"])


@router.get("/testarr", tags=["api"])

async def test():
    """
    测试参数流程
    """
    items = {
        "test": "test",
        "age": 1,
        "name": "张三",
        "status": True,
    }
    return Response.success(items,"测试路由")

@router.get("/testget", tags=["api"])
async def testget(
    name:str ,
    age:int = 18):
    """
    测试接收参数 ，可以铜鼓name和age来接受参数判断
    """
    items = {
        "name": name,
        "age": age,
    }
    return Response.success(items)
