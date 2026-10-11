"""
密码哈希工具:scrypt(标准库 hashlib.scrypt,无需引入 bcrypt/passlib 依赖)。

- 参数 N=2^15, r=8, p=1, dklen=32(OWASP 认可区间;单次哈希内存约 32MB,耗时约 100ms,
  对登录场景可接受,对暴力破解者则是数量级更贵的成本)
- 存储格式: `scrypt$<N>$<r>$<p>$<salt_hex>$<hash_hex>`,自描述,后续调参可平滑升级
- verify 与 hash 用同一参数;哈希失败的异常统一上抛,不做"宽容放行"
- verify 的 maxmem 按存储串里的 n·r 动态计算(DEV-26):否则未来把 N 提到 2^17 时,
  旧参数哈希验证会因超限抛 ValueError 被吞成 False,存量用户全部静默登录失败
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

# verify 接受的参数边界:防存储串被篡改后触发巨型分配(动态 maxmem 的代价面)。
# 上界 N=2^20/r=32 单次约 4GB 内存,已远超登录场景一切合理调参,直接拒绝。
_N_BOUNDS = (2 ** 14, 2 ** 20)
_R_BOUNDS = (1, 32)
_P_BOUNDS = (1, 8)


def _is_power_of_two(v: int) -> bool:
    return v > 0 and v & (v - 1) == 0


def _scrypt_maxmem(n: int, r: int, p: int) -> int:
    """按参数计算 maxmem:需求约 128·N·r(V 数组)+ 少量工作缓冲,取 2 倍余量。

    当前参数(N=2^15, r=8)下即 64MB,与原 64MB 常量行为一致;N 提到 2^17 时
    自动放宽到 256MB,存量哈希验证不受影响。
    """
    return 2 * 128 * n * r + 256 * r * p


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
        maxmem=_scrypt_maxmem(_SCRYPT_N, _SCRYPT_R, _SCRYPT_P),
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
        n, r, p = int(n), int(r), int(p)
        if not (_is_power_of_two(n) and _N_BOUNDS[0] <= n <= _N_BOUNDS[1]):
            return False
        if not (_R_BOUNDS[0] <= r <= _R_BOUNDS[1] and _P_BOUNDS[0] <= p <= _P_BOUNDS[1]):
            return False
        expected = bytes.fromhex(hash_hex)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=n, r=r, p=p,
            dklen=len(expected),
            maxmem=_scrypt_maxmem(n, r, p),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)
