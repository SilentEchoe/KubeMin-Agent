"""Memory manager coordinating builtin, session search, and external providers."""

from __future__ import annotations

from pathlib import Path

from kubemin_agent.agent.memory.builtin import BuiltinMemoryStore, MemoryUpdateResult
from kubemin_agent.agent.memory.dream import (
    DreamDueResult,
    DreamSource,
    DreamTargetScope,
    MemoryDreamDraft,
    MemoryDreamService,
)
from kubemin_agent.agent.memory.provider import MemoryProvider, NoOpMemoryProvider
from kubemin_agent.agent.memory.scope import MemoryScope
from kubemin_agent.agent.memory.session_index import SessionSearchIndex, SessionSearchResult


class MemoryManager:
    """Hermes-style memory coordinator."""

    def __init__(
        self,
        root: Path,
        *,
        enabled: bool = True,
        user_max_chars: int = 1375,
        agent_memory_max_chars: int = 2200,
        team_max_chars: int = 2200,
        team_agent_memory_max_chars: int = 2600,
        warning_ratio: float = 0.8,
        session_search_enabled: bool = True,
        session_search_top_k: int = 5,
        dream_enabled: bool = True,
        dream_turn_threshold: int = 20,
        dream_draft_top_k: int = 20,
        external_provider: MemoryProvider | None = None,
    ) -> None:
        self.root = root.expanduser()
        self.enabled = enabled
        self.session_search_top_k = max(1, session_search_top_k)
        self.dream_enabled = dream_enabled
        self.builtin = BuiltinMemoryStore(
            self.root,
            user_max_chars=user_max_chars,
            agent_memory_max_chars=agent_memory_max_chars,
            team_max_chars=team_max_chars,
            team_agent_memory_max_chars=team_agent_memory_max_chars,
            warning_ratio=warning_ratio,
        )
        self.session_index = SessionSearchIndex(self.root, enabled=enabled and session_search_enabled)
        self.dream_service = MemoryDreamService(
            self.root,
            self.builtin,
            self.session_index,
            dream_turn_threshold=dream_turn_threshold,
            dream_draft_top_k=dream_draft_top_k,
        )
        self.external_provider = external_provider or NoOpMemoryProvider()
        if not isinstance(self.external_provider, NoOpMemoryProvider):
            self._external_provider_count = 1
        else:
            self._external_provider_count = 0

    def build_system_prompt_block(self, scope: MemoryScope) -> str:
        """Build the frozen scoped memory block for a run."""
        if not self.enabled:
            return ""
        return self.builtin.build_snapshot(scope)

    def update_builtin(
        self,
        scope: MemoryScope,
        target: str,
        action: str,
        content: str = "",
        old_text: str = "",
    ) -> MemoryUpdateResult:
        """Update scoped USER.md, TEAM.md, or MEMORY.md."""
        if not self.enabled:
            raise RuntimeError("memory is disabled")
        return self.builtin.update(scope, target=target, action=action, content=content, old_text=old_text)

    def search_sessions(
        self,
        scope: MemoryScope,
        query: str,
        top_k: int | None = None,
        scope_mode: str = "auto",
        agent_name: str | None = None,
        session_key: str | None = None,
        request_id: str | None = None,
    ) -> list[SessionSearchResult]:
        """Search scoped session history."""
        if not self.enabled:
            return []
        return self.session_index.search(
            scope,
            query=query,
            top_k=top_k or self.session_search_top_k,
            scope_mode=scope_mode,
            agent_name=agent_name,
            session_key=session_key,
            request_id=request_id,
        )

    def sync_turn(
        self,
        scope: MemoryScope,
        session_key: str,
        user_message: str,
        assistant_response: str,
        request_id: str = "",
    ) -> None:
        """Persist a completed turn to the large-capacity session index."""
        if not self.enabled:
            return
        self.session_index.index_turn(
            scope=scope,
            session_key=session_key,
            user_message=user_message,
            assistant_response=assistant_response,
            request_id=request_id,
        )

    def check_dream_due(self, scope: MemoryScope) -> DreamDueResult:
        """Check whether a scoped dream draft should be created."""
        if not self.enabled or not self.dream_enabled:
            return DreamDueResult(due=False, reasons=())
        return self.dream_service.check_due(scope)

    def create_dream_draft(
        self,
        scope: MemoryScope,
        target_scope: DreamTargetScope = "personal",
        source: DreamSource = "manual",
    ) -> MemoryDreamDraft:
        """Create a pending dream draft without updating builtin memory."""
        if not self.enabled:
            raise RuntimeError("memory is disabled")
        if not self.dream_enabled:
            raise RuntimeError("memory dream is disabled")
        return self.dream_service.create_draft(scope, target_scope=target_scope, source=source)

    def apply_dream_draft_item(self, draft_id: str, item_id: str) -> MemoryUpdateResult:
        """Apply one approved dream draft item to builtin memory."""
        if not self.enabled:
            raise RuntimeError("memory is disabled")
        if not self.dream_enabled:
            raise RuntimeError("memory dream is disabled")
        return self.dream_service.apply_draft_item(draft_id, item_id)
