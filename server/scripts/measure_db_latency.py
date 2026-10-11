"""数据库链路延迟测量(DEV-29)。

区分三层延迟,定位"页面慢"是网络 RTT、连接建立(NullPool 逐操作新建连接)
还是查询本身:

1. TCP 握手:到 host:port 建立 TCP 连接的耗时分布 —— 纯网络 RTT 下界;
2. 复用连接 select 1:一条常驻连接上反复执行 `select 1` —— 查询本身的耗时;
3. 逐次新建连接 select 1:每轮 connect → select 1 → close —— 模拟 6543 事务
   pooler 下 NullPool 的逐操作开销(连接建立 + TLS + 认证 + 查询)。

读 `server/config.yaml` + 环境变量拼出的连接配置(与 `app/common/db/engine.py`
同源),测的就是应用实际走的链路。想对比 6543 / 5432,改 `.env` 里的
`DATABASE_PORT`(以及对应的 host)后重跑即可。

用法:
    cd server
    uv run python scripts/measure_db_latency.py                 # 默认 30 轮
    uv run python scripts/measure_db_latency.py --rounds 50 --skip-tcp

输出为汇总表(min / p50 / p90 / max / avg,毫秒),可直接粘贴进
`docs/11-数据库连接调优.md` 的实测数据表。
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path

import asyncpg

# 把 server/ 加入 path,确保脚本从任意 cwd 都能 import app(同 diff_pg_schema.py)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings


def _summary(name: str, values: list[float], extra: str = "") -> None:
    if not values:
        print(f"{name:<28} 无成功样本{extra}")
        return
    ordered = sorted(values)
    n = len(ordered)

    def pct(p: float) -> float:
        return ordered[min(n - 1, int(n * p))]

    print(
        f"{name:<28} n={n:<4} min={ordered[0]:7.1f}  p50={pct(0.50):7.1f}  "
        f"p90={pct(0.90):7.1f}  max={ordered[-1]:7.1f}  avg={statistics.mean(ordered):7.1f}{extra}"
    )


async def tcp_probe(host: str, port: int, rounds: int) -> None:
    """TCP 握手耗时(不发送任何数据,不需要数据库凭据)。"""
    values: list[float] = []
    fails = 0
    loop = asyncio.get_running_loop()
    for _ in range(rounds):
        t0 = time.perf_counter()
        try:
            _reader, writer = await asyncio.wait_for(
                loop.open_connection(host, port), timeout=5.0
            )
            values.append((time.perf_counter() - t0) * 1000)
            writer.close()
        except (TimeoutError, OSError):
            fails += 1
        await asyncio.sleep(0.05)
    _summary(f"TCP 握手 {host}:{port}", values, f"  (失败 {fails}/{rounds})" if fails else "")


async def _connect() -> asyncpg.Connection:
    db = settings.database
    return await asyncpg.connect(
        host=db.host,
        port=db.port,
        user=db.user,
        password=db.password,
        database=db.database,
        ssl=db.sslmode or None,
    )


async def persistent_select1(rounds: int) -> None:
    """常驻连接上反复 select 1:查询本身 + 单程 RTT。"""
    values: list[float] = []
    conn = await _connect()
    try:
        for _ in range(rounds):
            t0 = time.perf_counter()
            await conn.fetchval("select 1")
            values.append((time.perf_counter() - t0) * 1000)
            await asyncio.sleep(0.02)
    finally:
        await conn.close()
    _summary("复用连接 select 1", values)


async def fresh_conn_select1(rounds: int) -> None:
    """每轮新建连接(模拟 NullPool):连接建立 + TLS + 认证 + select 1。"""
    values: list[float] = []
    fails = 0
    for _ in range(rounds):
        t0 = time.perf_counter()
        try:
            conn = await _connect()
            try:
                await conn.fetchval("select 1")
            finally:
                await conn.close()
            values.append((time.perf_counter() - t0) * 1000)
        except (TimeoutError, OSError, asyncpg.PostgresError):
            fails += 1
        await asyncio.sleep(0.05)
    _summary("逐次新建连接 select 1", values, f"  (失败 {fails}/{rounds})" if fails else "")


async def main() -> None:
    parser = argparse.ArgumentParser(description="数据库链路延迟测量")
    parser.add_argument("--rounds", type=int, default=30, help="每项测量的轮数(默认 30)")
    parser.add_argument("--skip-tcp", action="store_true", help="跳过 TCP 握手探测")
    args = parser.parse_args()

    db = settings.database
    print(f"目标: {db.host}:{db.port}/{db.database}  (sslmode={db.sslmode})")
    print(f"轮数: {args.rounds}\n")

    if not args.skip_tcp:
        await tcp_probe(db.host, db.port, args.rounds)
    await persistent_select1(args.rounds)
    await fresh_conn_select1(args.rounds)


if __name__ == "__main__":
    asyncio.run(main())
