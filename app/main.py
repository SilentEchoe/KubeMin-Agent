from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.middlewares.request_id import RequestIdMiddleware


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title=settings.app_name)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_v1_router, prefix=settings.api_prefix)
    return app


app = create_app()
