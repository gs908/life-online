# Life Online Server

家庭任务游戏化后端(FastAPI + PostgreSQL/Supabase + MinIO + LLM)。

## 0. 目录

```
server/
├── start.py                 # 启动入口
├── pyproject.toml           # uv 项目
├── config.yaml              # 结构化配置(默认值)
├── .env / .env.example      # 环境变量(.env 为本地密钥,不提交)
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

## 3. 起 PostgreSQL/Supabase + MinIO(本地开发)

数据库配置采用 `config.yaml + .env` 分段方式。使用 Supabase 时,在 `.env` 中填写:

```ini
DATABASE_HOST=aws-1-ap-southeast-1.pooler.supabase.com
DATABASE_PORT=6543
DATABASE_USER=postgres.mjonchwjzealatkbtbgd
DATABASE_PASSWORD=你的数据库密码
DATABASE_NAME=postgres
DATABASE_SSLMODE=require
```

MinIO 可按本地环境单独启动。若后续补齐仓库根 `docker-compose.yml`,本地 PostgreSQL + MinIO 可统一启动。

## 4. 数据库初始化 / 迁移

当前历史 Alembic 初始迁移使用 `Base.metadata.create_all()`,不适合在新的 PostgreSQL/Supabase 空库直接重放完整迁移链。空库初始化请优先使用安全同步脚本:

```bash
cd server
# 只读检查目标库是否已有项目表
uv run python scripts/sync_postgres_schema.py --check
# 确认为空后创建当前表结构并标记 Alembic head
uv run python scripts/sync_postgres_schema.py --apply
```

后续模型变更仍通过 Alembic 管理:

```bash
uv run alembic revision --autogenerate -m "your change"
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

## 8. 代码检查

```bash
uv run ruff check .
uv run mypy app
```
