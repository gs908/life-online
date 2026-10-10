"""
网页端账号密码登录测试(DEV-22)。

覆盖:
- 注册(邀请码) → 登录 → 携带 token 调用受保护接口的完整链路(验收主路径)
- 登录失败语义:用户不存在与密码错误返回同一 401(防用户名枚举)
- 登录失败限流:窗口内连续失败超限后返回 429
- 用户名大小写不敏感;重复用户名注册 409(邀请码不被消费);弱密码/非法用户名 422
- 修改密码:旧密码校验、改密后新旧密码生效性、首次设置必须带 username
- 通道开关关闭时 503(dev-login 的 DEV_LOGIN_ENABLED 门禁不受影响,见 test_dev_login_smoke.py)

需要数据库的用例标 `@pytest.mark.db` + `db_ready`;参数校验/开关类用例不依赖数据库,
任何环境都会执行。测试数据经 family_service 正常链路创建,结束用 cleanup_family
级联清理,不在远程数据库留脏数据。
"""
from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.dev.seed import cleanup_family
from app.main import app
from app.models.enums import InviteRole, UserRole
from app.models.sys_account import SysAccount
from app.services import family_service, password_service


def _fake_settings(
    *, enabled: bool = True, max_attempts: int = 5, window_minutes: int = 15
) -> SimpleNamespace:
    return SimpleNamespace(
        auth=SimpleNamespace(
            password_login_enabled=enabled,
            login_max_attempts=max_attempts,
            login_window_minutes=window_minutes,
        )
    )


@pytest_asyncio.fixture
async def auth_cfg() -> AsyncIterator[dict]:
    """覆盖 get_settings 提供收紧的限流参数,并重置进程内限流计数器。"""
    cfg = {"max_attempts": 3, "window_minutes": 15}
    app.dependency_overrides[get_settings] = lambda: _fake_settings(enabled=True, **cfg)
    password_service._throttle = password_service._LoginThrottle()
    try:
        yield cfg
    finally:
        app.dependency_overrides.pop(get_settings, None)
        password_service._throttle = password_service._LoginThrottle()


@pytest_asyncio.fixture
async def password_login_disabled() -> AsyncIterator[None]:
    app.dependency_overrides[get_settings] = lambda: _fake_settings(enabled=False)
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_settings, None)


async def _new_family_with_invite(
    db_session: AsyncSession, *, role: InviteRole = InviteRole.ADVENTURER
) -> tuple[str, str]:
    """建家庭 + 一张邀请码,返回 (family_id, code)。"""
    suffix = secrets.token_hex(4)
    family = await family_service.create_family(
        db_session, name=f"pw-家庭-{suffix}", owner_name=f"pw-家长-{suffix}"
    )
    invite = await family_service.create_invite(
        db_session, family_id=family.id, role=role, created_by=family.owner_id
    )
    return family.id, invite.code


# ---- 参数校验 / 开关(不依赖数据库,始终执行) ----


async def test_login_rejects_weak_password(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/api/v1/sys/auth/password/login",
        json={"username": "alice", "password": "short"},
    )
    assert resp.status_code == 422


async def test_login_rejects_bad_username(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/api/v1/sys/auth/password/login",
        json={"username": "非法用户名", "password": "good-password"},
    )
    assert resp.status_code == 422


async def test_login_unavailable_when_disabled(
    api_client: AsyncClient, password_login_disabled: None
) -> None:
    resp = await api_client.post(
        "/api/v1/sys/auth/password/login",
        json={"username": "alice", "password": "good-password"},
    )
    assert resp.status_code == 503
    assert resp.json()["data"]["error_code"] == "service_unavailable"


async def test_register_unavailable_when_disabled(
    api_client: AsyncClient, password_login_disabled: None
) -> None:
    resp = await api_client.post(
        "/api/v1/sys/auth/password/register",
        json={"code": "ANYCODE", "username": "alice", "password": "good-password"},
    )
    assert resp.status_code == 503


# ---- 完整链路(需要数据库) ----


@pytest.mark.db
async def test_register_login_and_call_protected_api(
    api_client: AsyncClient, db_session: AsyncSession, auth_cfg: dict, db_ready: bool
) -> None:
    """注册(邀请码) → 登录 → /sys/auth/me 全链路;这是 DEV-22 的验收主路径。"""
    family_id, code = await _new_family_with_invite(db_session)

    username = f"child_{secrets.token_hex(4)}"
    password = "sup3r-secret!"
    reg = await api_client.post(
        "/api/v1/sys/auth/password/register",
        json={"code": code, "username": username, "password": password},
    )
    assert reg.status_code == 200, reg.text
    tokens = reg.json()["data"]
    assert tokens["access_token"] and tokens["refresh_token"]

    me = await api_client.get(
        "/api/v1/sys/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    data = me.json()["data"]
    assert data["role"] == UserRole.ADVENTURER.value
    assert data["family_id"] == family_id

    # 登录(用户名大小写不敏感)也能拿到 token
    login = await api_client.post(
        "/api/v1/sys/auth/password/login",
        json={"username": username.upper(), "password": password},
    )
    assert login.status_code == 200, login.text
    assert login.json()["data"]["access_token"]

    await cleanup_family(db_session, family_id)


@pytest.mark.db
async def test_login_failure_is_uniform_and_rate_limited(
    api_client: AsyncClient, db_session: AsyncSession, auth_cfg: dict, db_ready: bool
) -> None:
    """用户不存在/密码错误同返回 401;超限后 429,且限流只影响该用户名。"""
    username = f"ghost_{secrets.token_hex(4)}"
    body = {"username": username, "password": "whatever-123"}

    # 用户不存在:401,与密码错误不可区分
    first = await api_client.post("/api/v1/sys/auth/password/login", json=body)
    assert first.status_code == 401

    # 连续失败至超限(auth_cfg.max_attempts=3):共 3 次 401,第 4 次起 429
    for _ in range(auth_cfg["max_attempts"] - 1):
        resp = await api_client.post("/api/v1/sys/auth/password/login", json=body)
        assert resp.status_code == 401
    limited = await api_client.post("/api/v1/sys/auth/password/login", json=body)
    assert limited.status_code == 429
    assert limited.json()["data"]["error_code"] == "rate_limited"

    # 其它用户名不受影响
    other = await api_client.post(
        "/api/v1/sys/auth/password/login",
        json={"username": f"other_{secrets.token_hex(4)}", "password": "whatever-123"},
    )
    assert other.status_code == 401


@pytest.mark.db
async def test_register_duplicate_username_conflict(
    api_client: AsyncClient, db_session: AsyncSession, auth_cfg: dict, db_ready: bool
) -> None:
    """同名(含大小写变体)再注册 → 409,且第二张邀请码未被消费。"""
    family_id, code1 = await _new_family_with_invite(db_session)
    from app.models.sys_family import SysFamily

    family = await db_session.get(SysFamily, family_id)
    invite2 = await family_service.create_invite(
        db_session, family_id=family_id, role=InviteRole.ADVENTURER,
        created_by=family.owner_id,
    )

    username = f"dup_{secrets.token_hex(4)}"
    first = await api_client.post(
        "/api/v1/sys/auth/password/register",
        json={"code": code1, "username": username, "password": "sup3r-secret!"},
    )
    assert first.status_code == 200

    dup = await api_client.post(
        "/api/v1/sys/auth/password/register",
        json={"code": invite2.code, "username": username.upper(), "password": "sup3r-secret!"},
    )
    assert dup.status_code == 409

    await db_session.refresh(invite2)
    assert invite2.used_at is None

    await cleanup_family(db_session, family_id)


@pytest.mark.db
async def test_change_password_flow(
    api_client: AsyncClient, db_session: AsyncSession, auth_cfg: dict, db_ready: bool
) -> None:
    """改密需旧密码;改完后旧密码 401、新密码可登录。"""
    family_id, code = await _new_family_with_invite(db_session)

    username = f"chg_{secrets.token_hex(4)}"
    old_pw, new_pw = "old-password-1", "new-password-2"
    reg = await api_client.post(
        "/api/v1/sys/auth/password/register",
        json={"code": code, "username": username, "password": old_pw},
    )
    assert reg.status_code == 200, reg.text
    auth_header = {"Authorization": f"Bearer {reg.json()['data']['access_token']}"}

    # 错误的旧密码 → 401
    wrong = await api_client.put(
        "/api/v1/sys/auth/password/me",
        json={"new_password": new_pw, "old_password": "wrong-old-pw"},
        headers=auth_header,
    )
    assert wrong.status_code == 401

    # 正确旧密码 → 改密成功
    good = await api_client.put(
        "/api/v1/sys/auth/password/me",
        json={"new_password": new_pw, "old_password": old_pw},
        headers=auth_header,
    )
    assert good.status_code == 200, good.text

    assert (await api_client.post(
        "/api/v1/sys/auth/password/login",
        json={"username": username, "password": old_pw},
    )).status_code == 401
    assert (await api_client.post(
        "/api/v1/sys/auth/password/login",
        json={"username": username, "password": new_pw},
    )).status_code == 200

    await cleanup_family(db_session, family_id)


@pytest.mark.db
async def test_wechat_account_can_set_first_password(
    api_client: AsyncClient, db_session: AsyncSession, auth_cfg: dict, db_ready: bool
) -> None:
    """已有账号(如微信注册)首次设置网页密码:必须带 username,成功后即可密码登录。"""
    family_id, _ = await _new_family_with_invite(db_session)
    from app.models.sys_family import SysFamily
    from app.services import auth_service

    family = await db_session.get(SysFamily, family_id)
    owner = await db_session.get(SysAccount, family.owner_id)
    token = auth_service.issue_token_pair(owner).access_token
    auth_header = {"Authorization": f"Bearer {token}"}

    # 不带 username → 409
    missing = await api_client.put(
        "/api/v1/sys/auth/password/me",
        json={"new_password": "brand-new-pw-1"},
        headers=auth_header,
    )
    assert missing.status_code == 409

    username = f"wx_{secrets.token_hex(4)}"
    setpw = await api_client.put(
        "/api/v1/sys/auth/password/me",
        json={"new_password": "brand-new-pw-1", "username": username},
        headers=auth_header,
    )
    assert setpw.status_code == 200, setpw.text

    login = await api_client.post(
        "/api/v1/sys/auth/password/login",
        json={"username": username, "password": "brand-new-pw-1"},
    )
    assert login.status_code == 200

    await cleanup_family(db_session, family_id)
