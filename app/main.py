"""FastAPI 应用入口。

本文件创建应用实例、注册中间件和路由，并在启动时初始化数据库表。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.config.settings import get_settings
from app.db.session import init_db


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def startup() -> None:
        """应用启动时初始化数据库表，保证本地 Docker Compose 首次运行可用。"""
        init_db()

    app.include_router(health_router)
    app.include_router(jobs_router)
    return app


app = create_app()
