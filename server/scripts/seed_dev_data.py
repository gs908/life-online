"""
本地开发种子数据脚本。

用途:在配置好的(远程优先)数据库上创建一条最小可用的家庭数据链路,方便手动用
Postman / 前端 mock 替换阶段验证接口,而不必每次都从零手工建号。

用法:
    cd server
    uv run python scripts/seed_dev_data.py [suffix]

`suffix` 可选,默认 "dev",用于区分同一数据库中多次运行产生的家庭(名称里会带上该后缀)。

注意:
- 复用 `app.dev.seed.seed_basic_family`,与冒烟测试用的是同一套构造逻辑。
- 本脚本只创建数据,不做清理;需要清理时可直接在数据库里删除对应 `sys_family` 行
  (外键 `ondelete=CASCADE` 会级联删除下级数据),或调用
  `app.dev.seed.cleanup_family(db, family_id)`。
- 创建出的账号目前还不能直接登录:微信登录需要真实 openid,登录能力见 DEV-5
  (开发阶段非微信登录)。DEV-5 上线后可直接用这里创建的 `parent.id` / `child_account.id`
  配合 `auth_service.issue_token_pair` 签发 token。
"""
from __future__ import annotations

import asyncio
import sys

from app.common.db.engine import AsyncSessionLocal
from app.dev.seed import seed_basic_family


async def main(suffix: str) -> None:
    async with AsyncSessionLocal() as db:
        seeded = await seed_basic_family(db, suffix=suffix)

    print("种子数据创建完成:")
    print(f"  family_id       = {seeded.family.id}")
    print(f"  parent_account  = {seeded.parent.id} ({seeded.parent.name})")
    print(f"  child_account   = {seeded.child_account.id} ({seeded.child_account.name})")
    print(f"  child_profile   = {seeded.child.id}")
    print(f"  season_id       = {seeded.season.id}")
    print(f"  task_template   = {seeded.task_template.id}")
    print(f"  task_instance   = {seeded.task_instance.id}")


if __name__ == "__main__":
    suffix = sys.argv[1] if len(sys.argv) > 1 else "dev"
    asyncio.run(main(suffix))
