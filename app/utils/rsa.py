"""
============================================
rsa — RSA / AES 加解密工具（对标 Go rsa.go）
============================================
包含 RSA 公钥加密/私钥解密、AES-ECB 加解密、AES-CFB 加解密。
"""

import binascii
import logging
import os

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding, serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding as asym_padding

logger = logging.getLogger(__name__)

AES_BLOCK_SIZE = 16
# 对标 Go EncodeStr2Base64 / DecodeStrFromBase64（rsa.go 中导出的公共函数）


def encode_str_to_base64(s: str) -> str:
    """字符串 → base64 编码（对标 Go EncodeStr2Base64）"""
    import base64
    return base64.b64encode(s.encode("utf-8")).decode("utf-8")


def decode_str_from_base64(s: str) -> str:
    """base64 字符串 → 原文（对标 Go DecodeStrFromBase64）"""
    import base64
    return base64.b64decode(s).decode("utf-8")


# ── 内部辅助 ────────────────────────────────────────────────

def _generate_key(key: bytes) -> bytes:
    """对标 Go generateKey：取前 16 字节，后续字节异或到前 16 字节上"""
    gen_key = bytearray(16)
    for i, b in enumerate(key):
        if i < 16:
            gen_key[i] = b
        else:
            gen_key[i % 16] ^= b
    return bytes(gen_key)


def _pkcs7_pad(data: bytes, block_size: int = AES_BLOCK_SIZE) -> bytes:
    pad_len = block_size - len(data) % block_size
    return data + bytes([pad_len] * pad_len)


def _pkcs7_unpad(data: bytes, block_size: int = AES_BLOCK_SIZE) -> bytes:
    if len(data) == 0 or len(data) % block_size != 0:
        raise ValueError("Invalid padding")
    pad_len = data[-1]
    if pad_len < 1 or pad_len > block_size:
        raise ValueError("Invalid padding value")
    if data[-pad_len:] != bytes([pad_len] * pad_len):
        raise ValueError("Invalid padding bytes")
    return data[:-pad_len]


# ── RSA ─────────────────────────────────────────────────────

def rsa_read_key_from_file(filename: str) -> bytes:
    """从 PEM 文件中读取密钥内容"""
    with open(filename, "rb") as f:
        return f.read()


def rsa_encrypt(data: str | bytes, public_pem: str | bytes) -> bytes:
    """
    RSA 公钥加密（PKCS1v15），返回 base64 编码的密文字节。
    对标 Go RSAEncrypt。
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    if isinstance(public_pem, str):
        public_pem = public_pem.encode("utf-8")

    public_key = serialization.load_pem_public_key(public_pem)
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise TypeError("提供的 PEM 不是 RSA 公钥")

    ciphertext = public_key.encrypt(
        data,
        asym_padding.PKCS1v15(),
    )
    # 对标 Go：加密后做一次 base64 编码返回
    import base64
    return base64.b64encode(ciphertext)


def rsa_decrypt(base64_data: str | bytes, private_pem: str | bytes) -> bytes:
    """
    RSA 私钥解密（PKCS1v15），输入 base64 编码的密文。
    对标 Go RSADecrypt。
    """
    if isinstance(base64_data, str):
        base64_data = base64_data.encode("utf-8")
    if isinstance(private_pem, str):
        private_pem = private_pem.encode("utf-8")

    import base64
    ciphertext = base64.b64decode(base64_data)

    private_key = serialization.load_pem_private_key(private_pem, password=None)
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise TypeError("提供的 PEM 不是 RSA 私钥")

    return private_key.decrypt(
        ciphertext,
        asym_padding.PKCS1v15(),
    )


# ── AES-ECB ─────────────────────────────────────────────────

def aes_encrypt_ecb(plain: str | bytes, key: bytes | None = None) -> bytes:
    """
    AES-ECB 加密（对标 Go AesEncryptECB）。
    默认 key = b"0f90023fc9b9b8ff"。
    返回原始密文字节（上层自行 hex 编码）。
    """
    if key is None:
        key = b"0f90023fc9b9b8ff"
    if isinstance(plain, str):
        plain = plain.encode("utf-8")

    actual_key = _generate_key(key)
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes as cipher_modes

    padded = _pkcs7_pad(plain, AES_BLOCK_SIZE)
    # ECB 模式：IV 长度为 0
    cipher = Cipher(algorithms.AES(actual_key), cipher_modes.ECB())
    encryptor = cipher.encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def aes_decrypt_ecb(cipher_bytes: bytes, key: bytes | None = None) -> bytes:
    """
    AES-ECB 解密（对标 Go AesDecryptECB）。
    默认 key = b"0f90023fc9b9b8ff"。
    """
    if key is None:
        key = b"0f90023fc9b9b8ff"
    if len(cipher_bytes) % AES_BLOCK_SIZE != 0:
        return b""

    actual_key = _generate_key(key)
    cipher = Cipher(algorithms.AES(actual_key), modes.ECB())
    decryptor = cipher.decryptor()
    padded = decryptor.update(cipher_bytes) + decryptor.finalize()
    return _pkcs7_unpad(padded)


# ── AES-CFB ─────────────────────────────────────────────────

def _rand_hex(length: int) -> str:
    """生成长度为 length 的随机 hex 字符串（对标 Go getRndStr）"""
    return binascii.hexlify(os.urandom(length // 2)).decode("ascii")[:length]


def aes_encrypt_cfb(key: str, data: str) -> str | None:
    """
    AES-CFB 加密（对标 Go AesEncryptByCFB）。
    返回混合 hex 格式: encrypted[:16] + iv_hex(32) + encrypted[16:]
    """
    try:
        iv = _rand_hex(AES_BLOCK_SIZE)
        key_bytes = key.encode("utf-8")
        data_bytes = data.encode("utf-8")
        iv_bytes = iv.encode("utf-8")

        cipher = Cipher(algorithms.AES(key_bytes), modes.CFB(iv_bytes))
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(data_bytes) + encryptor.finalize()

        encrypted_hex = binascii.hexlify(ciphertext).decode("ascii")
        iv_hex = binascii.hexlify(iv_bytes).decode("ascii")
        return encrypted_hex[:16] + iv_hex + encrypted_hex[16:]
    except Exception as exc:
        logger.error("AES-CFB 加密失败: %s", exc)
        return None


def aes_decrypt_cfb(key: str, cipher_text: str) -> str | None:
    """
    AES-CFB 解密（对标 Go AesDecryptByCFB）。
    解析混合 hex 格式: encrypted[:16] + iv_hex(32) + encrypted[16:]
    """
    try:
        strlen = len(cipher_text)
        if strlen < 48:
            if strlen <= 32:
                logger.error("AES-CFB 密文长度错误")
                return None
            content = cipher_text[:strlen - 32]
            iv = cipher_text[strlen - 32:]
        else:
            content = cipher_text[:16] + cipher_text[48:]
            iv = cipher_text[16:48]

        key_bytes = key.encode("utf-8")
        content_bytes = binascii.unhexlify(content)
        iv_bytes = binascii.unhexlify(iv)

        cipher = Cipher(algorithms.AES(key_bytes), modes.CFB(iv_bytes))
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(content_bytes) + decryptor.finalize()
        return decrypted.decode("utf-8")
    except Exception as exc:
        logger.error("AES-CFB 解密失败: %s", exc)
        return None
