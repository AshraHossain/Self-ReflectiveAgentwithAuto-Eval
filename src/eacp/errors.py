class MissingExtraError(ImportError):
    """A backend was requested but its optional extra isn't installed."""


class PolicyError(ValueError):
    """A policy document could not be turned into a valid Policy."""


class DuplicateEntrypointError(ValueError):
    """An entrypoint name was registered more than once."""


class CapabilityError(ValueError):
    """A workflow's policy requires a capability its backend does not provide."""
