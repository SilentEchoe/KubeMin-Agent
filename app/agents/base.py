from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from langchain_core.runnables import Runnable

from app.chains.echo_chain import build_echo_chain


class BaseAgent(ABC):
    @abstractmethod
    async def run(self, query: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError


class LangChainAgent(BaseAgent):
    def __init__(self, chain: Runnable | None = None) -> None:
        self._chain = chain or build_echo_chain()

    async def run(self, query: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"input": query, "metadata": metadata or {}}
        result = await self._chain.ainvoke(payload)
        return {"result": result}
