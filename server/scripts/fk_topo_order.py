"""
按外键依赖输出表的拓扑顺序,供数据迁移 / 批量导入使用。

用途(只读,不连数据库,只读 ``Base.metadata``):
- 正向顺序(默认):被引用表在前 → **INSERT / COPY** 的安全顺序,
  immediate FK 约束下逐表写入不会中途报外键违规;
- 逆向顺序(``--reverse``):引用表在前 → **DELETE / TRUNCATE**(不带 CASCADE)的
  安全顺序,先删子表再删父表,不会因残留引用而失败;
- ``--layers``:分层视图,同层表互不依赖,可并行导入。

**循环引用的处理**:当前模型存在一个真实的表间环
(``sys_child`` → ``scn_onboarding_step`` → ``scn_task_template`` → ``sys_child``,
即 ``sys_child`` 上两处 ``use_alter=True`` 外键对应的环)。环上的外键列全部
可空(``SET NULL``),脚本自动选出"回填边":导入时这些列先置 NULL,其余表按
输出的拓扑顺序导入,全部完成后再回填这些列。回填边优先取 ``use_alter=True``
的外键——DDL 建表顺序的破环边同时充当数据导入的破环边,语义一致。
若未来出现**不可空**的环(置 NULL 走不通),脚本会明确报错并提示改用
deferrable 约束——裁决依据见 docs/12-外键与迁移策略.md。

背景:项目保留数据库级 FK,批量导入不使用 ``session_replication_role = replica``
(Supabase postgres 角色无权限)也不引入 deferrable 约束,统一走拓扑顺序。

用法:
    cd server
    uv run python scripts/fk_topo_order.py            # 正向顺序(导入)+ 回填提示
    uv run python scripts/fk_topo_order.py --reverse  # 逆向顺序(删除)
    uv run python scripts/fk_topo_order.py --layers   # 分层视图(同层可并行)

说明:
- 自引用外键(如 ``scn_onboarding_step.unlocks_after``)不构成顺序约束,忽略;
- 脚本不连库、不读配置值,只依赖模型定义,可随时在 CI 中运行。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import ForeignKeyConstraint
from sqlalchemy.sql.schema import MetaData, Table

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 本脚本不连库,但导入模型链路会经过 app.config(必填项 jwt.secret 无默认值,
# 缺失会在 import 时直接报错)。与 tests/conftest.py 同一处理:只 setdefault
# 占位值,已配置真实 .env / 环境变量的环境不受影响,且本脚本不使用任何配置值。
os.environ.setdefault("JWT_SECRET", "topo-order-no-db-usage")

# 只导入模型,不连数据库,只读 Base.metadata。
import app.models  # noqa: F401,E402
from app.common.db.base import Base  # noqa: E402

# (子表, 列, 父表);额外用 use_alter 标记 DDL 破环边
Edge = tuple[str, str, str]


def _fk_edges(tables: dict[str, Table]) -> dict[Edge, bool]:
    """全部外键边 → 是否 use_alter(DDL 破环边)。自引用忽略。"""
    edges: dict[Edge, bool] = {}
    for table in tables.values():
        for constraint in table.constraints:
            if not isinstance(constraint, ForeignKeyConstraint):
                continue
            for element in constraint.elements:
                referred = element.column.table
                if referred is not table:
                    edges[(table.name, element.parent.name, referred.name)] = bool(element.use_alter)
    return edges


def _tarjan_sccs(nodes: list[str], edges: dict[Edge, bool]) -> list[list[str]]:
    """Tarjan 强连通分量;返回按完成序的列表(分量内节点按名排序)。"""
    index_counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    result: list[list[str]] = []

    succ: dict[str, list[str]] = {n: [] for n in nodes}
    for (child, _col, parent), _ in edges.items():
        if child in succ and parent in succ:
            succ[child].append(parent)

    def strongconnect(v: str) -> None:
        # 迭代版避免深递归(本模型仅 27 表,防御性写法)
        work = [(v, iter(succ[v]))]
        index[v] = lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        while work:
            node, it = work[-1]
            advanced = False
            for w in it:
                if w not in index:
                    index[w] = lowlink[w] = index_counter[0]
                    index_counter[0] += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(succ[w])))
                    advanced = True
                    break
                elif w in on_stack:
                    lowlink[node] = min(lowlink[node], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                parent_node = work[-1][0]
                lowlink[parent_node] = min(lowlink[parent_node], lowlink[node])
            if lowlink[node] == index[node]:
                component: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    component.append(w)
                    if w == node:
                        break
                result.append(sorted(component))

    for v in nodes:
        if v not in index:
            strongconnect(v)
    return result


def _break_scc(scc: list[str], edges: dict[Edge, bool], metadata: MetaData) -> list[Edge]:
    """在强连通分量内选"回填边":优先 use_alter 边,其次字典序第一条可空边。

    每移除一条边就重算剩余子图的强连通性,直到分量被拆成无环子图。
    """
    members = set(scc)
    intra = {e: ua for e, ua in edges.items() if e[0] in members and e[2] in members}
    sub_nodes = scc
    chosen: list[Edge] = []
    while True:
        sub_sccs = [c for c in _tarjan_sccs(sub_nodes, intra) if len(c) > 1]
        if not sub_sccs:
            return chosen
        # 找仍成环的分量,继续破环
        cyclic_members = set(sub_sccs[0])
        candidates = sorted(
            e for e, _ in intra.items()
            if e[0] in cyclic_members and e[2] in cyclic_members
        )
        use_alter_edges = [e for e in candidates if intra[e]]
        nullable_edges = [
            e for e in candidates
            if metadata.tables[e[0]].columns[e[1]].nullable
        ]
        pick_from = use_alter_edges or nullable_edges
        if not pick_from:
            stuck = ", ".join(sorted(cyclic_members))
            raise ValueError(
                "外键依赖存在**不可空**的循环引用,置 NULL 回填方案走不通,"
                "需要 deferrable 约束或拆环后重试。涉及表: " + stuck
            )
        edge = pick_from[0]
        chosen.append(edge)
        del intra[edge]
        sub_nodes = [n for n in sub_nodes if n in intra or True]  # 节点集不变


def topo_sort(metadata: MetaData) -> tuple[list[str], list[Edge]]:
    """返回(拓扑顺序, 回填边列表)。

    顺序保证:除回填边外,每张表的所有外键父表都排在该表之前;
    回填边对应的列导入时置 NULL,全部导入完成后回填(见脚本头部说明)。
    """
    tables = dict(metadata.tables)
    edges = _fk_edges(tables)
    sccs = _tarjan_sccs(sorted(tables), edges)

    backfill: list[Edge] = []
    for scc in sccs:
        if len(scc) > 1:
            backfill.extend(_break_scc(scc, edges, metadata))
    for edge in backfill:
        edges.pop(edge, None)

    # 分量间 + 分量内统一做一次 Kahn(破环后整图必为 DAG)
    remaining = set(tables)
    deps: dict[str, set[str]] = {n: set() for n in remaining}
    for (child, _col, parent), _ in edges.items():
        if child in remaining and parent in remaining:
            deps[child].add(parent)
    order: list[str] = []
    while remaining:
        ready = sorted(n for n in remaining if not deps[n])
        if not ready:
            stuck = ", ".join(sorted(remaining))
            raise ValueError(f"拓扑排序失败(存在未处理的循环引用): {stuck}")
        order.extend(ready)
        remaining.difference_update(ready)
        for d in deps.values():
            d.difference_update(ready)
    return order, backfill


def _format_layers(order: list[str], backfill: list[Edge], edges: dict[Edge, bool]) -> str:
    """分层视图:第 n 层的表,其(未被回填的)父表都在更早层。"""
    depth: dict[str, int] = {}
    for name in order:
        parents = {p for (c, _col, p) in edges if c == name and (c, _col, p) not in set(backfill)}
        depth[name] = 1 + max((depth[p] for p in parents if p in depth), default=-1)
    max_depth = max(depth.values())
    lines = []
    for i in range(max_depth + 1):
        layer = [n for n in order if depth[n] == i]
        if layer:
            lines.append(f"第 {i + 1} 层: " + ", ".join(layer))
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="按外键依赖输出表拓扑顺序(导入正向,删除逆向)。"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--reverse", action="store_true", help="逆向顺序(引用表在前,用于 DELETE/TRUNCATE)"
    )
    group.add_argument(
        "--layers", action="store_true", help="分层视图(同层表互不依赖,可并行导入)"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    order, backfill = topo_sort(Base.metadata)
    edges = _fk_edges(dict(Base.metadata.tables))

    print(f"# 共 {len(order)} 张表;循环引用回填边 {len(backfill)} 处")
    if args.layers:
        print(_format_layers(order, backfill, edges))
    elif args.reverse:
        for name in reversed(order):
            print(name)
    else:
        for name in order:
            print(name)
        if backfill:
            print()
            print("# 循环引用回填边(导入时先置 NULL,全部导入完成后回填):")
            for child, col, parent in backfill:
                print(f"#   UPDATE {child} SET {col} = ... (来自源库 {child}.{col},引用 {parent})")


if __name__ == "__main__":
    main()
