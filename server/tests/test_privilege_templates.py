"""权益模板 CRUD 冒烟测试(DEV-67):家庭级模板增删改 + 系统模板保护 + 家庭隔离。

覆盖:
- 家长可完成"新建 -> 编辑 -> 重新 GET 反映变更 -> 删除 -> 重新 GET 消失"的闭环
  (即"刷新即消失"问题的持久化验证)。
- `is_system=True` 的系统模板改/删一律 403;系统模板仍可被家庭 GET 到。
- 别的家庭的模板改/删返回 404(不泄露其是否存在),且不出现在本家庭 GET 结果里。
- 孩子角色调用写接口(新增/编辑/删除)返回 403。
- PATCH 显式传 `null` 落到非空列时返回 422(而不是 IntegrityError 兜底成 500)。
- 删除模板时解锁记录被级联清理、历史使用记录保留且 `privilege_template_id` 置空。

需要可连接的数据库(远程优先),不可达时该模块内用例会被 `db_ready` fixture 跳过。
"""
from __future__ import annotations

from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.timeutil import utcnow
from app.dev.seed import SeededFamily, cleanup_family, seed_basic_family
from app.models.scn_privilege_template import ScnPrivilegeTemplate
from app.models.scn_privilege_unlock import ScnPrivilegeUnlock
from app.models.scn_privilege_use import ScnPrivilegeUse
from app.services import auth_service

pytestmark = pytest.mark.db


def _auth_headers(account) -> dict[str, str]:
    tokens = auth_service.issue_token_pair(account)
    return {"Authorization": f"Bearer {tokens.access_token}"}


@pytest_asyncio.fixture
async def other_family(db_session: AsyncSession) -> AsyncIterator[SeededFamily]:
    """第二个家庭,专门用于跨家庭隔离断言。"""
    seeded = await seed_basic_family(db_session, suffix="priv-other")
    try:
        yield seeded
    finally:
        await cleanup_family(db_session, seeded.family.id)


async def _create_system_template(db: AsyncSession, *, level: int = 1) -> ScnPrivilegeTemplate:
    """直接落库一条系统模板(family_id=None, is_system=True),供保护断言使用。"""
    template = ScnPrivilegeTemplate(
        family_id=None,
        level_required=level,
        title="系统特权",
        description="平台预置,不可改",
        icon="🏆",
        is_system=True,
        is_active=True,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@pytest_asyncio.fixture
async def system_template(db_session: AsyncSession) -> AsyncIterator[ScnPrivilegeTemplate]:
    """一条系统模板,用例结束后清理(它不挂在家庭下,不会被 cleanup_family 带走)。"""
    template = await _create_system_template(db_session)
    try:
        yield template
    finally:
        await db_session.delete(await db_session.get(ScnPrivilegeTemplate, template.id))
        await db_session.commit()


async def test_parent_template_crud_persists(
    api_client: AsyncClient, seeded_family: SeededFamily
) -> None:
    headers = _auth_headers(seeded_family.parent)

    create_resp = await api_client.post(
        "/api/v1/scn/privileges/templates",
        json={
            "level_required": 3,
            "title": "周末电影",
            "description": "可自选一部电影",
            "icon": "🎬",
        },
        headers=headers,
    )
    assert create_resp.status_code == 200
    created = create_resp.json()["data"]
    assert created["title"] == "周末电影"
    assert created["is_system"] is False
    assert created["family_id"] == seeded_family.family.id
    template_id = created["id"]

    # 重新 GET 模板树应能看到新建的模板(持久化)。
    list_resp = await api_client.get("/api/v1/scn/privileges/templates", headers=headers)
    assert list_resp.status_code == 200
    assert template_id in {t["id"] for t in list_resp.json()["data"]}

    patch_resp = await api_client.patch(
        f"/api/v1/scn/privileges/templates/{template_id}",
        json={"title": "周末电影-改", "level_required": 4},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()["data"]
    assert patched["title"] == "周末电影-改"
    assert patched["level_required"] == 4

    # 重新 GET 反映编辑后的值。
    list_after_patch = await api_client.get(
        "/api/v1/scn/privileges/templates", headers=headers
    )
    row = next(t for t in list_after_patch.json()["data"] if t["id"] == template_id)
    assert row["title"] == "周末电影-改"

    delete_resp = await api_client.delete(
        f"/api/v1/scn/privileges/templates/{template_id}", headers=headers
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["data"]["deleted"] is True

    list_after_delete = await api_client.get(
        "/api/v1/scn/privileges/templates", headers=headers
    )
    assert template_id not in {t["id"] for t in list_after_delete.json()["data"]}


async def test_system_template_edit_and_delete_rejected(
    api_client: AsyncClient, seeded_family: SeededFamily, system_template: ScnPrivilegeTemplate
) -> None:
    headers = _auth_headers(seeded_family.parent)

    patch_resp = await api_client.patch(
        f"/api/v1/scn/privileges/templates/{system_template.id}",
        json={"title": "越权改名"},
        headers=headers,
    )
    assert patch_resp.status_code == 403

    delete_resp = await api_client.delete(
        f"/api/v1/scn/privileges/templates/{system_template.id}", headers=headers
    )
    assert delete_resp.status_code == 403

    # 拒绝后系统模板仍在(操作无副作用),且家庭可见。
    list_resp = await api_client.get("/api/v1/scn/privileges/templates", headers=headers)
    assert system_template.id in {t["id"] for t in list_resp.json()["data"]}


async def test_template_cross_family_isolation(
    api_client: AsyncClient, seeded_family: SeededFamily, other_family: SeededFamily
) -> None:
    headers = _auth_headers(seeded_family.parent)

    # 在另一家庭里建一条模板。
    other_headers = _auth_headers(other_family.parent)
    created = (
        await api_client.post(
            "/api/v1/scn/privileges/templates",
            json={"level_required": 2, "title": "别人家的特权"},
            headers=other_headers,
        )
    ).json()["data"]
    other_id = created["id"]

    # 本家庭既看不到,也改不了、删不了(404 不泄露存在性)。
    list_resp = await api_client.get("/api/v1/scn/privileges/templates", headers=headers)
    assert other_id not in {t["id"] for t in list_resp.json()["data"]}

    patch_resp = await api_client.patch(
        f"/api/v1/scn/privileges/templates/{other_id}",
        json={"title": "越权改名"},
        headers=headers,
    )
    assert patch_resp.status_code == 404

    delete_resp = await api_client.delete(
        f"/api/v1/scn/privileges/templates/{other_id}", headers=headers
    )
    assert delete_resp.status_code == 404

    # 另一家庭仍能改到自己的模板(未被误伤)。
    still_there = await api_client.patch(
        f"/api/v1/scn/privileges/templates/{other_id}",
        json={"title": "别人家的特权-改"},
        headers=other_headers,
    )
    assert still_there.status_code == 200


async def test_child_cannot_write_templates(
    api_client: AsyncClient, seeded_family: SeededFamily
) -> None:
    headers = _auth_headers(seeded_family.child_account)

    create_resp = await api_client.post(
        "/api/v1/scn/privileges/templates",
        json={"level_required": 1, "title": "孩子创建"},
        headers=headers,
    )
    assert create_resp.status_code == 403

    patch_resp = await api_client.patch(
        "/api/v1/scn/privileges/templates/does-not-matter",
        json={"title": "孩子改名"},
        headers=headers,
    )
    assert patch_resp.status_code == 403

    delete_resp = await api_client.delete(
        "/api/v1/scn/privileges/templates/does-not-matter", headers=headers
    )
    assert delete_resp.status_code == 403

    # 只读接口对孩子角色开放。
    list_resp = await api_client.get("/api/v1/scn/privileges/templates", headers=headers)
    assert list_resp.status_code == 200


async def test_template_season_must_belong_to_family(
    api_client: AsyncClient, seeded_family: SeededFamily, other_family: SeededFamily
) -> None:
    """模板可选关联的"来源赛季"须属于本家庭,否则 404(而不是 FK 违约兜成 500)。"""
    headers = _auth_headers(seeded_family.parent)

    cross_family = await api_client.post(
        "/api/v1/scn/privileges/templates",
        json={
            "level_required": 1,
            "title": "挂到别人赛季",
            "season_id": other_family.season.id,
        },
        headers=headers,
    )
    assert cross_family.status_code == 404

    unknown = await api_client.post(
        "/api/v1/scn/privileges/templates",
        json={
            "level_required": 1,
            "title": "不存在的赛季",
            "season_id": "00000000-0000-0000-0000-000000000000",
        },
        headers=headers,
    )
    assert unknown.status_code == 404

    ok_resp = await api_client.post(
        "/api/v1/scn/privileges/templates",
        json={
            "level_required": 1,
            "title": "本家庭赛季",
            "season_id": seeded_family.season.id,
        },
        headers=headers,
    )
    assert ok_resp.status_code == 200
    assert ok_resp.json()["data"]["season_id"] == seeded_family.season.id


async def test_patch_explicit_null_rejected_422(
    api_client: AsyncClient, seeded_family: SeededFamily
) -> None:
    """显式传 null 落到非空列应得 422,而不是写库违约后兜底成 500。

    若服务层直接 `setattr(None)`,会在 commit 时触发 IntegrityError(列
    `nullable=False`)并被全局 handler 兜成 500 —— 用户可控输入不该产生 500。
    """
    headers = _auth_headers(seeded_family.parent)
    created = (
        await api_client.post(
            "/api/v1/scn/privileges/templates",
            json={"level_required": 2, "title": "空值校验"},
            headers=headers,
        )
    ).json()["data"]

    null_patch = await api_client.patch(
        f"/api/v1/scn/privileges/templates/{created['id']}",
        json={"title": None},
        headers=headers,
    )
    assert null_patch.status_code == 422

    # 拒绝后模板未被改动(整个操作无副作用)。
    list_resp = await api_client.get("/api/v1/scn/privileges/templates", headers=headers)
    row = next(t for t in list_resp.json()["data"] if t["id"] == created["id"])
    assert row["title"] == "空值校验"

    # `season_id` 可空,显式 null 表示"清空来源赛季",应被接受。
    clear_season = await api_client.patch(
        f"/api/v1/scn/privileges/templates/{created['id']}",
        json={"season_id": None},
        headers=headers,
    )
    assert clear_season.status_code == 200
    assert clear_season.json()["data"]["season_id"] is None


async def test_delete_cascades_unlocks_and_keeps_uses(
    api_client: AsyncClient, seeded_family: SeededFamily, db_session: AsyncSession
) -> None:
    """删模板:解锁记录随 FK CASCADE 清理,使用记录保留且 `privilege_template_id` SET NULL。

    现有用例删的都是"从未被解锁过"的模板,走不到有 unlock/use 记录的路径 ——
    这里补上,锁住删除的级联契约。
    """
    headers = _auth_headers(seeded_family.parent)
    created = (
        await api_client.post(
            "/api/v1/scn/privileges/templates",
            json={"level_required": 1, "title": "有记录的模板"},
            headers=headers,
        )
    ).json()["data"]
    template_id = created["id"]

    unlock = ScnPrivilegeUnlock(
        family_id=seeded_family.family.id,
        child_id=seeded_family.child.id,
        season_id=seeded_family.season.id,
        privilege_template_id=template_id,
    )
    use = ScnPrivilegeUse(
        family_id=seeded_family.family.id,
        child_id=seeded_family.child.id,
        season_id=seeded_family.season.id,
        privilege_template_id=template_id,
        privilege_title="有记录的模板",
        used_at=utcnow(),
    )
    db_session.add_all([unlock, use])
    await db_session.commit()
    unlock_id, use_id = unlock.id, use.id

    delete_resp = await api_client.delete(
        f"/api/v1/scn/privileges/templates/{template_id}", headers=headers
    )
    assert delete_resp.status_code == 200

    # 删除在另一会话完成,本会话身份映射仍持有旧对象 —— 直接查列(不取实体),
    # 从库拿真实状态,既不触发懒加载,也不会被身份映射的缓存值骗过。
    unlock_row = (
        await db_session.execute(
            select(ScnPrivilegeUnlock.id).where(ScnPrivilegeUnlock.id == unlock_id)
        )
    ).first()
    assert unlock_row is None, "解锁记录应随模板删除被级联清理"

    use_row = (
        await db_session.execute(
            select(ScnPrivilegeUse.id, ScnPrivilegeUse.privilege_template_id).where(
                ScnPrivilegeUse.id == use_id
            )
        )
    ).first()
    assert use_row is not None, "历史使用记录应保留"
    assert use_row[1] is None, "模板被删后使用记录应解绑(SET NULL)"