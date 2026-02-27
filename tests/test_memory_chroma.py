"""Tests for ChromaDB memory backend."""

import os
import pytest

from kubemin_agent.agent.memory.chroma_backend import ChromaDBBackend
from kubemin_agent.agent.memory.entry import MemoryEntry


@pytest.fixture(autouse=True)
def isolated_chroma_env(tmp_path):
    """Ensure ONNX and Chroma don't clash on default cache dirs during testing."""
    cache_dir = tmp_path / ".cache"
    cache_dir.mkdir()
    
    old_onnx = os.environ.get("ONNX_HOME")
    old_chroma = os.environ.get("CHROMA_CACHE_DIR")
    
    os.environ["ONNX_HOME"] = str(cache_dir / "onnx")
    os.environ["CHROMA_CACHE_DIR"] = str(cache_dir / "chroma")
    
    yield
    
    if old_onnx is not None:
        os.environ["ONNX_HOME"] = old_onnx
    else:
        os.environ.pop("ONNX_HOME", None)
        
    if old_chroma is not None:
        os.environ["CHROMA_CACHE_DIR"] = old_chroma
    else:
        os.environ.pop("CHROMA_CACHE_DIR", None)


@pytest.fixture
def workspace(tmp_path):
    """Create a temporary workspace directory."""
    return tmp_path


@pytest.mark.asyncio
async def test_chroma_backend_crud(workspace):
    """Test Create, Read (list), Delete operations."""
    backend = ChromaDBBackend(workspace)

    # List empty
    entries = await backend.list_all()
    assert len(entries) == 0

    # Store
    entry1 = MemoryEntry(id="test-1", content="I am GeneralAgent.", tags=["identity"])
    entry2 = MemoryEntry(id="test-2", content="Kubernetes is a container orchestration system.", tags=["knowledge"])

    await backend.store(entry1)
    await backend.store(entry2)

    # List all
    entries = await backend.list_all()
    assert len(entries) == 2
    # Verify content was preserved
    contents = {e.content for e in entries}
    assert "I am GeneralAgent." in contents

    # Delete
    deleted = await backend.delete(entry1.id)
    assert deleted is True

    # List after delete
    entries = await backend.list_all()
    assert len(entries) == 1
    assert entries[0].id == entry2.id

    # Delete non-existent
    deleted = await backend.delete("does-not-exist")
    assert deleted is False


@pytest.mark.asyncio
async def test_chroma_backend_search(workspace):
    """Test semantic search."""
    backend = ChromaDBBackend(workspace)

    # Store varied content
    docs = [
        "The cluster has 3 worker nodes.",
        "Pod nginx-deployment-123 is CrashLoopBackOff.",
        "To deploy, run kubectl apply -f manifest.yaml.",
        "My favorite color is blue.",
        "Node memory pressure detected on worker-2.",
    ]

    for i, doc in enumerate(docs):
        await backend.store(MemoryEntry(id=f"doc-{i}", content=doc))

    # Basic keyword search
    results = await backend.search("nginx", top_k=2)
    assert len(results) > 0
    assert "nginx-deployment-123" in results[0].content

    # Semantic search (should match "Cluster has 3 worker nodes" or "Node memory pressure")
    results = await backend.search("How many servers are in the k8s environment?", top_k=2)
    assert len(results) > 0
    contents = [r.content for r in results]
    assert any("worker nodes" in c or "worker-2" in c for c in contents)

    # Empty query should return recent entries
    results = await backend.search("", top_k=3)
    assert len(results) == 3
