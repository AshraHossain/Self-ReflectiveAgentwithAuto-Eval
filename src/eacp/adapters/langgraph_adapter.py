"""LangGraph adapter.

Package:  langgraph>=1.2,<1.3   (PyPI name `langgraph`, imports as `langgraph`)
Install:  pip install 'eacp[langgraph]'

Placeholder: real adapter logic lands in Phase 5 (LANGGRAPH-01, LANGGRAPH-02).
"""

from __future__ import annotations

import langgraph  # noqa: F401  proves the extra resolved; lazy via eacp.backends

BACKEND = "langgraph"
FRAMEWORK_VERSION = getattr(langgraph, "__version__", "unknown")
