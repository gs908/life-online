"""
应用配置加载。

- `config.yaml` 存放结构化默认值
- 占位符语法:
    ${env:VAR}            必填,缺失报错
    ${env:VAR:default}    缺失时使用 default
- 解析后用 Pydantic 模型校验,提供类型安全访问
- DB 字段独立配置,运行期自动拼装为:
    async URL: mysql+asyncmy://user:pwd@host:port/db?charset=utf8mb4
    sync  URL: mysql+pymysql://user:pwd@host:port/db?charset=utf8mb4
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# 1. 先把 .env 加载到进程环境
load_dotenv(override=False)

# 2. 匹配 ${env:VAR} 或 ${env:VAR:default}
_ENV_REF_PATTERN = re.compile(r"\$\{env:([A-Z_][A-Z0-9_]*)(?::([^}]*))?\}")


def _resolve_env_refs(obj: Any, env: dict[str, str]) -> Any:
    """递归解析 yaml 树中的占位符。"""
    if isinstance(obj, dict):
        return {k: _resolve_env_refs(v, env) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env_refs(v, env) for v in obj]
    if isinstance(obj, str):
        def repl(m: re.Match) -> str:
            key = m.group(1)
            default = m.group(2)
            if key in env and env[key] != "":
                return env[key]
            if default is not None:
                return default
            raise ValueError(
                f"config.yaml 引用了环境变量 {key!r},但在 .env 和当前环境中均未设置。"
            )
        return _ENV_REF_PATTERN.sub(repl, obj)
    return obj


# ---- 配置 schema ----

class AppSection(BaseModel):
    name: str = "life-online"
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    debug: bool = False
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=list)


class DatabasePoolSection(BaseModel):
    pool_pre_ping: bool = True
    pool_recycle: int = 3600


class DatabaseSection(BaseModel):
    host: str
    port: int
    user: str
    password: str
    database: str
    charset: str = "utf8mb4"
    pool: DatabasePoolSection = Field(default_factory=DatabasePoolSection)

    @property
    def url_async(self) -> str:
        """运行时用,asyncmy 驱动。"""
        return (
            f"mysql+asyncmy://{quote_plus(self.user)}:{quote_plus(self.password)}"
            f"@{self.host}:{self.port}/{self.database}?charset={self.charset}"
        )

    @property
    def url_sync(self) -> str:
        """Alembic 迁移用,pymysql 驱动。"""
        return (
            f"mysql+pymysql://{quote_plus(self.user)}:{quote_plus(self.password)}"
            f"@{self.host}:{self.port}/{self.database}?charset={self.charset}"
        )


class StorageMinioSection(BaseModel):
    endpoint: str = ""
    access_key: str = ""
    secret_key: str = ""
    secure: bool = False
    bucket: str = "life-online"


class StorageLocalSection(BaseModel):
    root_path: str = "./uploads"
    public_base_url: str = "/api/v1/files"
    bucket: str = "local"


class StorageSection(BaseModel):
    provider: str = "minio"
    minio: StorageMinioSection = Field(default_factory=StorageMinioSection)
    local: StorageLocalSection = Field(default_factory=StorageLocalSection)


class LLMSection(BaseModel):
    base_url: str
    api_key: str
    model: str


class JWTSection(BaseModel):
    secret: str
    algorithm: str = "HS256"
    access_expires_minutes: int = 60
    refresh_expires_days: int = 14


class WechatSection(BaseModel):
    open_appid: str = ""
    open_secret: str = ""
    open_redirect_uri: str = ""
    mp_appid: str = ""
    mp_secret: str = ""


class RedisSection(BaseModel):
    """预留,暂不接入。"""
    enabled: bool = False
    url: str = "redis://localhost:6379/0"


class XpSection(BaseModel):
    """
    经验值 / 等级数值配置。

    升级所需 XP 采用指数曲线:
        xp_required_for_level(L) = base_xp * growth ** (L - 1)
    前 Lv1~Lv5 一周内可达,Lv10+ 进入"长期目标"段。
    所有倍率集中在配置中,便于不发布代码即可调参。
    """
    base_xp: int = 200
    growth: float = 1.5

    # 星级系数: 1-5 星 -> 倍率
    rating_multiplier: dict[int, float] = Field(
        default_factory=lambda: {1: 0.6, 2: 0.8, 3: 1.0, 4: 1.2, 5: 1.5}
    )

    # 任务类型加成
    challenge_bonus: float = 1.25
    hidden_bonus: float = 1.15

    # 连环任务链末加成
    chain_final_bonus: float = 1.5

    # 时效系数(限时任务)
    timing_bonus: float = 1.2
    timing_penalty: float = 0.8

    # 速度系数(60 分钟内完成)
    speed_window_minutes: int = 60
    speed_bonus: float = 1.1


class Settings(BaseModel):
    app: AppSection
    database: DatabaseSection
    storage: StorageSection
    llm: LLMSection
    jwt: JWTSection
    wechat: WechatSection
    redis: RedisSection = Field(default_factory=RedisSection)
    xp: XpSection = Field(default_factory=XpSection)


@lru_cache
def get_settings() -> Settings:
    config_path = Path(os.getenv("LIFE_ONLINE_CONFIG", "config.yaml"))
    if not config_path.exists():
        raise FileNotFoundError(
            f"未找到配置文件: {config_path.resolve()}。"
            f"请复制 config.yaml.example,或设置环境变量 LIFE_ONLINE_CONFIG 指向你的配置。"
        )
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    resolved = _resolve_env_refs(raw, dict(os.environ))
    return Settings.model_validate(resolved)


# 进程级单例
settings = get_settings()
