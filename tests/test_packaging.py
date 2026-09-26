"""Guards the packaging invariants of PACKAGE-01/02/04."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from eacp.backends import available_backends, load_backend_module
from eacp.errors import MissingExtraError

FRAMEWORK_ROOTS = ("langgraph", "crewai", "ag2")

_PROBE = """
import json, sys
import eacp, eacp.backends
roots = {"langgraph", "crewai", "ag2"}
print(json.dumps(sorted(m for m in sys.modules if m.split(".")[0] in roots)))
"""


def test_import_eacp_does_not_import_any_framework() -> None:
    """PACKAGE-01/02: true even when the frameworks ARE installed."""
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE], capture_output=True, text=True, check=True
    )
    leaked = json.loads(proc.stdout)
    assert leaked == [], (
        f"`import eacp` eagerly imported {leaked}. An adapter is being imported "
        f"from eacp/__init__.py or eacp/adapters/__init__.py."
    )


@pytest.mark.parametrize("backend", available_backends())
def test_backend_either_loads_or_explains_itself(backend: str) -> None:
    """PACKAGE-02: no third outcome. Never a bare ModuleNotFoundError."""
    root = backend  # backend name == framework import root for all three
    installed = importlib.util.find_spec(root) is not None
    if installed:
        module = load_backend_module(backend)
        assert module.BACKEND == backend
    else:
        with pytest.raises(MissingExtraError, match=rf"eacp\[{backend}\]"):
            load_backend_module(backend)


def test_unknown_backend_is_a_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown backend"):
        load_backend_module("autogen")  # a plausible wrong guess


def test_no_adapter_is_named_autogen() -> None:
    """PITFALLS.md Pitfall 1: name things for the package, never the brand."""
    adapters = Path(__file__).parent.parent / "src" / "eacp" / "adapters"
    names = [p.name for p in adapters.glob("*_adapter.py")]
    assert "autogen_adapter.py" not in names
    assert "ag2_adapter.py" in names


def test_readme_documents_the_platform_gap() -> None:
    """PACKAGE-04."""
    readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
    low = readme.lower()
    for token in ("x86_64", "lancedb", "crewai", "arm64"):
        assert token in low, f"README platform matrix does not mention {token!r}"
