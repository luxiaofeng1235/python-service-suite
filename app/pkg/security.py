"""
============================================
安全模块 — 短 Token 生成 + 密码加密
============================================
"""

import secrets

from passlib.context import CryptContext

# ==================== 密码加密 ====================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """对明文密码进行 bcrypt 哈希"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码 vs 已哈希的密码"""
    return pwd_context.verify(plain_password, hashed_password)


# ==================== 短 Token ====================
def create_short_token() -> str:
    """生成 32 位 hex 登录 Token"""
    return secrets.token_hex(16)
