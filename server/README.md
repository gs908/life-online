# Life Online Server

家庭任务游戏化后端(FastAPI + MySQL + MinIO + LLM)。

## 0. 目录

```
server/
├── start.py                 # 启动入口
├── pyproject.toml           # uv 项目
├── config.yaml              # 结构化配置(默认值)
├── .env / .env.example      # 环境变量(密钥、URL)
├── alembic/                 # DB 迁移
└── app/
    ├── main.py              # FastAPI 实例
    ├── config.py            # 配置加载(config.yaml + ${env:VAR} 解析)
    ├── deps.py              # 依赖注入
    ├── api/v1/              # HTTP 路由
    ├── common/              # 基础设施层
    │   ├── db/              # SQLAlchemy engine / session / Base
    │   ├── storage/         # 对象存储抽象 + MinIO 实现
    │   ├── llm/             # LLM 抽象 + OpenAI 协议实现
    │   ├── security/        # JWT 等
    │   ├── exceptions.py
    │   └── logging.py
    ├── models/              # SQLAlchemy ORM
    │   ├── enums.py
    │   ├── family.py / user.py / task.py / ...
    └── services/            # 业务逻辑(后续添加)
```

## 1. 准备依赖

```bash
cd server
uv sync
```

## 2. 配置

```bash
# 复制并按需修改
cp .env.example .env
# 编辑 .env 填入真实值
```

`config.yaml` 是结构化配置,所有 `${env:VAR}` 占位符会在启动时从 `.env`(或进程环境)解析。

## 3. 起 MySQL + MinIO(本地开发)

项目根目录有 `docker-compose.yml`(后续添加),用 docker 起这两个服务:

```bash
# 回到仓库根
cd ..
docker compose up -d mysql minio
# MinIO 控制台:http://localhost:9001 (minioadmin / minioadmin)
```

## 4. 数据库迁移

```bash
cd server
# 生成首个迁移(基于 Base.metadata)
uv run alembic revision --autogenerate -m "init schema"
# 执行
uv run alembic upgrade head
```

## 5. 启动

```bash
# 开发模式(hot reload)
uv run python start.py

# 生产模式(多 worker)
uv run python start.py --prod

# 自定义端口
uv run python start.py --port 9000
```

启动后访问:

- `GET http://localhost:8000/api/v1/health` — 基础探活
- `GET http://localhost:8000/api/v1/health/ready` — 就绪探针
- `GET http://localhost:8000/docs` — Swagger UI
- `GET http://localhost:8000/redoc` — ReDoc

## 6. 切换 LLM

修改 `server/.env`:

```ini
# 默认:火山引擎 Ark Coding + Kimi K2.6
LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/coding
LLM_API_KEY=...
LLM_MODEL=kimi-k2.6

# 切到 OpenAI
# LLM_BASE_URL=https://api.openai.com/v1
# LLM_MODEL=gpt-4o-mini

# 切到 DeepSeek
# LLM_BASE_URL=https://api.deepseek.com/v1
# LLM_MODEL=deepseek-chat

# 切到 Ollama 本地
# LLM_BASE_URL=http://localhost:11434/v1
# LLM_API_KEY=ollama
# LLM_MODEL=qwen2.5:7b
```

无需改代码,重启服务即可。

## 7. 开发期非微信登录

微信登录依赖真实 `openid`,开发/测试环境不方便每次都走微信授权流程。为此提供了一个
仅限开发环境使用的登录入口:

```
POST /api/v1/sys/auth/dev-login
Content-Type: application/json

{"role": "GUILD_MASTER"}   // 或 "ADVENTURER"
```

- **开关**:`server/.env` 里的 `DEV_LOGIN_ENABLED`(对应 `config.yaml` 的
  `dev.login_enabled`)。**默认 `false`**,生产环境必须保持关闭 —— 关闭时该接口对任何请求
  一律返回 `403`,不区分角色/参数。仅本地开发或测试环境显式设为 `true` 才能使用。
- **行为**:按 `role` 返回(必要时创建)一个固定挂在“开发环境”家庭下的测试账号 ——
  `GUILD_MASTER` 对应家长,`ADVENTURER` 对应孩子。同一角色重复调用返回同一个账号(幂等),
  不会每次登录都在数据库里堆一条新家庭。
- **返回**:与微信登录 (`/sys/auth/wechat/jscode`) 一样的 `TokenPair`(复用
  `auth_service.issue_token_pair`),拿到 token 后即可正常调用 `/sys/auth/me` 等受保护接口。
- 这条路径下创建的“开发环境”家庭数据是有意长期保留的(不像冒烟测试那样每次清理),因为它
  本身就是给本地/测试环境反复复用的固定账号;`DEV_LOGIN_ENABLED=false` 时接口不可达,生产
  数据库不会出现这条数据。

## 7.1 Web 管理后端:家庭 / 家长 / 孩子账号管理

以下接口均需 `Authorization: Bearer <access_token>`(见上一节的开发期登录,或微信登录)。
返回统一走 `ApiResponse[T]` 包装:`{"data": T, ...}`,`T` 为下方标注的结构。

| 方法 & 路径 | 权限 | 说明 | 返回结构 |
| --- | --- | --- | --- |
| `GET /api/v1/sys/families/me` | 任意已登录角色 | 查看自己家庭的成员列表 | `FamilyMembersRead`:`{family: FamilyRead, guild_masters: UserRead[], adventurers: UserRead[]}`,只包含当前用户所属家庭 |
| `GET /api/v1/sys/accounts/me` | 任意已登录角色 | 查看当前登录账号资料(孩子角色会顺带触发每日重置) | `UserRead` |
| `PATCH /api/v1/sys/accounts/me` | 任意已登录角色 | 更新自己的昵称 / 头像 / locale(孩子角色额外支持等级等游戏化字段) | `UserRead` |
| `POST /api/v1/sys/accounts/adventurers` | 仅 `GUILD_MASTER` | 在自己家庭下创建一个孩子(冒险者)账号 | `UserRead` |
| `PATCH /api/v1/sys/accounts/adventurers/{account_id}` | 仅 `GUILD_MASTER` | 更新自己家庭下某个孩子的基础信息(昵称 / 头像),不涉及等级/时间币等游戏化数值 | `UserRead` |

`UserRead` 关键字段:`id`、`family_id`、`role`(`GUILD_MASTER`/`ADVENTURER`)、`name`、`avatar`、
`locale`、`child_id`(家长为 `null`)、`level`/`xp`/`time_coins`/`daily_abandon_count`(家长恒为
默认值)、`created_at`/`updated_at`。

**权限与隔离**:

- `GUILD_MASTER`-only 接口对 `ADVENTURER` 角色一律返回 `403`(见 `app/deps.py` 的
  `require_role`)。
- 创建 / 更新孩子账号时,`family_id` 恒取自当前登录家长的 `user.family_id`,不接受请求体传入
  ——家长不可能操作到别的家庭。更新接口额外在服务层(`family_service.get_adventurer_in_family`)
  校验目标账号确实属于同一家庭且角色是 `ADVENTURER`,不满足则统一返回 `404`,不区分"不存在"
  和"属于别的家庭",避免枚举出别的家庭的账号 id。

## 8. 测试

```bash
uv run pytest
```

测试策略是"远程数据库优先,不做 Docker 实机验证":

- `tests/conftest.py` 在 import 任何 `app.*` 模块之前,为 `JWT_SECRET` / `LLM_BASE_URL` /
  `LLM_API_KEY` / `LLM_MODEL` 这几个没有默认值的必填配置注入开发期占位默认值(仅
  `setdefault`,已配置真实 `.env` 的开发者不受影响),这样 `uv run pytest` 在一个干净环境
  (没有 `.env`)里也能跑起来。
- `db_ready` fixture 会先对配置的数据库探测一次 `SELECT 1`。数据库不可达时,依赖它的用例会
  被自动 `pytest.skip`,而不是失败,也不会在本机拉起 Docker MySQL 做实机验证。
- 标了 `@pytest.mark.db` 的测试模块(例如 `tests/test_auth_smoke.py`)依赖真实数据库连接;
  不可达时会被整体跳过。不带这个标记的用例(例如 `tests/test_health_smoke.py`)不依赖数据库,
  始终会执行。
- `api_client` fixture 用 httpx `AsyncClient` + `ASGITransport` 直接对内存中的 FastAPI app
  发请求,不需要起一个真实的 uvicorn 进程。

当前覆盖的测试链路:

- **健康检查**(`tests/test_health_smoke.py`,无需数据库):`/api/v1/health`、
  `/api/v1/health/ready`、`/docs` 能正常返回。
- **认证基础路径**(`tests/test_auth_smoke.py`,需要数据库):家长 / 孩子身份分别调用
  `/api/v1/sys/auth/me` 能拿到对应角色和 `family_id` / `child_id`;`/api/v1/sys/auth/refresh`
  能用 refresh token 换发新 token;不带 `Authorization` 头访问受保护接口会被拒绝(401)。
- **开发期非微信登录**(`tests/test_dev_login_smoke.py`):
  - 关闭场景(不需要数据库,始终执行):默认配置、以及显式通过
    `app.dependency_overrides` 把 `DEV_LOGIN_ENABLED` 覆盖为 `false` 两种情况下,
    `/sys/auth/dev-login` 都返回 `403`。
  - 开启场景(需要数据库,标了 `@pytest.mark.db` + `db_ready`):把 `DEV_LOGIN_ENABLED`
    覆盖为 `true` 后,家长 / 孩子两种角色都能登录成功并调用 `/sys/auth/me`;重复调用同一
    角色会拿到同一个账号(幂等)。
- **种子数据创建链路**(`app/dev/seed.py` 的 `seed_basic_family`,被 `seeded_family` fixture
  复用):家庭 → 家长 → 孩子 → 赛季 → 任务模板 → 任务实例的基础创建链路,用例结束后通过
  `sys_family` 上的外键级联删除(`ondelete=CASCADE`)自动清理,不在远程数据库中留下脏数据。
- **Web 管理后端:家庭 / 孩子账号管理**(`tests/test_family_management_smoke.py`,需要数据库):
  `GET /sys/families/me` 只返回当前用户所属家庭的成员,不泄露另一个家庭的数据;
  `POST /sys/accounts/adventurers` 家长可创建孩子账号,孩子角色调用返回 `403`;
  `PATCH /sys/accounts/adventurers/{id}` 家长可更新自己家庭下孩子的昵称/头像,孩子角色调用
  返回 `403`,家长更新另一个家庭的孩子账号返回 `404`(跨家庭隔离);
  `GET`/`PATCH /sys/accounts/me` 对家长和孩子两种角色都能正常查看和更新。

### 本地手动造数据

```bash
cd server
uv run python scripts/seed_dev_data.py [suffix]
```

复用与冒烟测试相同的 `app/dev/seed.seed_basic_family`,在配置好的数据库上创建一条最小可用
的家庭数据链路,方便手动用 Postman / 前端 mock 阶段验证接口。这条数据目前还不能直接登录
(微信登录需要真实 openid);如果只是要一个能登录的账号,直接用上面的开发期非微信登录接口
(`DEV_LOGIN_ENABLED=true` 时的 `POST /sys/auth/dev-login`)更省事。

## 9. 代码检查

```bash
uv run ruff check .
uv run mypy app
```

