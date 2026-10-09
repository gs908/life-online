"""
对比目标 PostgreSQL 实际 schema 与当前 SQLAlchemy ``Base.metadata``。

用途(只读,不修改任何数据):
- 校验空库执行 ``alembic upgrade head`` 后,最终 schema 是否与模型一致;
- 校验现有 Supabase 实库是否与代码零差异(DEV-11 口径)。

比较维度:表集合、列(类型/可空/服务端默认)、索引(列/唯一性)、
外键(引用/ondelete)、唯一约束。以公共前缀 ``sys_`` / ``scn_`` 的项目表为界,
忽略 ``alembic_version`` 与数据库自带的非项目表。

用法:
    uv run python scripts/diff_pg_schema.py           # 有差异时退出码 1
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from sqlalchemy import UniqueConstraint, create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.schema import CreateTable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 导入所有模型,确保 Base.metadata 完整。
import app.models  # noqa: F401
from app.common.db.base import Base
from app.config import settings

PROJECT_TABLE_PREFIXES = ("sys_", "scn_")


def _build_engine() -> Engine:
    return create_engine(settings.database.url_sync, pool_pre_ping=True)


def _norm(value: str | None) -> str | None:
    """归一化服务端默认值 / where 子句文本,消除无关的空白与括号差异。"""
    if value is None:
        return None
    value = value.strip().lower()
    while value.startswith("(") and value.endswith(")"):
        value = value[1:-1].strip()
    return re.sub(r"\s+", "", value)


# PostgreSQL 标识符最长 63 字节,超长的约束/索引名会被数据库截断;
# create_all 与迁移链落库行为一致,比较时统一按 63 字符截断。
PG_NAME_LIMIT = 63


def _pg_name(name: str | None) -> str | None:
    return name[:PG_NAME_LIMIT] if name else name


def _server_default_text(server_default: object) -> str | None:
    """把 Column.server_default 统一编译为文本(text()/func.now()/字符串三种形态)。"""
    if server_default is None:
        return None
    arg = server_default.arg  # type: ignore[attr-defined]
    if isinstance(arg, str):
        return _norm(arg)
    if isinstance(getattr(arg, "text", None), str):  # sa.text(...)
        return _norm(arg.text)
    return _norm(str(arg.compile(dialect=postgresql.dialect())))  # func.now() 等


def _norm_type(type_text: str) -> str:
    """归一化类型文本:'TIMESTAMP WITHOUT TIME ZONE' 与反射出的 'TIMESTAMP' 等价。"""
    return re.sub(r"\s+without\s+time\s+zone", "", type_text.strip().lower(), flags=re.IGNORECASE)


def _index_wheres(conn: Connection) -> dict[str, str | None]:
    """从 pg_indexes.indexdef 提取部分索引的 WHERE 条件(反射 API 不返回该信息)。"""
    rows = conn.execute(
        text("select indexname, indexdef from pg_indexes where schemaname = 'public'")
    ).fetchall()
    wheres: dict[str, str | None] = {}
    for index_name, index_def in rows:
        match = re.search(r"\bwhere\b(.+)$", index_def, flags=re.IGNORECASE)
        wheres[index_name] = match.group(1) if match else None
    return wheres


def _collect_db(conn: Connection) -> dict[str, dict]:
    """从目标库 public schema 反射出结构摘要。"""
    inspector = inspect(conn)
    index_wheres = _index_wheres(conn)
    summary: dict[str, dict] = {}
    for table_name in sorted(inspector.get_table_names(schema="public")):
        if not table_name.startswith(PROJECT_TABLE_PREFIXES):
            continue
        columns = {
            col["name"]: {
                "type": _norm_type(str(col["type"])),
                "nullable": col["nullable"],
                "default": _norm(col.get("default")),
            }
            for col in inspector.get_columns(table_name, schema="public")
        }
        uniques = {
            _pg_name(uq["name"]): list(uq["column_names"])
            for uq in inspector.get_unique_constraints(table_name, schema="public")
            if uq.get("name")
        }
        indexes = {
            _pg_name(idx["name"]): {
                "columns": list(idx["column_names"]),
                "unique": idx["unique"],
                "where": _norm(index_wheres.get(idx["name"])),
            }
            # 唯一约束在 PG 里同样以唯一索引形式存在,反射会重复报出,跳过
            for idx in inspector.get_indexes(table_name, schema="public")
            if _pg_name(idx["name"]) not in uniques
        }
        foreign_keys = {
            _pg_name(fk["name"]): {
                "constrained": list(fk["constrained_columns"]),
                "referred_table": fk["referred_table"],
                "ondelete": fk.get("options", {}).get("ondelete"),
            }
            for fk in inspector.get_foreign_keys(table_name, schema="public")
            if fk.get("name")
        }
        summary[table_name] = {
            "columns": columns,
            "indexes": indexes,
            "foreign_keys": foreign_keys,
            "uniques": uniques,
        }
    return summary


def _collect_metadata() -> dict[str, dict]:
    """从 Base.metadata 生成与 _collect_db 同构的结构摘要。"""
    pg_dialect = postgresql.dialect()
    summary: dict[str, dict] = {}
    for table in sorted(Base.metadata.tables.values(), key=lambda t: t.name):
        columns = {
            col.name: {
                # 与反射结果同口径:用 PG 方言编译类型(DATETIME -> TIMESTAMP 等)
                "type": _norm_type(col.type.compile(dialect=pg_dialect)),
                "nullable": col.nullable,
                "default": _server_default_text(col.server_default),
            }
            for col in table.columns
        }
        # 约束落库时的最终名称以 PG 方言编译出的 DDL 为准:超过 63 字节的名称
        # SQLAlchemy 会做带摘要后缀的截断,直接截字符串无法还原真实落库名。
        ddl = str(CreateTable(table).compile(dialect=pg_dialect))
        ddl_fk_names = {
            tuple(c.strip() for c in cols.split(",")): name
            for name, cols in re.findall(r"CONSTRAINT (\S+) FOREIGN KEY ?\(([^)]+)\)", ddl)
        }
        ddl_uq_names = {
            tuple(c.strip() for c in cols.split(",")): name
            for name, cols in re.findall(r"CONSTRAINT (\S+) UNIQUE \(([^)]+)\)", ddl)
        }
        indexes = {
            _pg_name(idx.name): {
                "columns": [col.name for col in idx.columns],
                "unique": idx.unique,
                "where": _norm(
                    str(idx.dialect_options["postgresql"]["where"])
                    if "postgresql" in idx.dialect_options
                    and "where" in idx.dialect_options["postgresql"]
                    else None
                ),
            }
            for idx in table.indexes
        }
        foreign_keys = {
            ddl_fk_names.get(tuple(col.name for col in fk.columns), _pg_name(fk.name)): {
                "constrained": [col.name for col in fk.columns],
                "referred_table": fk.elements[0].column.table.name,
                "ondelete": fk.ondelete,
            }
            for fk in table.foreign_key_constraints
        }
        uniques = {
            ddl_uq_names.get(tuple(col.name for col in uq.columns), _pg_name(uq.name)): [
                col.name for col in uq.columns
            ]
            for uq in table.constraints
            if isinstance(uq, UniqueConstraint) and uq.name
        }
        summary[table.name] = {
            "columns": columns,
            "indexes": indexes,
            "foreign_keys": foreign_keys,
            "uniques": uniques,
        }
    return summary


def diff(db: dict[str, dict], meta: dict[str, dict]) -> list[str]:
    """比较两份摘要,返回人类可读的差异列表(空列表 = 完全一致)。"""
    problems: list[str] = []

    only_db = sorted(set(db) - set(meta))
    only_meta = sorted(set(meta) - set(db))
    if only_db:
        problems.append(f"仅存在于数据库的表: {only_db}")
    if only_meta:
        problems.append(f"仅存在于模型的表: {only_meta}")

    for table_name in sorted(set(db) & set(meta)):
        db_table, meta_table = db[table_name], meta[table_name]

        for col in sorted(set(db_table["columns"]) - set(meta_table["columns"])):
            problems.append(f"{table_name}.{col}: 仅存在于数据库")
        for col in sorted(set(meta_table["columns"]) - set(db_table["columns"])):
            problems.append(f"{table_name}.{col}: 仅存在于模型")
        for col in sorted(set(db_table["columns"]) & set(meta_table["columns"])):
            db_col, meta_col = db_table["columns"][col], meta_table["columns"][col]
            for key in ("type", "nullable", "default"):
                if db_col[key] != meta_col[key]:
                    problems.append(
                        f"{table_name}.{col}.{key}: 数据库={db_col[key]!r} 模型={meta_col[key]!r}"
                    )

        kind_labels = {"indexes": "index", "foreign_keys": "foreign_key", "uniques": "unique"}
        for kind, label in kind_labels.items():
            db_items, meta_items = db_table[kind], meta_table[kind]
            for name in sorted(set(db_items) - set(meta_items)):
                problems.append(f"{table_name} {label} {name}: 仅存在于数据库")
            for name in sorted(set(meta_items) - set(db_items)):
                problems.append(f"{table_name} {label} {name}: 仅存在于模型")
            for name in sorted(set(db_items) & set(meta_items)):
                if db_items[name] != meta_items[name]:
                    problems.append(
                        f"{table_name} {label} {name}: "
                        f"数据库={db_items[name]!r} 模型={meta_items[name]!r}"
                    )
    return problems


def main() -> None:
    # Windows 控制台默认 GBK,强制 UTF-8 避免中文输出乱码
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="对比数据库实际 schema 与 Base.metadata(只读)。")
    parser.parse_args()

    engine = _build_engine()
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("select current_database() as database, current_schema() as schema")
            ).mappings().one()
            print(f"目标数据库: database={row['database']}, schema={row['schema']}")
            db_summary = _collect_db(conn)
    finally:
        engine.dispose()

    meta_summary = _collect_metadata()
    print(f"数据库项目表: {len(db_summary)} 张;模型表: {len(meta_summary)} 张")

    problems = diff(db_summary, meta_summary)
    if problems:
        print(f"\n发现 {len(problems)} 处差异:")
        for problem in problems:
            print(f"  - {problem}")
        raise SystemExit(1)

    print("schema 与 Base.metadata 完全一致。")


if __name__ == "__main__":
    main()
