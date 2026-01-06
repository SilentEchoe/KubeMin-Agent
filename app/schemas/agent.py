from __future__ import annotations

from typing import Any
from pydantic import BaseModel


class AgentRequest(BaseModel):
    request_id: str | None = None
    query: str
    metadata: dict[str, Any] | None = None


class AgentResponse(BaseModel):
    request_id: str
    output: dict[str, Any]
    latency_ms: int
