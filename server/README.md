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

## 7. 测试

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
- **种子数据创建链路**(`app/dev/seed.py` 的 `seed_basic_family`,被 `seeded_family` fixture
  复用):家庭 → 家长 → 孩子 → 赛季 → 任务模板 → 任务实例的基础创建链路,用例结束后通过
  `sys_family` 上的外键级联删除(`ondelete=CASCADE`)自动清理,不在远程数据库中留下脏数据。

### 本地手动造数据

```bash
cd server
uv run python scripts/seed_dev_data.py [suffix]
```

复用与冒烟测试相同的 `app/dev/seed.seed_basic_family`,在配置好的数据库上创建一条最小可用
的家庭数据链路,方便手动用 Postman / 前端 mock 阶段验证接口。这条数据目前还不能直接登录
(微信登录需要真实 openid);登录能力见后续的开发期非微信登录方案,届时可直接复用这里创建
的账号 ID 配合 `auth_service.issue_token_pair` 签发 token。

## 8. 代码检查

```bash
uv run ruff check .
uv run mypy app
```
