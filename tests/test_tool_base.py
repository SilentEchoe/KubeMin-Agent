"""Tests for the Tool base class and parameter validation."""

from typing import Any

import pytest

from kubemin_agent.agent.tools.base import Tool


class DummyTool(Tool):
    """A dummy tool for testing."""

    @property
    def name(self) -> str:
        return "dummy_tool"

    @property
    def description(self) -> str:
        return "A tool for testing validation."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "minLength": 3, "maxLength": 10},
                "age": {"type": "integer", "minimum": 0, "maximum": 120},
                "score": {"type": "number", "minimum": 0.0},
                "is_active": {"type": "boolean"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "role": {"type": "string", "enum": ["admin", "user"]},
                "metadata": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"}
                    },
                    "required": ["key"]
                }
            },
            "required": ["name", "age"]
        }

    async def execute(self, **kwargs: Any) -> str:
        return "success"


def test_tool_schema_generation():
    """Test generating OpenAI function schema."""
    tool = DummyTool()
    schema = tool.to_schema()
    
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "dummy_tool"
    assert schema["function"]["description"] == "A tool for testing validation."
    assert "properties" in schema["function"]["parameters"]


def test_tool_validation_success():
    """Test successful parameter validation."""
    tool = DummyTool()
    
    valid_params = {
        "name": "Alice",
        "age": 30,
        "score": 95.5,
        "is_active": True,
        "tags": ["test", "agent"],
        "role": "admin",
        "metadata": {"key": "value"}
    }
    
    errors = tool.validate_params(valid_params)
    assert len(errors) == 0


def test_tool_validation_missing_required():
    """Test validation fails on missing required fields."""
    tool = DummyTool()
    
    errors = tool.validate_params({"name": "Alice"})
    assert len(errors) == 1
    assert "missing required age" in errors[0]


def test_tool_validation_type_mismatch():
    """Test validation fails on type mismatch."""
    tool = DummyTool()
    
    errors = tool.validate_params({
        "name": 123,  # Should be string
        "age": "thirty"  # Should be integer
    })
    
    assert len(errors) >= 2
    assert any("name should be string" in e for e in errors)
    assert any("age should be integer" in e for e in errors)


def test_tool_validation_constraints():
    """Test validation constraints (min/max/enum)."""
    tool = DummyTool()
    
    errors = tool.validate_params({
        "name": "Al",           # minLength is 3
        "age": 150,             # maximum is 120
        "score": -5.0,          # minimum is 0.0
        "role": "superadmin"    # not in enum
    })
    
    assert len(errors) == 4
    assert any("name must be at least 3 chars" in e for e in errors)
    assert any("age must be <= 120" in e for e in errors)
    assert any("score must be >= 0.0" in e for e in errors)
    assert any("role must be one of" in e for e in errors)


def test_tool_validation_nested_object():
    """Test validation of nested objects and arrays."""
    tool = DummyTool()
    
    errors = tool.validate_params({
        "name": "Alice",
        "age": 30,
        "tags": [1, 2],         # Should be array of strings
        "metadata": {}          # Missing required 'key'
    })
    
    assert len(errors) >= 2
    assert any("missing required metadata.key" in e for e in errors)
    assert any("tags[0] should be string" in e for e in errors)


def test_tool_bad_schema():
    """Test that a schema must be an object type."""
    class BadTool(DummyTool):
        @property
        def parameters(self) -> dict[str, Any]:
            return {"type": "array"}
            
    tool = BadTool()
    with pytest.raises(ValueError, match="Schema must be object type"):
        tool.validate_params({})
