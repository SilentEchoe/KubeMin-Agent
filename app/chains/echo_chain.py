from __future__ import annotations

from langchain_core.runnables import RunnableLambda


def build_echo_chain() -> RunnableLambda:
    return RunnableLambda(lambda payload: {"echo": payload["input"]})
