"""
============================================
文本向量适配器 - 商品语义检索的模型调用
============================================
提供可替换的向量化接口，复用千问公共请求的后端鉴权与网络异常处理。
校验返回向量的数量、顺序、维度及数值，避免错误数据污染本地索引。
"""

import asyncio
import math
from collections.abc import Sequence
from typing import Protocol

from app.common.exception import AppException
from app.core.config import settings
from app.services.qwen_ai_service import QwenAIService


class EmbeddingAdapter(Protocol):
    """隔离具体模型，便于替换厂商和注入测试向量。"""

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """按输入顺序返回商品文档的向量。"""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """返回一条搜索文本的向量。"""
        ...


class QwenEmbedding:
    """使用兼容接口生成向量，不依赖 Chroma 的默认模型下载。"""

    MAX_BATCH_SIZE = 10

    def __init__(self) -> None:
        """读取后端模型配置，不发起请求。"""
        self.model = settings.QWEN_EMBEDDING_MODEL
        self.dimensions = settings.QWEN_EMBEDDING_DIMENSIONS

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """分批向量化，整个调用共用超时预算，避免重试耗尽工具预算。"""
        if not texts:
            return []
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise AppException(msg="向量化文本不能为空")
        if not settings.QWEN_EMBEDDING_URL:
            raise AppException(msg="千问向量接口地址未配置")
        if not self.model or self.dimensions <= 0:
            raise AppException(msg="千问向量模型或维度配置错误")
        batch_size = min(settings.GOODS_EMBEDDING_BATCH_SIZE, self.MAX_BATCH_SIZE)
        timeout = min(
            settings.QWEN_EMBEDDING_TIMEOUT,
            settings.AGENT_TOOL_TIMEOUT * 0.8,
        )
        if batch_size < 1 or timeout <= 0:
            raise AppException(msg="千问向量批量或超时配置错误")

        vectors: list[list[float]] = []
        try:
            async with asyncio.timeout(timeout):
                for offset in range(0, len(texts), batch_size):
                    batch = list(texts[offset : offset + batch_size])
                    vectors.extend(await self._embed_batch(batch))
        except TimeoutError as exc:
            raise AppException(msg="商品文本向量化超时，请稍后重试") from exc
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        """搜索与建库使用相同模型和维度。"""
        return (await self.embed_documents([text]))[0]

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """校验兼容接口的索引，允许上游乱序返回但拒绝缺失或重复。"""
        payload = {
            "model": self.model,
            "input": texts,
            "dimensions": self.dimensions,
            "encoding_format": "float",
        }
        async with QwenAIService.request(
            payload,
            url=settings.QWEN_EMBEDDING_URL,
            stream=False,
        ) as response:
            await response.aread()
            try:
                data = response.json()
            except ValueError as exc:
                raise AppException(msg="向量服务返回格式错误") from exc

        if not isinstance(data, dict) or data.get("error") or data.get("code"):
            raise AppException(msg="向量服务返回异常，请稍后重试")
        items = data.get("data")
        if not isinstance(items, list) or len(items) != len(texts):
            raise AppException(msg="向量服务返回数量不一致")
        ordered: dict[int, list[float]] = {}
        for item in items:
            if not isinstance(item, dict):
                raise AppException(msg="向量服务返回格式错误")
            index = item.get("index")
            if type(index) is not int or index < 0 or index >= len(texts) or index in ordered:
                raise AppException(msg="向量服务返回索引错误")
            vector = item.get("embedding")
            ordered[index] = validate_embedding(vector, self.dimensions)
        return [ordered[index] for index in range(len(texts))]


def validate_embedding(vector: object, dimensions: int) -> list[float]:
    """校验模型及注入适配器的向量，拒绝布尔值、非有限数和零向量。"""
    if not isinstance(vector, (list, tuple)) or len(vector) != dimensions:
        raise AppException(msg="向量维度与索引配置不一致，请重建索引")
    result: list[float] = []
    for value in vector:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AppException(msg="向量服务返回了无效数值")
        try:
            number = float(value)
        except (ValueError, OverflowError) as exc:
            raise AppException(msg="向量服务返回了无效数值") from exc
        if not math.isfinite(number):
            raise AppException(msg="向量服务返回了无效数值")
        result.append(number)
    if not any(result):
        raise AppException(msg="向量服务返回了无效零向量")
    return result
