"""Framework adapters.

Importing this package MUST NOT pull in any agent framework. Adapter modules
are loaded on demand by `eacp.backends.load_backend_module`. Do not add
imports here — doing so breaks PACKAGE-01.
"""
