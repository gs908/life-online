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

## 7.2 Web 管理后端:赛季管理

以下接口均需 `Authorization: Bearer <access_token>`,返回统一走 `ApiResponse[T]` 包装。

| 方法 & 路径 | 权限 | 说明 | 返回结构 |
| --- | --- | --- | --- |
| `GET /api/v1/scn/seasons` | 任意已登录角色 | 列出自己家庭的全部赛季(`include_inactive=false` 只看激活赛季) | `SeasonRead[]` |
| `GET /api/v1/scn/seasons/active` | 任意已登录角色 | 当前激活赛季,没有则为 `null` | `SeasonRead \| null` |
| `GET /api/v1/scn/seasons/history` | 任意已登录角色 | 历史赛季 + 每季任务统计,供管理台历史面板展示 | `SeasonHistoryItem[]` |
| `GET /api/v1/scn/seasons/{id}` | 任意已登录角色 | 赛季详情,跨家庭访问统一 `404` | `SeasonRead` |
| `POST /api/v1/scn/seasons` | 仅 `GUILD_MASTER` | 创建赛季,自动使同家庭下原激活赛季下线 | `SeasonRead` |
| `PATCH /api/v1/scn/seasons/{id}` | 仅 `GUILD_MASTER` | 更新赛季(名称/主题/剧情/结束时间/激活状态) | `SeasonRead` |
| `POST /api/v1/scn/seasons/{id}/activate` | 仅 `GUILD_MASTER` | 激活指定赛季,同家庭下其他赛季自动下线 | `SeasonRead` |
| `DELETE /api/v1/scn/seasons/{id}` | 仅 `GUILD_MASTER` | 删除赛季(级联删除其下任务模板/任务实例) | `{"deleted": true}` |

`SeasonRead` 关键字段:`id`、`family_id`、`name`、`theme_id`、`narrative_context`、`start_date`、
`end_date`、`is_active`、`created_at`/`updated_at`。`SeasonHistoryItem` = `{season: SeasonRead,
total_tasks, completed_tasks, total_xp}`,`total_xp` 是该赛季内所有 `COMPLETED` 任务实例的
`xp_awarded` 之和。

**单一激活赛季约束**:

- 服务层在 `create_season` / `update_season(is_active=True)` / `activate_season` 中,先把同
  家庭下其他 `is_active=True` 的赛季下线,再插入/激活目标赛季。
- 数据库层额外兜底:`scn_season` 新增生成列 `active_family_id`
  (`IF(is_active, family_id, NULL)` STORED),并在其上建唯一索引
  `ux_scn_season_active_per_family`。同一家庭最多一行 `is_active=True`(对应一个非 NULL 的
  `active_family_id`),并发写入冲突时数据库唯一约束会兜底拒绝,服务层捕获后转换为
  `409 Conflict`,不会出现两个 active 赛季。见迁移
  `alembic/versions/f3a1c9d02b7e_scn_season_single_active_per_family.py`。

**任务/主题关联规则**:

- `scn_task_template.season_id` / `scn_task_instance.season_id` 均为必填外键
  (`ondelete="CASCADE"`),一个任务模板/实例恒属于唯一一个赛季;删除赛季会级联删除挂在它下面
  的任务模板和任务实例。
- `theme_id` 挂在赛季上(`ThemeId` 枚举),任务模板/实例不单独持有主题,展示时通过所属赛季的
  `theme_id` 取主题视觉样式(对应管理台 `SeasonHistory.tsx` / `SeasonConfigModal.tsx` 里按
  `theme.id` 取 `THEMES` 映射的用法)。

**跨家庭隔离**:详情/更新/激活/删除对别的家庭的赛季一律返回 `404`(与 `family_service` 的约定
一致,不泄露赛季是否存在于别的家庭);`GUILD_MASTER`-only 接口对 `ADVENTURER` 角色一律 `403`。

## 7.3 Web 管理后端:时间币 / 上传 / AI 闭环

以下接口均需 `Authorization: Bearer <access_token>`,返回统一走 `ApiResponse[T]` 包装。

| 方法 & 路径 | 权限 | 说明 | 返回结构 |
| --- | --- | --- | --- |
| `GET /api/v1/scn/time-configs/me` | 任意已登录角色 | 查看自己家庭的时间币规则(默认每日额度 + 按星期几的特例) | `TimeConfigRead` |
| `PUT /api/v1/scn/time-configs/me` | 仅 `GUILD_MASTER` | 更新默认每日额度 / 星期特例(整体替换 `exceptions`) | `TimeConfigRead` |
| `GET /api/v1/scn/time-coin-logs` | 任意已登录角色 | 分页查询自己家庭的时间币流水,可选 `child_id` 过滤 | `Page[CoinTransactionRead]` |
| `POST /api/v1/scn/time-coin-logs/adjust` | 仅 `GUILD_MASTER` | 人工调整某个孩子的时间币余额,落一条 `MANUAL_ADJUST` 流水 | `CoinTransactionRead` |
| `POST /api/v1/sys/uploads` | 任意已登录角色 | multipart 上传(`file` + `purpose`),`purpose=task_proof` 用于任务完成凭证图片 | `UploadRead` |
| `POST /api/v1/scn/ai/generate-quest` | 仅 `GUILD_MASTER` | 按主题 / 孩子等级 / 剧情上下文生成任务草稿(结构化 JSON) | `GenerateQuestResponse` |
| `POST /api/v1/scn/ai/evaluate-proof` | 仅 `GUILD_MASTER` | 对任务完成凭证做 AI 初评,返回建议与理由 | `EvaluateProofResponse` |

**前端可用返回字段**:

- `TimeConfigRead`:`family_id`、`default_daily_allowance`、`exceptions: {day_of_week, coin_amount}[]`(`day_of_week` 0=周一)。
- `CoinTransactionRead`:`id`、`family_id`、`child_id`、`amount`(正负号即增减)、`type`(`DAILY_RESET`/`TASK_REWARD`/`MANUAL_ADJUST`/...)、`note`、`created_at`。
- `UploadRead`:`id`、`family_id`、`purpose`、`object_key`、`access_url` —— **前端只用 `access_url` 展示图片**,不关心背后是 MinIO 预签名链接还是本地静态文件路径,两种存储模式返回的字段形状完全一致。
- AI 接口的返回体只包含生成结果(题目/理由等文本字段),**不包含、也不会包含任何模型 Key** —— 前端永远不直连模型服务,所有 LLM 调用都经由后端 `app/common/llm` 转发。

**每日重置 ↔ 时间币配置联动**:`app/workers/scheduler.py` 的 `daily_reset_job`(每天 00:05)对
`last_login_date != 今天` 的孩子调用 `coin_service.reset_daily_allowance`,后者读取
`get_or_create_time_config` 返回的规则(先查当天星期几是否有 `exceptions` 特例,没有则用
`default_daily_allowance`)写回余额并落 `DAILY_RESET` 流水;孩子调用 `GET /sys/accounts/me` 时
也会触发同一条重置逻辑,不需要等定时任务。

**LLM / MinIO 未配置时的降级规则**(DEV-9 新增):

- **LLM**(`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`,对应 `config.yaml` 的 `llm:` 段)三个字段
  均允许留空 —— 留空时应用照常启动,不会因为缺少 AI 配置就整体起不来。只有真正调用
  `/scn/ai/generate-quest` 或 `/scn/ai/evaluate-proof` 时,`app/common/llm/factory.get_llm_client()`
  才会检查 `settings.llm.is_configured`,未配置时抛出 `ServiceUnavailableError`,统一映射为
  `HTTP 503` + `{"data": {"error_code": "service_unavailable"}}`,而不是连接超时或 500。
- **MinIO**(`STORAGE_PROVIDER=minio` 时需要 `MINIO_ENDPOINT` / `MINIO_ACCESS_KEY` /
  `MINIO_SECRET_KEY`)同理:`app/common/storage/factory.get_storage()` 在
  `settings.storage.minio.is_configured` 为假时直接抛 `ServiceUnavailableError`(503),不会把空
  字符串传给 MinIO SDK 产生难以理解的底层报错。
- **降级路径**:把 `STORAGE_PROVIDER` 切成 `local`(`config.yaml` 的 `storage.provider`),上传接口
  即可在完全不配置 MinIO 的情况下工作,返回的 `UploadRead.access_url` 指向本地静态文件挂载路径,
  字段形状与 MinIO 模式一致,前端无需区分。AI 功能目前没有"降级实现",未配置 LLM 时就是明确的
  503,前端应据此提示"该功能未开放",而不是重试。
- 二者共用同一套错误语义:`ServiceUnavailableError`(503,"根本没配置")与已有的
  `ExternalServiceError`(502,"配置了但这次调用失败,比如 LLM 限流/微信接口报错")是两类不同的
  错误,前端可以按 `error_code` 区分展示文案。

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
- **Web 管理后端:赛季管理**(`tests/test_season_management_smoke.py`,需要数据库):
  创建 → 详情 → 更新 → 激活 → 删除的完整闭环;创建/激活新赛季会自动使原激活赛季下线,任意时刻
  同家庭最多一个 `is_active=True`;详情/更新/激活/删除对别的家庭的赛季返回 `404`;孩子角色调用
  写接口返回 `403`;历史统计接口返回的任务总数/完成数/已发放 XP 总和与种子数据一致;删除赛季会
  级联删除其下的任务模板和任务实例。
- **LLM / MinIO 未配置降级**(`tests/test_ai_storage_config.py`,无需数据库,始终执行):
  `LLMSection`/`StorageMinioSection.is_configured` 的判定逻辑;`get_llm_client()`/`get_storage()`
  在未配置时抛出 `ServiceUnavailableError`(503)且报错信息里点名缺失的环境变量;`local` 存储在
  任何情况下都能正常初始化,不依赖 MinIO 配置。
- **时间币 / 上传 / AI 闭环**(`tests/test_time_coin_upload_ai_smoke.py`,需要数据库):时间币配置
  读取/更新(孩子无权更新);时间币流水查询与人工调整(孩子无权调整,跨家庭隔离);每日重置按
  时间币配置的当日特例/默认额度写回余额;`local` 存储模式下任务凭证上传成功且 `access_url`
  可直接展示;MinIO 未配置 / LLM 未配置时上传接口与 AI 接口分别返回 `503`。

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

