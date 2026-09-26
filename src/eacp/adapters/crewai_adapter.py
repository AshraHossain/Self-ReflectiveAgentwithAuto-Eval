"""CrewAI adapter.

Package:  crewai>=1.15,<2   (PyPI name `crewai`, imports as `crewai`)
Install:  pip install 'eacp[crewai]'
Platform: not installable on macOS x86_64 — see README "Platform support".

Placeholder: real adapter logic lands in Phase 6 (CREWAI-01, CREWAI-02, CREWAI-03).
"""

from __future__ import annotations

import importlib.metadata

import crewai  # noqa: F401  proves the extra resolved; lazy via eacp.backends

BACKEND = "crewai"

# Distribution metadata first, so all three adapters report a version the same
# way. PackageNotFoundError subclasses ModuleNotFoundError, so it must be
# caught here — leaking it would let eacp.backends misreport an installed
# framework as a missing extra.
try:
    FRAMEWORK_VERSION = importlib.metadata.version("crewai")
except importlib.metadata.PackageNotFoundError:
    FRAMEWORK_VERSION = getattr(crewai, "__version__", "unknown")
