"""应用配置。

本文件集中读取环境变量，包含数据库、存储目录、LLM 模式和
OpenAI-compatible 第三方中转站配置。
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Park Agent"
    database_url: str = "postgresql+psycopg://park:park@db:5432/park_agent"
    report_storage_dir: str = "/app/storage"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"
    openai_agent_api: str = "chat_completions"
    llm_mode: str = "auto"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
