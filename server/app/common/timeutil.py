"""统一时区工具。

时区规范(见 server/README.md「时间与时区规范」):
- 数据库时间列统一 `timestamptz`(TIMESTAMPTZ,存 UTC);
- 应用层一律使用**带时区**的 datetime(`utcnow()` / `now_bj()`),禁止裸 `datetime.utcnow()`;
- 与"自然日"相关的业务逻辑(每日限领、每日重置、任务过期自然日等)锚定北京时区
  (Asia/Shanghai,UTC+8,无夏令时),不依赖服务器本地时区;
- 展示层需要北京时间时用 `to_bj()` 转换。
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

# 业务时区:北京(UTC+8,无夏令时,固定偏移)。
BJ_TZ = ZoneInfo("Asia/Shanghai")


def utcnow() -> datetime:
    """当前时刻,带时区(UTC)。写入数据库/参与比较统一用它。"""
    return datetime.now(timezone.utc)


def now_bj() -> datetime:
    """当前北京时刻,带时区。"""
    return datetime.now(BJ_TZ)


def to_bj(dt: datetime) -> datetime:
    """任意带时区 datetime 转为北京时区展示。"""
    return dt.astimezone(BJ_TZ)


def today_bj() -> date:
    """北京时区的"今天"。所有自然日边界(每日限领/重置)用它。"""
    return now_bj().date()
