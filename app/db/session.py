"""数据库连接和 session 管理。

本文件负责创建 SQLAlchemy engine、提供 FastAPI 数据库依赖，
并在本地开发/面试作业环境中初始化数据库表。
"""

from collections.abc import Generator
import time

from sqlalchemy.exc import OperationalError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import get_settings
from app.db.models import Base

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db(max_attempts: int = 30, delay_seconds: float = 1.0) -> None:
    """初始化数据库表；数据库容器启动较慢时会短暂重试连接。"""
    for attempt in range(1, max_attempts + 1):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except OperationalError:
            if attempt == max_attempts:
                raise
            time.sleep(delay_seconds)


def get_db() -> Generator[Session, None, None]:
    """为 FastAPI 请求提供数据库 session，并在请求结束后关闭连接。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
