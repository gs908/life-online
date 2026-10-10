"""
密码哈希工具:scrypt(标准库 hashlib.scrypt,无需引入 bcrypt/passlib 依赖)。

- 参数 N=2^15, r=8, p=1, dklen=32(OWASP 认可区间;单次哈希内存约 32MB,耗时约 100ms,
  对登录场景可接受,对暴力破解者则是数量级更贵的成本)
- 存储格式: `scrypt$<N>$<r>$<p>$<salt_hex>$<hash_hex>`,自描述,后续调参可平滑升级
- verify 与 hash 用同一参数;哈希失败的异常统一上抛,不做"宽容放行"
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_SALT_BYTES = 16
# OpenSSL 对 scrypt 有默认内存上限(~32MB),N=2^15/r=8 恰好 32MB 会触顶,
# 需显式放宽到 64MB(仍远小于可承受的部署内存预算)。
_SCRYPT_MAXMEM = 64 * 1024 * 1024


def hash_password(password: str) -> str:
    """生成自描述的 scrypt 摘要串。"""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
        maxmem=_SCRYPT_MAXMEM,
    )
    return "$".join([
        "scrypt",
        str(_SCRYPT_N), str(_SCRYPT_R), str(_SCRYPT_P),
        salt.hex(), digest.hex(),
    ])


def verify_password(password: str, stored: str) -> bool:
    """常数时间比对;格式不认识一律返回 False(视为校验失败)。"""
    try:
        scheme, n, r, p, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(hash_hex)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p),
            dklen=len(expected),
            maxmem=_SCRYPT_MAXMEM,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)
