"""Base class for agent tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """A callable capability exposed to an agent."""

    _TYPE_MAP: dict[str, type[Any] | tuple[type[Any], ...]] = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name used in function calls."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable tool description."""

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema object for tool parameters."""

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool and return a text result."""

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """Validate tool parameters against the declared JSON schema."""
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            return ["tool schema must be an object"]
        return self._validate(params, {**schema, "type": "object"}, "")

    def _validate(self, val: Any, schema: dict[str, Any], path: str) -> list[str]:
        t_raw = schema.get("type")
        t = t_raw if isinstance(t_raw, str) else ""
        label = path or "parameter"
        expected = self._TYPE_MAP.get(t)
        if expected is not None and not isinstance(val, expected):
            return [f"{label} should be {t}"]

        errors: list[str] = []
        if "enum" in schema and val not in schema["enum"]:
            errors.append(f"{label} must be one of {schema['enum']}")
        if t == "string":
            if "minLength" in schema and len(val) < schema["minLength"]:
                errors.append(f"{label} must be at least {schema['minLength']} chars")
            if "maxLength" in schema and len(val) > schema["maxLength"]:
                errors.append(f"{label} must be at most {schema['maxLength']} chars")
        if t == "object":
            props = schema.get("properties", {})
            for key in schema.get("required", []):
                if key not in val:
                    errors.append(f"missing required {path + '.' + key if path else key}")
            for key, nested in val.items():
                if key in props:
                    errors.extend(self._validate(nested, props[key], f"{path}.{key}" if path else key))
        return errors

    def to_schema(self) -> dict[str, Any]:
        """Return an OpenAI-compatible function schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
