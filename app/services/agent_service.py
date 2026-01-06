from __future__ import annotations

import time
from uuid import uuid4

from app.agents.base import BaseAgent
from app.schemas.agent import AgentRequest, AgentResponse


class AgentService:
    def __init__(self, agent: BaseAgent) -> None:
        self._agent = agent

    async def run(self, request: AgentRequest) -> AgentResponse:
        request_id = request.request_id or str(uuid4())
        start = time.perf_counter()
        output = await self._agent.run(request.query, request.metadata)
        latency_ms = int((time.perf_counter() - start) * 1000)
        return AgentResponse(
            request_id=request_id,
            output=output,
            latency_ms=latency_ms,
        )
