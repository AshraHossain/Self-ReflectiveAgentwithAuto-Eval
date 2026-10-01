"""Shared fixtures. Imports nothing from eacp at module scope: this file is collected
for the whole tests/ directory, so a missing eacp module must not break collection."""

import json
from collections.abc import Callable
from typing import Any

import pytest

PolicyYaml = Callable[..., str]

_VALID_POLICY: dict[str, Any] = {
    "policy_id": "demo",
    "version": 1,
    "max_tokens_per_run": 100,
    "max_cost_per_day": 25,
    "allowed_tools": ["search", "summarize"],
    "forbidden_tools": ["send_email"],
    "required_approval_nodes": ["send"],
    "compliance_tags": ["soc2", "gdpr"],
    "requires": [],
}


@pytest.fixture
def policy_yaml() -> PolicyYaml:
    """Build a valid policy YAML string. Keyword overrides replace field values;
    ``drop=("field", ...)`` removes fields. For raw YAML (``yes``, ``25.00``), edit the text."""

    def build(drop: tuple[str, ...] = (), **overrides: Any) -> str:
        doc = {**_VALID_POLICY, **overrides}
        for name in drop:
            doc.pop(name)
        # JSON values are valid YAML flow scalars/sequences, so one line per key is YAML.
        return "".join(f"{key}: {json.dumps(value)}\n" for key, value in doc.items())

    return build
