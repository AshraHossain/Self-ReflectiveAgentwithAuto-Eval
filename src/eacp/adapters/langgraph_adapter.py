"""LangGraph adapter.

Package:  langgraph>=1.2,<1.3   (PyPI name `langgraph`, imports as `langgraph`)
Install:  pip install 'eacp[langgraph]'

Placeholder: real adapter logic lands in Phase 5 (LANGGRAPH-01, LANGGRAPH-02).
"""

from __future__ import annotations

import importlib.metadata

import langgraph  # noqa: F401  proves the extra resolved; lazy via eacp.backends

BACKEND = "langgraph"

# Distribution metadata, not a module attribute: langgraph 1.x exposes no
# `__version__`. PackageNotFoundError subclasses ModuleNotFoundError, so it
# must be caught here — leaking it would let eacp.backends misreport an
# installed framework as a missing extra.
try:
    FRAMEWORK_VERSION = importlib.metadata.version("langgraph")
except importlib.metadata.PackageNotFoundError:
    FRAMEWORK_VERSION = getattr(langgraph, "__version__", "unknown")
