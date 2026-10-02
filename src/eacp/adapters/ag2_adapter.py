"""ag2 adapter.

Package:  ag2>=1.1,<2   (PyPI name `ag2`, imports as `ag2`)
NOT:      autogen / pyautogen / autogen-agentchat — four different codebases.
Install:  pip install 'eacp[ag2]'

Placeholder: real adapter logic lands in Phase 7 (AG2-01, AG2-02).
"""

from __future__ import annotations

import importlib.metadata

import ag2  # noqa: F401  proves the extra resolved; lazy via eacp.backends

from eacp.capabilities import Capability

BACKEND = "ag2"

# Distribution metadata first, so all three adapters report a version the same
# way. PackageNotFoundError subclasses ModuleNotFoundError, so it must be
# caught here — leaking it would let eacp.backends misreport an installed
# framework as a missing extra.
try:
    FRAMEWORK_VERSION = importlib.metadata.version("ag2")
except importlib.metadata.PackageNotFoundError:
    FRAMEWORK_VERSION = getattr(ag2, "__version__", "unknown")

# D-07: inline only. APPROVAL-05 scopes ag2 to inline approval for v1; true durable
# pause/resume here is a framework-level limitation deferred to v2 (ROADMAP.md).
CAPABILITIES: frozenset[Capability] = frozenset({"inline_approval"})
