"""Tests for YAML validation tool."""

from unittest.mock import patch

import pytest

from kubemin_agent.agent.tools.yaml_validator import YAMLValidatorTool


@pytest.fixture
def tool():
    """Create a validator tool."""
    return YAMLValidatorTool()


@pytest.mark.asyncio
async def test_validator_basic_properties(tool):
    """Test standard tool properties."""
    assert tool.name == "validate_yaml"
    assert "YAML string" in tool.description
    assert "content" in tool.parameters["required"]


@pytest.mark.asyncio
async def test_validator_no_pyyaml(tool):
    """Test gracefully degraded error when pyyaml is missing."""
    with patch.dict("sys.modules", {"yaml": None}):
        result = await tool.execute(content="kind: Pod")
        assert "PyYAML is not installed" in result


@pytest.mark.asyncio
async def test_validator_syntax_error(tool):
    """Test catching malformed YAML syntax."""
    bad_yaml = """
    kind: Pod
      metadata:
       invalid indent
    """
    result = await tool.execute(content=bad_yaml)
    assert "INVALID: YAML syntax error" in result


@pytest.mark.asyncio
async def test_validator_empty_document(tool):
    """Test catching empty documents."""
    result = await tool.execute(content="")
    assert "INVALID: empty YAML document" in result

    result2 = await tool.execute(content="---\n---\n")
    assert "INVALID: no YAML documents found" in result2


@pytest.mark.asyncio
async def test_validator_kubemin_workflow_valid(tool):
    """Test a fully valid KubeMin workflow."""
    valid_yaml = """
apiVersion: agent.kubemin.io/v1alpha1
kind: Workflow
metadata:
  name: demo-workflow
spec:
  components:
    - name: step-1
      trait: Job
    - name: step-2
      trait: Service
    """
    result = await tool.execute(content=valid_yaml)
    assert "VALID" in result
    assert "Summary: 1 document(s), kinds: Workflow" in result


@pytest.mark.asyncio
async def test_validator_missing_required_fields(tool):
    """Test missing standard Kubernetes/KubeMin fields."""
    missing_fields_yaml = """
metadata:
  labels:
    app: demo
    """
    result = await tool.execute(content=missing_fields_yaml)
    assert "INVALID" in result
    assert "missing required field: apiVersion" in result
    assert "missing required field: kind" in result
    assert "missing required field: metadata.name" in result


@pytest.mark.asyncio
async def test_validator_spec_warnings_and_errors(tool):
    """Test spec component validation rules."""
    bad_components_yaml = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: test
spec:
  components:
    - trait: Job # missing name
    - "not a dict"
    """
    result = await tool.execute(content=bad_components_yaml)

    # Missing name is a warning
    assert "Warnings:" in result
    assert "missing 'name'" in result

    # Not a dict is an error
    assert "Errors:" in result
    assert "spec.components[1] should be a mapping" in result
    assert "INVALID" in result


@pytest.mark.asyncio
async def test_validator_multi_document(tool):
    """Test validating multiple documents in one stream."""
    multi_docs = """
apiVersion: v1
kind: Service
metadata:
  name: svc1
---
apiVersion: v1
kind: Pod
metadata:
  name: pod1
    """
    result = await tool.execute(content=multi_docs)
    assert "VALID" in result
    assert "2 document" in result
    assert "Service, Pod" in result
