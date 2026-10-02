"""Workflow registry: the entrypoint allowlist and the ``Workflow`` schema.

This module contains no import machinery of any kind (T-02-04). An entrypoint is a key
into ``_ENTRYPOINTS``, populated by application code calling ``register_entrypoint`` in
Python; a caller-supplied string is only ever looked up, never resolved to a module.
"""

import re
from collections.abc import Callable
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from eacp.errors import DuplicateEntrypointError
from eacp.policy import _PolicyId

# One regex governs every name the registry can emit. These names surface in error
# messages, run records and Phase 4's CLI output, so they are never log-injection or
# path-traversal shaped.
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

_Name = Annotated[str, Field(pattern=_NAME_RE.pattern)]

# Kept as a Literal (not a runtime check against available_backends()) for mypy narrowing
# at adapter call sites; tests/test_registry.py asserts it cannot drift from _BACKENDS.
BackendType = Literal["langgraph", "crewai", "ag2"]

_ENTRYPOINTS: dict[str, Callable[..., object]] = {}


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
