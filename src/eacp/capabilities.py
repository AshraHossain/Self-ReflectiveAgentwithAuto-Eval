"""The v1 adapter capability vocabulary. Core code: no agent framework, no eacp import.

Governing rule: *a capability name earns its place only when at least one shipped
adapter genuinely lacks it.* Add a new name in the same commit as the adapter that
lacks it.

Evaluated and rejected (02-RESEARCH.md Finding 4) -- all three adapters are expected
to have each of these, which makes them gates that can never fire:
``tool_call_interception``, ``pre_call_admission``, ``delegation_tool_enforcement``,
``provider_token_usage``.

``inline_approval`` is kept even though every adapter has it, so the capability matrix
has more than one column and the vocabulary is self-describing.
"""

from typing import Literal, get_args

Capability = Literal["durable_approval", "inline_approval"]

KNOWN_CAPABILITIES: frozenset[str] = frozenset(get_args(Capability))
