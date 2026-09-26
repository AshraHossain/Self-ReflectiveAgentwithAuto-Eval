"""Enterprise Agent Control Plane.

Importing this package MUST NOT pull in langgraph, crewai, or ag2 (PACKAGE-01).
Adapters load on demand via `eacp.backends.load_backend_module`.

Keep this module version-only. Do not add convenience re-exports of adapter
classes: one such re-export makes `import eacp` raise `ModuleNotFoundError`
naming a framework for every core-only user, with a perfectly correct
pyproject.toml. If ergonomic re-exports are wanted later, use PEP 562
module-level `__getattr__` so they stay lazy.
"""

from eacp.__about__ import __version__

__all__ = ["__version__"]
