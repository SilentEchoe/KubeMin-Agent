"""YAML validator tool for KubeMin Workflow definitions."""

from __future__ import annotations

from typing import Any

from kubemin_agent.agent.tools.base import Tool


class YAMLValidatorTool(Tool):
    """Validate YAML syntax and KubeMin Workflow structure."""

    @property
    def name(self) -> str:
        return "validate_yaml"

    @property
    def description(self) -> str:
        return (
            "Validate a YAML string for syntax correctness and KubeMin Workflow "
            "structural requirements (apiVersion, kind, metadata.name, spec). "
            "Returns validation result with specific error details."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The YAML content to validate.",
                },
            },
            "required": ["content"],
        }

    async def execute(self, *, content: str) -> str:
        try:
            import yaml
        except ImportError:
            return "Error: PyYAML is not installed. Run: pip install pyyaml"

        # 1. Syntax validation
        try:
            docs = list(yaml.safe_load_all(content))
        except yaml.YAMLError as e:
            return f"INVALID: YAML syntax error:\n{e}"

        if not docs:
            return "INVALID: empty YAML document"

        # Remove None docs (from trailing ---)
        docs = [d for d in docs if d is not None]
        if not docs:
            return "INVALID: no YAML documents found (all empty)"

        # 2. Structural validation for each document
        errors: list[str] = []
        warnings: list[str] = []

        for i, doc in enumerate(docs):
            prefix = f"[doc {i + 1}] " if len(docs) > 1 else ""

            if not isinstance(doc, dict):
                errors.append(f"{prefix}document is not a mapping (got {type(doc).__name__})")
                continue

            # Required top-level fields
            if "apiVersion" not in doc:
                errors.append(f"{prefix}missing required field: apiVersion")
            if "kind" not in doc:
                errors.append(f"{prefix}missing required field: kind")

            # metadata.name
            metadata = doc.get("metadata")
            if not metadata:
                errors.append(f"{prefix}missing required field: metadata")
            elif not isinstance(metadata, dict):
                errors.append(f"{prefix}metadata should be a mapping")
            elif "name" not in metadata:
                errors.append(f"{prefix}missing required field: metadata.name")

            # spec
            if "spec" not in doc:
                warnings.append(f"{prefix}missing field: spec (usually required)")

            # spec.components (KubeMin workflow specific)
            spec = doc.get("spec", {})
            if isinstance(spec, dict) and "components" in spec:
                components = spec["components"]
                if not isinstance(components, list):
                    errors.append(f"{prefix}spec.components should be a list")
                else:
                    for j, comp in enumerate(components):
                        if not isinstance(comp, dict):
                            errors.append(f"{prefix}spec.components[{j}] should be a mapping")
                        elif "name" not in comp:
                            warnings.append(f"{prefix}spec.components[{j}] missing 'name'")

        # Build result
        parts: list[str] = []

        if errors:
            parts.append("INVALID")
            parts.append("\nErrors:")
            for err in errors:
                parts.append(f"  - {err}")
        else:
            parts.append("VALID")

        if warnings:
            parts.append("\nWarnings:")
            for warn in warnings:
                parts.append(f"  - {warn}")

        if not errors:
            doc_count = len(docs)
            kinds = [d.get("kind", "unknown") for d in docs if isinstance(d, dict)]
            parts.append(f"\nSummary: {doc_count} document(s), kinds: {', '.join(kinds)}")

        return "\n".join(parts)
