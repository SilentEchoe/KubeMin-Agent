from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import agents, health

api_v1_router = APIRouter()
api_v1_router.include_router(health.router, tags=["health"])
api_v1_router.include_router(agents.router, prefix="/agents", tags=["agents"])
