"""WORKFLOW-01, WORKFLOW-02 and WORKFLOW-03's executable contract."""

import ast
import types
import typing
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import pytest

import eacp.registry as reg
from eacp.backends import available_backends
from eacp.errors import CapabilityError, DuplicateEntrypointError
from eacp.policy import Policy, load_yaml_mapping
from eacp.registry import (
    BackendType,
    Workflow,
    get_workflow,
    register_entrypoint,
    register_workflow,
    resolve_entrypoint,
)

PolicyYaml = Callable[..., str]

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
    monkeypatch.setattr(reg, "_WORKFLOWS", {})


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


# --- WORKFLOW-03: the capability gate ----------------------------------------------------
#
# No extra is installed in CI's core job or on the dev host, so every capability test but
# one swaps the registry's backend loader for a fake module carrying CAPABILITIES.


def _policy(policy_yaml: PolicyYaml, **overrides: Any) -> Policy:
    return Policy.model_validate(load_yaml_mapping(policy_yaml(**overrides)))


def _wf(wid: str, backend: str = "ag2", entrypoint: str = "contract_review") -> Workflow:
    return Workflow.model_validate(
        {**WF, "id": wid, "backend_type": backend, "entrypoint": entrypoint}
    )


def _fake_backends(monkeypatch: pytest.MonkeyPatch, caps: Iterable[str]) -> None:
    def load(backend: str) -> types.SimpleNamespace:
        return types.SimpleNamespace(BACKEND=backend, CAPABILITIES=frozenset(caps))

    monkeypatch.setattr(reg, "load_backend_module", load)
    register_entrypoint("contract_review", _original)


def test_capability_shortfall_rejected(
    monkeypatch: pytest.MonkeyPatch, policy_yaml: PolicyYaml
) -> None:
    _fake_backends(monkeypatch, {"inline_approval"})
    durable = _policy(policy_yaml, requires=["durable_approval"])
    with pytest.raises(CapabilityError) as excinfo:
        register_workflow(_wf("w1", "ag2"), durable)
    msg = str(excinfo.value)
    # Actionable without reading the source: what is missing, where, and what is on offer.
    assert "durable_approval" in msg and "'ag2'" in msg and "inline_approval" in msg, msg
    with pytest.raises(ValueError, match="w1"):
        get_workflow("w1")


def test_capability_match_accepted(
    monkeypatch: pytest.MonkeyPatch, policy_yaml: PolicyYaml
) -> None:
    _fake_backends(monkeypatch, {"durable_approval", "inline_approval"})
    wf = _wf("w1", "langgraph")
    register_workflow(wf, _policy(policy_yaml, requires=["durable_approval"]))
    assert get_workflow("w1") == wf


@pytest.mark.parametrize("backend", available_backends())
def test_empty_requires_accepts_any_backend(
    monkeypatch: pytest.MonkeyPatch, policy_yaml: PolicyYaml, backend: str
) -> None:
    _fake_backends(monkeypatch, set())
    register_workflow(_wf("w1", backend), _policy(policy_yaml, requires=[]))
    assert get_workflow("w1").backend_type == backend


def test_adapter_declaring_unknown_capability_rejected(
    monkeypatch: pytest.MonkeyPatch, policy_yaml: PolicyYaml
) -> None:
    _fake_backends(monkeypatch, {"durable_approval", "teleportation"})
    with pytest.raises(CapabilityError, match="teleportation"):
        register_workflow(_wf("w1", "langgraph"), _policy(policy_yaml, requires=[]))


def test_gate_order_unknown_entrypoint_wins(policy_yaml: PolicyYaml) -> None:
    # The REAL loader: no extra is installed here, so a wrong gate order raises
    # MissingExtraError (an ImportError, not a ValueError) and this test genuinely fails.
    register_entrypoint("contract_review", _original)
    with pytest.raises(ValueError, match="not_registered"):
        register_workflow(
            _wf("w1", "crewai", entrypoint="not_registered"), _policy(policy_yaml, requires=[])
        )


def test_policy_id_mismatch_rejected(
    monkeypatch: pytest.MonkeyPatch, policy_yaml: PolicyYaml
) -> None:
    _fake_backends(monkeypatch, {"durable_approval", "inline_approval"})
    with pytest.raises(ValueError, match=r"different.*demo|demo.*different"):
        register_workflow(_wf("w1"), _policy(policy_yaml, policy_id="different"))
    with pytest.raises(ValueError, match="w1"):
        get_workflow("w1")


def test_duplicate_workflow_registration_rejected(
    monkeypatch: pytest.MonkeyPatch, policy_yaml: PolicyYaml
) -> None:
    _fake_backends(monkeypatch, {"durable_approval", "inline_approval"})
    policy = _policy(policy_yaml, requires=[])
    original = _wf("w1", "langgraph")
    register_workflow(original, policy)
    # T-02-13: an existing id cannot be re-pointed at another backend.
    with pytest.raises(ValueError, match="w1"):
        register_workflow(_wf("w1", "crewai"), policy)
    assert get_workflow("w1") == original
