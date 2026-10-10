"""只读对比:当前代码 Base.metadata vs Supabase 实际库表(列级差异)。

用途(DEV-11):
- 在配置好 server/.env(指向 Supabase)后执行:
      uv run python scripts/diff_pg_schema.py
- 输出:
  1. alembic_version 实际值 vs 代码迁移链 head(由 versions/ 目录动态计算)
  2. 表级差异:代码期望有 / 库里多出
  3. 列级差异:缺失列 / 多余列 / 可空性不一致 / 类型不一致(方言编译后比对)

只读,不修改任何数据。类型比对将双方都编译到 PostgreSQL 方言后做字符串归一化,
仅提示性参考,不代表必须修改。
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection, Engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.models  # noqa: F401,E402
from app.common.db.base import Base  # noqa: E402
from app.config import settings  # noqa: E402

PG = postgresql.dialect()
PROJECT_TABLE_PREFIXES = ("sys_", "scn_")

MIGRATION_REVISION_RE = 'revision: str = '


def _expected_head() -> str:
    """从 alembic/versions 目录推导当前迁移链 head(不依赖数据库)。"""
    versions_dir = ROOT / "alembic" / "versions"
    revisions: dict[str, str | None] = {}
    for f in versions_dir.glob("*.py"):
        rev, down = None, None
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.startswith("revision:"):
                rev = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("down_revision:"):
                val = line.split("=", 1)[1].strip()
                down = None if "None" in val else val.split('"')[1] if '"' in val else val.split("'")[1]
        if rev:
            revisions[rev] = down
    referenced = {d for d in revisions.values() if d}
    heads = [r for r in revisions if r not in referenced]
    if len(heads) != 1:
        raise SystemExit(f"迁移链异常: 发现 {len(heads)} 个 head: {heads}")
    return heads[0]


def _norm_type(t: object) -> str:
    try:
        compiled = t.compile(PG)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        compiled = str(t)
    return " ".join(str(compiled).upper().split())


def _meta_columns(table_name: str) -> dict[str, tuple[str, bool]]:
    table = Base.metadata.tables[table_name]
    return {c.name: (_norm_type(c.type), c.nullable) for c in table.columns}


def _db_columns(conn: Connection, table_name: str) -> dict[str, tuple[str, bool]]:
    inspector = inspect(conn)
    return {
        c["name"]: (_norm_type(c["type"]), bool(c["nullable"]))
        for c in inspector.get_columns(table_name, schema="public")
    }


def diff(engine: Engine) -> int:
    problems = 0
    with engine.connect() as conn:
        row = conn.execute(text("select current_database() as db, version_num from alembic_version")).mappings().one_or_none()
        expected = _expected_head()
        if row is None:
            print("!! alembic_version 表不存在(数据库未按迁移链初始化)")
            problems += 1
        else:
            actual = row["version_num"]
            mark = "OK" if actual == expected else "MISMATCH"
            print(f"[alembic] 库中版本={actual} | 代码 head={expected} => {mark}")
            if actual != expected:
                problems += 1
                print("  提示: 若库为 sync_postgres_schema.py --apply 初始化,应被 stamp 为代码 head。")

        inspector = inspect(conn)
        db_tables = {
            t for t in inspector.get_table_names(schema="public")
            if t.startswith(PROJECT_TABLE_PREFIXES)
        }
        meta_tables = {
            t for t in Base.metadata.tables.keys()
            if t.startswith(PROJECT_TABLE_PREFIXES)
        }

        missing = sorted(meta_tables - db_tables)
        extra = sorted(db_tables - meta_tables)
        print(f"\n[tables] 代码期望 {len(meta_tables)} 张项目表, 库中 {len(db_tables)} 张")
        if missing:
            problems += len(missing)
            print("  库中缺失:")
            for t in missing:
                print(f"    - {t}")
        if extra:
            problems += len(extra)
            print("  库中多出(代码已移除或改名):")
            for t in extra:
                print(f"    - {t}")
        if not missing and not extra:
            print("  表级一致。")

        print("\n[columns] 逐表列级比对(仅比对双方都存在的表):")
        col_issues = 0
        for t in sorted(meta_tables & db_tables):
            meta_cols = _meta_columns(t)
            db_cols = _db_columns(conn, t)
            miss_c = sorted(set(meta_cols) - set(db_cols))
            extra_c = sorted(set(db_cols) - set(meta_cols))
            diffs = []
            for cname in sorted(set(meta_cols) & set(db_cols)):
                mt, mn = meta_cols[cname]
                dt, dn = db_cols[cname]
                if mt != dt:
                    diffs.append(f"{cname}: 类型 代码={mt} / 库={dt}")
                elif mn != dn:
                    diffs.append(f"{cname}: 可空 代码={mn} / 库={dn}")
            if miss_c or extra_c or diffs:
                col_issues += 1
                print(f"  {t}:")
                for c in miss_c:
                    print(f"    - 缺失列 {c} ({meta_cols[c][0]}, nullable={meta_cols[c][1]})")
                for c in extra_c:
                    print(f"    - 多余列 {c} ({db_cols[c][0]})")
                for d in diffs:
                    print(f"    ~ {d}")
        if col_issues == 0:
            print("  列级全部一致。")
        problems += col_issues

    print(f"\n结论: {'一致,无需同步。' if problems == 0 else f'共 {problems} 处差异/异常,见上方明细。'}")
    return 0 if problems == 0 else 1


def main() -> None:
    engine = create_engine(settings.database.url_sync, pool_pre_ping=True, connect_args={"connect_timeout": 10})
    try:
        raise SystemExit(diff(engine))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
