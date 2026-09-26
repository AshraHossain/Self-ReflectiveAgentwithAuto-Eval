"""ag2 adapter.

Package:  ag2>=1.1,<2   (PyPI name `ag2`, imports as `ag2`)
NOT:      autogen / pyautogen / autogen-agentchat — four different codebases.
Install:  pip install 'eacp[ag2]'

Placeholder: real adapter logic lands in Phase 7 (AG2-01, AG2-02).
"""

from __future__ import annotations

import ag2  # noqa: F401  proves the extra resolved; lazy via eacp.backends

BACKEND = "ag2"
FRAMEWORK_VERSION = getattr(ag2, "__version__", "unknown")
