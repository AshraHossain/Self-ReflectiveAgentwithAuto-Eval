"""Lazy backend resolution.

This module MUST NOT import any agent framework at module scope. It stores
adapter locations as strings and imports on demand, which is what keeps
`import eacp` framework-free (PACKAGE-01) while still shipping three
adapters (PACKAGE-02).
"""

from __future__ import annotations

import importlib
from types import ModuleType

from eacp.errors import MissingExtraError

# backend name -> (adapter module, extra name, framework root module)
_BACKENDS: dict[str, tuple[str, str, str]] = {
    "langgraph": ("eacp.adapters.langgraph_adapter", "langgraph", "langgraph"),
    "crewai": ("eacp.adapters.crewai_adapter", "crewai", "crewai"),
    "ag2": ("eacp.adapters.ag2_adapter", "ag2", "ag2"),
}


def available_backends() -> tuple[str, ...]:
    """Backend names this build knows about (installed or not)."""
    return tuple(_BACKENDS)


def load_backend_module(backend: str) -> ModuleType:
    """Import a backend's adapter module, or explain which extra is missing."""
    # Allowlist lookup BEFORE any import_module call: a caller-supplied string
    # is never interpolated into an import target (T-01-04).
    try:
        module_path, extra, framework_root = _BACKENDS[backend]
    except KeyError:
        raise ValueError(
            f"Unknown backend {backend!r}. Known backends: {sorted(_BACKENDS)}"
        ) from None

    try:
        return importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        # Only translate a MISSING FRAMEWORK into an install hint. A typo'd
        # internal import inside the adapter must propagate unchanged, or a
        # real bug gets misreported as "you forgot to install an extra".
        if (exc.name or "").split(".")[0] != framework_root:
            raise
        raise MissingExtraError(
            f"Backend {backend!r} requires the {framework_root!r} package, "
            f"which is not installed. Install it with:\n"
            f"    pip install 'eacp[{extra}]'"
        ) from exc
