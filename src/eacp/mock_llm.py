"""Framework-free scripted LLM (success criterion 4): ``MockLLM``, ``MockTurn``, ``MockToolCall``.

Imports stdlib plus ``eacp.engine.Usage`` only -- no agent framework, no network library, no
``os`` (the keylessness claim is "never reads a key," not "happens to work without one" --
see ``tests/test_mock_llm.py::test_mock_is_keyless``). Phases 5-7 wrap this in a per-framework
fake (``FakeMessagesListChatModel`` / a ``crewai.llms.base_llm.BaseLLM`` subclass /
``ag2.testing.TestConfig``); this module is the thing those wrappers delegate to, not a
wrapper itself.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field

from eacp.engine import Usage


@dataclass(frozen=True, slots=True)
class MockToolCall:
    name: str
    args: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MockTurn:
    text: str = ""
    tool_calls: tuple[MockToolCall, ...] = ()
    # Non-zero by default (Pitfall 5/11): a caller who scripts a turn without thinking about
    # usage at all still gets a real reading, never a silent Usage(0, 0, ...) that would make
    # every downstream budget check vacuous.
    usage: Usage = Usage(40, 12, "provider")


class MockLLM:
    """A scripted, in-process stand-in for a real provider client.

    ``loop=True`` repeats the script forever via ``itertools.cycle`` -- the shape a runaway
    agent loop takes in tests: the same turn (and the same non-zero usage) emitted on every
    call, with nothing in this class ever looking at a budget. Only the ledger stops it.
    """

    def __init__(
        self, script: Sequence[MockTurn], *, model: str = "mock", loop: bool = False
    ) -> None:
        if not script:
            raise ValueError("script must contain at least one turn")
        self.model = model
        self.calls = 0
        self._turns: Iterator[MockTurn] = itertools.cycle(script) if loop else iter(script)

    def complete(self, messages: Sequence[Mapping[str, str]]) -> MockTurn:
        try:
            turn = next(self._turns)
        except StopIteration:
            # Never let StopIteration propagate -- that would look like a Python bug
            # (e.g. a mishandled generator) rather than a test-harness misuse (script
            # exhausted without loop=True).
            raise RuntimeError(f"mock script exhausted after {self.calls} calls") from None
        self.calls += 1
        return turn
