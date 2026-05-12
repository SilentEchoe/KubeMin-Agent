"""Per-run memory runtime context."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from kubemin_agent.agent.memory.manager import MemoryManager
from kubemin_agent.agent.memory.scope import MemoryScope

_ACTIVE_SCOPE: ContextVar[MemoryScope | None] = ContextVar("active_memory_scope", default=None)
_ACTIVE_MANAGER: ContextVar[MemoryManager | None] = ContextVar("active_memory_manager", default=None)


def get_active_memory() -> tuple[MemoryManager, MemoryScope]:
    """Return active memory manager and scope or fail fast."""
    manager = _ACTIVE_MANAGER.get()
    scope = _ACTIVE_SCOPE.get()
    if manager is None or scope is None:
        raise RuntimeError("memory tools require an active MemoryManager and MemoryScope")
    return manager, scope


@contextmanager
def memory_run_context(manager: MemoryManager, scope: MemoryScope) -> Iterator[None]:
    """Set scoped memory context for tool execution."""
    manager_token = _ACTIVE_MANAGER.set(manager)
    scope_token = _ACTIVE_SCOPE.set(scope)
    try:
        yield
    finally:
        _ACTIVE_SCOPE.reset(scope_token)
        _ACTIVE_MANAGER.reset(manager_token)
