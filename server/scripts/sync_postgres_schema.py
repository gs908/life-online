"""
安全同步当前 SQLAlchemy metadata 到 PostgreSQL / Supabase。

用途:
- `--check`: 只读检查目标库是否已有项目表。
- `--apply`: 仅当目标库没有项目表时,创建当前表结构并写入 Alembic head。

注意:该脚本用于新的 PostgreSQL/Supabase 空库初始化,避免旧 Alembic 初始迁移
`Base.metadata.create_all()` 与后续迁移重复执行的问题。不会删除或覆盖已有表。
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 导入所有模型,确保 Base.metadata 完整。
import app.models  # noqa: F401,E402
from app.common.db.base import Base  # noqa: E402
from app.config import settings  # noqa: E402

ALEMBIC_HEAD = "8aa7c7e1f4d1"
PROJECT_TABLE_PREFIXES = ("sys_", "scn_")


def _build_engine() -> Engine:
    return create_engine(settings.database.url_sync, pool_pre_ping=True)


def _project_tables(table_names: Sequence[str]) -> list[str]:
    return sorted(
        name
        for name in table_names
        if name == "alembic_version" or name.startswith(PROJECT_TABLE_PREFIXES)
    )


def _metadata_table_names() -> list[str]:
    return sorted(Base.metadata.tables.keys())


def _print_target_info(conn: Connection) -> None:
    row = conn.execute(
        text(
            "select current_database() as database, "
            "current_schema() as schema, "
            "current_user as user"
        )
    ).mappings().one()
    print(
        "目标数据库: "
        f"database={row['database']}, schema={row['schema']}, user={row['user']}"
    )


def check(engine: Engine) -> list[str]:
    with engine.connect() as conn:
        _print_target_info(conn)
        inspector = inspect(conn)
        existing_tables = inspector.get_table_names(schema="public")
        project_tables = _project_tables(existing_tables)

        print(f"当前 metadata 表数量: {len(_metadata_table_names())}")
        print(f"public schema 已有表数量: {len(existing_tables)}")
        if project_tables:
            print("发现已有项目相关表:")
            for table_name in project_tables:
                print(f"  - {table_name}")
        else:
            print("未发现 sys_* / scn_* / alembic_version 项目表。")
        return project_tables


def apply(engine: Engine) -> None:
    with engine.begin() as conn:
        _print_target_info(conn)
        inspector = inspect(conn)
        project_tables = _project_tables(inspector.get_table_names(schema="public"))
        if project_tables:
            print("目标库已存在项目相关表,为避免覆盖或破坏数据,本次同步已中止:")
            for table_name in project_tables:
                print(f"  - {table_name}")
            raise SystemExit(2)

        print("开始创建当前 SQLAlchemy metadata 表结构...")
        Base.metadata.create_all(bind=conn, checkfirst=False)

        print(f"写入 Alembic 版本: {ALEMBIC_HEAD}")
        conn.execute(
            text(
                "create table if not exists alembic_version "
                "(version_num varchar(32) not null primary key)"
            )
        )
        conn.execute(text("delete from alembic_version"))
        conn.execute(
            text("insert into alembic_version (version_num) values (:version_num)"),
            {"version_num": ALEMBIC_HEAD},
        )

    print("PostgreSQL/Supabase 表结构同步完成。")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="安全同步当前 SQLAlchemy metadata 到 PostgreSQL/Supabase。"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="只读检查目标库状态")
    mode.add_argument("--apply", action="store_true", help="空库时创建表结构并标记 Alembic head")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    engine = _build_engine()
    try:
        if args.check:
            check(engine)
        elif args.apply:
            apply(engine)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
