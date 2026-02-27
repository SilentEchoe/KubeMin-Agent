"""Tests for local memory backends and the unified MemoryStore."""

import os
from pathlib import Path

import pytest

from kubemin_agent.agent.memory.entry import MemoryEntry
from kubemin_agent.agent.memory.file_backend import FileBackend
from kubemin_agent.agent.memory.jsonl_backend import JSONLBackend
from kubemin_agent.agent.memory.store import MemoryStore


@pytest.fixture
def workspace(tmp_path: Path):
    """Create a temporary workspace directory."""
    return tmp_path


@pytest.mark.asyncio
async def test_file_backend_crud(workspace):
    """Test Create, Read, Delete operations for FileBackend."""
    backend = FileBackend(workspace)
    
    # Store
    entry1 = MemoryEntry(id="file-1", content="File content 1", tags=["test"], source="agent-x")
    entry2 = MemoryEntry(id="file-2", content="File content 2", tags=["docs"], source="agent-y")
    
    await backend.store(entry1)
    await backend.store(entry2)
    
    # List all
    entries = await backend.list_all()
    assert len(entries) == 2
    
    # Search
    results = await backend.search("content 1", top_k=5)
    assert len(results) == 1
    assert results[0].id == "file-1"
    
    # Delete
    assert await backend.delete("file-1") is True
    assert await backend.delete("does-not-exist") is False
    
    # List after delete
    entries = await backend.list_all()
    assert len(entries) == 1
    assert entries[0].id == "file-2"

    
@pytest.mark.asyncio
async def test_file_backend_parse_edge_cases(workspace):
    """Test corrupted or incorrectly formatted .md files in FileBackend."""
    backend = FileBackend(workspace)
    dir_path = workspace / "entries"
    dir_path.mkdir(exist_ok=True, parents=True)
    
    # Create a corrupted file
    bad_file = dir_path / "bad.md"
    bad_file.write_text("No frontmatter\nJust content", encoding="utf-8")
    
    entries = await backend.list_all()
    assert len(entries) == 1
    assert entries[0].content == "No frontmatter\nJust content"


@pytest.mark.asyncio
async def test_jsonl_backend_crud(workspace):
    """Test Create, Read, Delete operations for JSONLBackend."""
    backend = JSONLBackend(workspace)
    
    # Store
    entry1 = MemoryEntry(id="j-1", content="JSONL content A", tags=["test"], source="sys")
    entry2 = MemoryEntry(id="j-2", content="JSONL content B", tags=["data"], source="sys")
    
    await backend.store(entry1)
    await backend.store(entry2)
    
    # List all
    entries = await backend.list_all()
    assert len(entries) == 2
    
    # Search
    results = await backend.search("content B", top_k=5)
    assert len(results) == 1
    assert results[0].id == "j-2"
    
    # Delete
    assert await backend.delete("j-1") is True
    assert await backend.delete("fake-id") is False
    
    # List after delete
    entries = await backend.list_all()
    assert len(entries) == 1
    assert entries[0].id == "j-2"
    

@pytest.mark.asyncio
async def test_memory_store_facade(workspace):
    """Test the unified MemoryStore routing and factory."""
    # Test factory
    store_file = MemoryStore.create(workspace, backend_type="file")
    assert isinstance(store_file._backend, FileBackend)
    
    store_jsonl = MemoryStore.create(workspace, backend_type="jsonl")
    assert isinstance(store_jsonl._backend, JSONLBackend)
    
    # Test facade methods using FileBackend as delegate
    store = store_file
    
    # Remember
    eid = await store.remember("Facade content", tags=["facade"], source="tester")
    assert eid is not None
    
    # Recall
    results = await store.recall("Facade")
    assert len(results) == 1
    assert results[0].id == eid
    
    # Get context (no query)
    context_all = await store.get_context()
    assert "## Relevant Memories" in context_all
    assert "Facade content" in context_all
    
    # Get context (with query)
    context_filtered = await store.get_context(query="Facade")
    assert "Facade content" in context_filtered
    
    # Forget
    assert await store.forget(eid) is True
    assert len(await store.list_all()) == 0
    
    # Get empty context
    assert await store.get_context() == ""
