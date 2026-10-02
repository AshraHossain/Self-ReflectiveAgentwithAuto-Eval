"""Policy YAML -> validated, content-addressed ``Policy``. The phase's only trust boundary.

This module is the single PyYAML entry point in ``src/``. Plain ``yaml.safe_load`` is not
used anywhere: it blocks code execution but silently keeps the LAST of two repeated keys.
"""

import hashlib
import json
from collections import Counter
from collections.abc import Hashable
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Any

# PyYAML ships no type information and types-PyYAML is not in the lock; adding a
# dependency is out of scope for this plan, so the untyped boundary is marked here.
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, field_validator

from eacp.capabilities import Capability
from eacp.errors import PolicyError

# T-02-02: bounds YAML alias amplification. Measured: 220 bytes expanded to 531,441 nodes
# under safe_load. The cap is checked against UTF-8 length BEFORE the parser sees anything.
MAX_POLICY_BYTES = 64 * 1024
_TOO_BIG = f"policy document exceeds {MAX_POLICY_BYTES} bytes"

_COST_EXP = Decimal("0.000001")


class _StrictLoader(yaml.SafeLoader):  # type: ignore[misc]
    """SafeLoader that additionally refuses repeated mapping keys (T-02-01)."""


def _no_duplicate_keys(loader: Any, node: Any, deep: bool = False) -> dict[Any, Any]:
    # Compare CONSTRUCTED keys, so `a` vs `'a'` or an aliased key cannot slip past.
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, Hashable):
            continue  # base construct_mapping raises its own "unhashable key" error
        if key in seen:
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate key {key!r}", key_node.start_mark
            )
        seen.add(key)
    mapping: dict[Any, Any] = yaml.SafeLoader.construct_mapping(loader, node, deep)
    return mapping


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys)


def load_yaml_mapping(text: str) -> dict[str, Any]:
    """Parse one YAML document that must be a mapping. Every rejection is ``PolicyError``."""
    if len(text.encode("utf-8")) > MAX_POLICY_BYTES:
        raise PolicyError(_TOO_BIG)
    try:
        data = yaml.load(text, Loader=_StrictLoader)
    except yaml.YAMLError as exc:
        raise PolicyError(f"invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise PolicyError(f"policy document must be a YAML mapping, got {type(data).__name__}")
    return data


_PolicyId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]


class Policy(BaseModel):
    """A validated policy. Every field is required: absence never means unlimited (D-08/D-12).

    Strictness is per-field (``StrictInt``), never model-wide: model-level strict mode also
    rejects a plain YAML ``100`` for the Decimal cost field (02-RESEARCH.md Finding 2).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: _PolicyId
    version: Annotated[StrictInt, Field(ge=1)]
    max_tokens_per_run: Annotated[StrictInt, Field(ge=1)]
    max_cost_per_day: Annotated[Decimal, Field(ge=Decimal(0))]
    # Ordered lists, never sets: a set serializes in hash-seed-dependent order (Finding 1).
    allowed_tools: list[str]
    forbidden_tools: list[str]
    required_approval_nodes: list[str]
    compliance_tags: list[str]
    requires: list[Capability]

    @field_validator("max_cost_per_day")
    @classmethod
    def _quantize(cls, v: Decimal) -> Decimal:
        # Quantize, never normalize: Decimal("100").normalize() serializes as "1E+2".
        try:
            return v.quantize(_COST_EXP)
        except InvalidOperation:
            raise ValueError("cost is out of range") from None

    @field_validator(
        "allowed_tools", "forbidden_tools", "required_approval_nodes", "compliance_tags", "requires"
    )
    @classmethod
    def _sorted_unique(cls, v: list[str]) -> list[str]:
        dupes = sorted(item for item, n in Counter(v).items() if n > 1)
        if dupes:
            raise ValueError(f"duplicate entries are not allowed: {dupes}")
        return sorted(v)  # author's list order must not affect the content hash


# D-11: identity, not content. The hash answers "did the enforceable rules change between
# v1 and v2?"; a version bump that moved it would destroy that property. Nothing is lost:
# run records carry policy_id and policy_hash as separate columns.
_IDENTITY_FIELDS: frozenset[str] = frozenset({"policy_id", "version"})


def _canonical(payload: dict[str, Any]) -> str:
    """The single canonical JSON form. Phase 4's audit log reuses this; never write a second."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def policy_hash(policy: Policy) -> str:
    """SHA-256 hex digest of the policy's enforceable content (POLICY-04).

    This is content addressing, not a signature or a MAC: it proves which rules governed a
    run, not who authored them.

    Two traps:
    - pydantic's direct-to-JSON-string serializer has no sort-keys parameter (2.12.5) and
      emits field-declaration order, so reordering the class body would change every
      stored hash. Hence the dict dump + stdlib ``json`` with ``sort_keys``.
    - NEVER narrow the payload with exclude_unset / exclude_defaults / exclude_none: once an
      optional field exists, an absent value would hash differently from an explicit null.
    """
    payload = policy.model_dump(mode="json", exclude=set(_IDENTITY_FIELDS))
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _render(exc: ValidationError) -> str:
    # include_url=False drops the per-error docs link; `input` is deliberately not rendered.
    return "; ".join(
        f"{'.'.join(str(part) for part in err['loc']) or '<root>'}: {err['msg']}"
        for err in exc.errors(include_url=False)
    )


def load_policy_file(path: str | Path) -> Policy:
    """Read, parse and validate a policy file. Every failure is ``PolicyError``."""
    path = Path(path)
    try:
        with path.open("rb") as fh:
            raw = fh.read(MAX_POLICY_BYTES + 1)  # never read more than the cap into memory
    except OSError as exc:
        raise PolicyError(f"{path}: cannot read policy file: {exc.strerror}") from None
    if len(raw) > MAX_POLICY_BYTES:
        raise PolicyError(f"{path}: {_TOO_BIG}")
    try:
        return Policy.model_validate(load_yaml_mapping(raw.decode("utf-8")))
    except UnicodeDecodeError:
        raise PolicyError(f"{path}: policy file is not valid UTF-8") from None
    except PolicyError as exc:
        raise PolicyError(f"{path}: {exc}") from exc
    except ValidationError as exc:
        raise PolicyError(f"{path}: invalid policy: {_render(exc)}") from None
