"""Workflow registry: the entrypoint allowlist, the ``Workflow`` schema, and the capability gate.

This module contains no import machinery of any kind (T-02-04). An entrypoint is a key
into ``_ENTRYPOINTS``, populated by application code calling ``register_entrypoint`` in
Python; a caller-supplied string is only ever looked up, never resolved to a module. The
adapters are reached only through ``eacp.backends.load_backend_module``, the package's
single lazy-import chokepoint.

The registry is process-local and deliberately NOT persisted (D-13): registration happens
in Python at startup. The ``runs`` table is self-contained -- it carries ``workflow_id``,
``backend_type``, ``policy_id`` and ``policy_hash`` as columns, not foreign keys -- so
Phase 4's second-process approval CLI reads run history without ever needing this registry.
"""

import re
from collections.abc import Callable
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from eacp.backends import available_backends, load_backend_module
from eacp.capabilities import KNOWN_CAPABILITIES
from eacp.errors import CapabilityError, DuplicateEntrypointError
from eacp.policy import Policy, _PolicyId

# One regex governs every name the registry can emit. These names surface in error
# messages, run records and Phase 4's CLI output, so they are never log-injection or
# path-traversal shaped.
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

_Name = Annotated[str, Field(pattern=_NAME_RE.pattern)]

# Kept as a Literal (not a runtime check against available_backends()) for mypy narrowing
# at adapter call sites; tests/test_registry.py asserts it cannot drift from _BACKENDS.
BackendType = Literal["langgraph", "crewai", "ag2"]

_ENTRYPOINTS: dict[str, Callable[..., object]] = {}
_WORKFLOWS: dict[str, "Workflow"] = {}


class Workflow(BaseModel):
    """A registered workflow: exactly the six WORKFLOW-01 fields, all required.

    ``entrypoint`` is an opaque pointer to user-authored code, never a description of it.
    There is deliberately no ``nodes``, ``agents`` or ``edges`` field: topology lives in the
    code the entrypoint names, and ``extra="forbid"`` turns any such key into a rejection
    rather than a silently ignored one.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: _Name
    name: str
    description: str
    backend_type: BackendType
    entrypoint: _Name
    policy_id: _PolicyId


def register_entrypoint(name: str, fn: Callable[..., object]) -> None:
    """Add a workflow entrypoint to the allowlist. Re-registration is refused (T-02-05)."""
    if not _NAME_RE.fullmatch(name):
        raise ValueError(f"Invalid entrypoint name {name!r}: must match {_NAME_RE.pattern}")
    if name in _ENTRYPOINTS:
        raise DuplicateEntrypointError(f"Entrypoint {name!r} is already registered")
    _ENTRYPOINTS[name] = fn


def resolve_entrypoint(name: str) -> Callable[..., object]:
    """Look up a registered entrypoint. A dict lookup only -- never an import."""
    try:
        return _ENTRYPOINTS[name]
    except KeyError:
        raise ValueError(
            f"Unknown entrypoint {name!r}. Registered: {sorted(_ENTRYPOINTS)}"
        ) from None


def register_workflow(workflow: Workflow, policy: Policy) -> None:
    """Register a workflow under the policy that governs it, or fail loudly (WORKFLOW-03).

    Gates run cheapest-and-purest first, and the order is load-bearing: (1) entrypoint in
    the allowlist, (2) known backend name -- both pure dict lookups -- and only then (3)
    ``load_backend_module`` and the capability comparison. Step 3 is the only one that can
    raise about installation, so a misspelled entrypoint never reports a missing extra.

    Honesty gap (T-02-12, transferred to Phase 7): nothing here verifies that a backend
    declaring durable_approval actually delivers it. CONFORM-01's parametrized suite owns
    that: "for each adapter, durable approval is declared if and only if a run survives a
    process exit".
    """
    if workflow.id in _WORKFLOWS:
        raise ValueError(f"Workflow {workflow.id!r} is already registered")  # T-02-13
    if policy.policy_id != workflow.policy_id:
        # T-02-14: otherwise run records pin a hash from a policy the workflow doesn't name.
        raise ValueError(
            f"Workflow {workflow.id!r} names policy {workflow.policy_id!r} but was "
            f"registered with policy {policy.policy_id!r}"
        )
    resolve_entrypoint(workflow.entrypoint)  # (1)
    if workflow.backend_type not in available_backends():  # (2)
        raise ValueError(
            f"Unknown backend {workflow.backend_type!r}. Known backends: {available_backends()}"
        )
    declared = frozenset(load_backend_module(workflow.backend_type).CAPABILITIES)  # (3)
    # mypy only checks an adapter whose framework is installed; this closes the gap.
    unknown = declared - KNOWN_CAPABILITIES
    if unknown:
        raise CapabilityError(
            f"Adapter {workflow.backend_type!r} declares unknown capabilities: {sorted(unknown)}"
        )
    missing = set(policy.requires) - declared
    if missing:
        raise CapabilityError(
            f"Workflow {workflow.id!r} requires {sorted(missing)}, which backend "
            f"{workflow.backend_type!r} does not provide. It provides: {sorted(declared)}."
        )
    _WORKFLOWS[workflow.id] = workflow


def get_workflow(workflow_id: str) -> Workflow:
    """Look up a registered workflow by id."""
    try:
        return _WORKFLOWS[workflow_id]
    except KeyError:
        raise ValueError(
            f"Unknown workflow {workflow_id!r}. Registered: {sorted(_WORKFLOWS)}"
        ) from None
