from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import get_agent_service
from app.schemas.agent import AgentRequest, AgentResponse
from app.services.agent_service import AgentService

router = APIRouter()


@router.post("/run", response_model=AgentResponse)
async def run_agent(
    payload: AgentRequest,
    request: Request,
    service: AgentService = Depends(get_agent_service),
) -> AgentResponse:
    payload = payload.model_copy(
        update={"request_id": payload.request_id or request.state.request_id}
    )
    return await service.run(payload)
