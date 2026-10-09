from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # TYPE_CHECKING-only: a real import here would cycle (policy.py imports errors.py for
    # PolicyError, and engine.py imports policy.py), so errors.py importing engine.py at
    # module scope would close the loop. The type checker still sees the real type.
    from eacp.engine import Decision


class MissingExtraError(ImportError):
    """A backend was requested but its optional extra isn't installed."""


class PolicyError(ValueError):
    """A policy document could not be turned into a valid Policy."""


class DuplicateEntrypointError(ValueError):
    """An entrypoint name was registered more than once."""


class CapabilityError(ValueError):
    """A workflow's policy requires a capability its backend does not provide."""


class PolicyDenied(Exception):
    """A governance halt: ``decide()`` returned a deny. First raised by Plan 03-02's
    ``SQLiteBudgetLedger.admit``.

    Based on ``Exception``, not ``ValueError``: a caller must be able to catch a
    governance halt separately from a bad-value bug without one accidentally swallowing
    the other in a shared ``except`` clause.
    """

    def __init__(self, decision: "Decision") -> None:
        self.decision = decision
        super().__init__(
            f"policy denied: rule={decision.rule!r} limit={decision.limit!r} "
            f"observed={decision.observed!r}"
        )
