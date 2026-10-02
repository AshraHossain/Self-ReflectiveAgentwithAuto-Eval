"""WORKFLOW-01, WORKFLOW-02 and WORKFLOW-03's executable contract."""

import ast
import typing
from pathlib import Path
from typing import Any

import pytest

import eacp.registry as reg
from eacp.backends import available_backends
from eacp.errors import DuplicateEntrypointError
from eacp.registry import (
    BackendType,
    Workflow,
    register_entrypoint,
    resolve_entrypoint,
)

REGISTRY_SRC = Path(reg.__file__)

WF: dict[str, Any] = {
    "id": "contract_review",
    "name": "Contract review",
    "description": "Ingest, analyse, recommend, send behind an approval gate",
    "backend_type": "langgraph",
    "entrypoint": "contract_review",
    "policy_id": "demo",
}


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    # The allowlist is module-global; every test gets a fresh one and monkeypatch restores
    # the original afterwards, so test order can never matter.
    monkeypatch.setattr(reg, "_ENTRYPOINTS", {})


def _original() -> str:
    return "original"


def _other() -> str:
    return "hijacked"


# --- WORKFLOW-01: the schema -------------------------------------------------------------


@pytest.mark.parametrize("field", ["nodes", "agents", "edges"])
def test_topology_fields_rejected(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        Workflow.model_validate({**WF, field: ["a", "b"]})


def test_workflow_schema_fields() -> None:
    assert set(Workflow.model_fields) == set(WF)
    assert all(info.is_required() for info in Workflow.model_fields.values())
    Workflow.model_validate(WF)
    for field in WF:
        with pytest.raises(ValueError, match=field):
            Workflow.model_validate({k: v for k, v in WF.items() if k != field})


def test_backend_literal_matches_backends_module() -> None:
    assert set(typing.get_args(BackendType)) == set(available_backends())


# --- WORKFLOW-02: the entrypoint allowlist -----------------------------------------------


@pytest.mark.parametrize("name", ["os.system", "../etc", "Alpha", "", "a" * 65])
def test_entrypoint_name_charset(name: str) -> None:
    with pytest.raises(ValueError, match="must match"):
        register_entrypoint(name, _original)
    assert name not in reg._ENTRYPOINTS


def test_duplicate_entrypoint_registration_rejected() -> None:
    register_entrypoint("contract_review", _original)
    with pytest.raises(DuplicateEntrypointError, match="contract_review"):
        register_entrypoint("contract_review", _other)
    # T-02-05: a raise that left the registry mutated would be worse than no raise.
    assert resolve_entrypoint("contract_review")() == "original"


def test_unregistered_entrypoint_rejected() -> None:
    register_entrypoint("contract_review", _original)
    with pytest.raises(ValueError, match=r"'nope'.*contract_review"):
        resolve_entrypoint("nope")


# --- T-02-04: no import machinery, asserted from the syntax tree, not a text grep --------

_MACHINERY = {"importlib", "pkgutil", "runpy"}
_BARE = {"__import__", "exec", "eval", "compile"}
_FRAMEWORKS = {"langgraph", "crewai", "ag2", "langchain", "langchain_core"}


def test_registry_has_no_import_machinery() -> None:
    hits: list[str] = []
    for node in ast.walk(ast.parse(REGISTRY_SRC.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            hits += [a.name for a in node.names if a.name.split(".")[0] in _MACHINERY | _FRAMEWORKS]
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in _MACHINERY | _FRAMEWORKS:
                hits.append(node.module or "")
        elif isinstance(node, ast.Name) and node.id in _MACHINERY | _BARE:
            hits.append(node.id)
        elif isinstance(node, ast.Attribute):
            # Only attributes ON an import-machinery module: `re.compile` is not a hit.
            base = node.value
            if isinstance(base, ast.Name) and base.id in _MACHINERY | {"builtins"}:
                hits.append(f"{base.id}.{node.attr}")
    assert not hits, f"T-02-04: import machinery or a framework reached registry.py: {hits}"
