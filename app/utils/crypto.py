"""
============================================
接口签名验签工具模块
============================================
提供参数排序 + SHA256 签名验签能力，用于前后端接口防篡改，
防止外部人员暴力破解。

协议约定：
    1. 客户端传所有业务参数 + sign + timestamp
    2. 服务端去掉 sign，按 key 字典序排序 → key1value1key2value2... + timestamp
    3. sha256(上述拼接字符串 + API_ENCRYPT_KEY) → 与 sign 比对
    4. 校验 timestamp 是否在有效窗口内（防重放）

签名计算示例：
    参数: {"username": "admin", "password": "123"}
    timestamp: 1700000000000
    key: mysecret
    排序拼接: password123usernameadmin
    加时间戳: password123usernameadmin1700000000000
    签名: sha256("password123usernameadmin1700000000000mysecret")

协议约束（前端对接必读）：
    1. 签名参数只允许标量（字符串 / 数字），禁止数组和嵌套对象
       - 如需传数组，前端先 JSON.stringify 转成字符串当普通参数传
       - 禁止 bool 类型参与签名（需转 "1" / "0" 后传字符串）
    2. secret_key 必须拼在拼接串最末尾，勿调整顺序（否则安全模型失效）
    3. timestamp 不参与业务参数排序，只在末尾加一次，单位毫秒（13 位）
    4. 客户端时间需大致准确，偏差超过 5 分钟将返回 403
"""

import hashlib
import hmac
import time
from typing import Any


def compute_sign(params: dict[str, Any], secret_key: str, timestamp: int | None = None) -> str:
    """
    计算参数签名（客户端 / 服务端均可使用）

    按 key 字典序排序后拼接为 key1value1key2value2... + timestamp，
    最后拼接 secret_key 做 sha256 签名。

    Args:
        params: 参数字典（不含 sign 本身）
        secret_key: 签名密钥
        timestamp: 时间戳（毫秒），不传则取当前时间

    Returns:
        64 位 hex 签名

    Raises:
        ValueError: 参数含嵌套对象 / 数组 / bool 时抛出
    """
    if timestamp is None:
        timestamp = int(time.time() * 1000)

    # 0. 校验参数类型（禁止嵌套对象 / 数组 / bool）
    for k, v in params.items():
        if isinstance(v, (dict, list)):
            raise ValueError(f"参数 '{k}' 为 {type(v).__name__} 类型，签名参数不支持嵌套，请先 JSON.stringify 转成字符串")
        if isinstance(v, bool):
            raise ValueError(f"参数 '{k}' 为 bool 类型，签名参数不支持 bool，请转成 '1' / '0' 字符串")

    # 1. 按 key 排序
    sorted_keys = sorted(params.keys())
    # 2. 拼接
    raw = "".join(f"{k}{params[k]}" for k in sorted_keys)
    raw += str(timestamp)
    # 3. sha256
    raw += secret_key
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_sign(
    params: dict[str, Any],
    sign: str,
    secret_key: str,
    timestamp: int,
    ttl_ms: int = 300_000,
) -> None:
    """
    验证签名（服务端使用）

    Args:
        params: 业务参数字典（不含 sign）
        sign: 客户端传入的签名
        secret_key: 签名密钥
        timestamp: 客户端传入的时间戳
        ttl_ms: 有效时间窗口（毫秒），默认 5 分钟

    Raises:
        ValueError: 验签或时间戳异常
    """
    # 1. 防重放校验
    now_ms = int(time.time() * 1000)
    diff = abs(now_ms - timestamp)
    if diff > ttl_ms:
        raise ValueError(f"请求已过期或时间戳异常（偏差 {diff}ms）")

    # 2. 签名校验
    expected = compute_sign(params, secret_key, timestamp)
    if not hmac.compare_digest(expected, sign):
        raise ValueError("签名验证失败")
