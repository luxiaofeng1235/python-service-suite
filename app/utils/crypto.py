"""
============================================
接口加解密工具模块
============================================
提供 AES-256 加密 + HMAC-SHA256 签名验签能力，
用于前后端接口参数加密传输，防止外部暴力破解。

协议格式：
    {
        "encrypt_data": "<base64 加密数据>",
        "sign": "<HMAC-SHA256 签名>",
        "timestamp": 1700000000000
    }

验签流程：
    1. 校验 timestamp 是否在有效窗口内（防重放）
    2. 校验 HMAC-SHA256 签名（防篡改）
    3. 解密 encrypt_data 得到原始 JSON 参数
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from cryptography.fernet import Fernet


def _derive_fernet_key(raw_key: str) -> bytes:
    """将任意长度的密钥派生出 32 字节并编码为 Fernet 需要的 base64 格式"""
    key_bytes = hashlib.sha256(raw_key.encode("utf-8")).digest()[:32]
    return base64.urlsafe_b64encode(key_bytes)


def encrypt_request(body: dict[str, Any], raw_key: str) -> dict[str, Any]:
    """
    加密请求体（客户端使用）

    Args:
        body: 原始请求参数字典
        raw_key: 加密密钥字符串

    Returns:
        加密后的请求体（encrypt_data / sign / timestamp）
    """
    fernet = Fernet(_derive_fernet_key(raw_key))
    plaintext = json.dumps(body, separators=(",", ":")).encode("utf-8")
    encrypt_data = fernet.encrypt(plaintext).decode("utf-8")
    timestamp = int(time.time() * 1000)

    sign = _compute_sign(encrypt_data, timestamp, raw_key)

    return {
        "encrypt_data": encrypt_data,
        "sign": sign,
        "timestamp": timestamp,
    }


def decrypt_request(encrypted_body: dict[str, Any], raw_key: str, ttl_ms: int = 300_000) -> dict[str, Any]:
    """
    解密请求体（服务端使用）

    Args:
        encrypted_body: 加密后的请求体 {encrypt_data, sign, timestamp}
        raw_key: 加密密钥字符串
        ttl_ms: timestamp 有效窗口（毫秒），默认 5 分钟

    Returns:
        解密后的原始参数字典

    Raises:
        ValueError: 验签或解密失败
    """
    encrypt_data = encrypted_body.get("encrypt_data", "")
    sign = encrypted_body.get("sign", "")
    timestamp = encrypted_body.get("timestamp", 0)

    if not encrypt_data or not sign or not timestamp:
        raise ValueError("缺少加密参数：encrypt_data / sign / timestamp")

    # 1. 防重放校验
    now_ms = int(time.time() * 1000)
    if abs(now_ms - timestamp) > ttl_ms:
        raise ValueError(f"请求已过期或时间戳异常（偏差 {abs(now_ms - timestamp)}ms）")

    # 2. 签名校验
    expected_sign = _compute_sign(encrypt_data, timestamp, raw_key)
    if not hmac.compare_digest(expected_sign, sign):
        raise ValueError("签名验证失败")

    # 3. 解密
    fernet = Fernet(_derive_fernet_key(raw_key))
    plaintext = fernet.decrypt(encrypt_data.encode("utf-8"))
    return json.loads(plaintext.decode("utf-8"))


def _compute_sign(encrypt_data: str, timestamp: int, raw_key: str) -> str:
    """计算 HMAC-SHA256 签名"""
    msg = f"{encrypt_data}{timestamp}".encode("utf-8")
    key = raw_key.encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()
