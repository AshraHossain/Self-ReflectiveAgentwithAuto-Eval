"""POLICY-01, POLICY-02 and POLICY-04's executable contract."""

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from eacp.errors import PolicyError
from eacp.policy import (
    _IDENTITY_FIELDS,
    MAX_POLICY_BYTES,
    Policy,
    _canonical,
    load_policy_file,
    load_yaml_mapping,
    policy_hash,
)

PolicyYaml = Callable[..., str]

ALL_FIELDS = (
    "policy_id",
    "version",
    "max_tokens_per_run",
    "max_cost_per_day",
    "allowed_tools",
    "forbidden_tools",
    "required_approval_nodes",
    "compliance_tags",
    "requires",
)


def _load(tmp_path: Path, text: str) -> Policy:
    path = tmp_path / "policy.yaml"
    path.write_text(text, encoding="utf-8")
    return load_policy_file(path)


def test_valid_baseline_loads(tmp_path: Path, policy_yaml: PolicyYaml) -> None:
    p = _load(tmp_path, policy_yaml())
    assert p.policy_id == "demo"
    assert p.max_tokens_per_run == 100
    assert p.max_cost_per_day == Decimal("25")
    assert p.compliance_tags == ["gdpr", "soc2"]  # sorted by the validator
    assert p.requires == []


def test_unknown_field_rejected(tmp_path: Path, policy_yaml: PolicyYaml) -> None:
    with pytest.raises(PolicyError, match="bogus_field"):
        _load(tmp_path, policy_yaml(bogus_field=3))


@pytest.mark.parametrize(
    ("text", "found"),
    [("- a\n- b\n", "list"), ("just text\n", "str"), ("", "NoneType")],
    ids=["list", "scalar", "empty"],
)
def test_non_mapping_root_rejected(text: str, found: str) -> None:
    with pytest.raises(PolicyError, match=f"got {found}"):
        load_yaml_mapping(text)


def test_duplicate_key_rejected(tmp_path: Path, policy_yaml: PolicyYaml) -> None:
    # T-02-01: under plain safe_load the second value silently wins (100 -> 999999).
    text = policy_yaml() + "max_tokens_per_run: 999999\n"
    result: object = None
    with pytest.raises(PolicyError, match="max_tokens_per_run"):
        result = load_yaml_mapping(text)
    assert result is None  # the loader did not hand back the overriding value
    with pytest.raises(PolicyError, match="max_tokens_per_run"):
        _load(tmp_path, text)


def test_duplicate_key_rejected_in_nested_and_quoted_forms() -> None:
    with pytest.raises(PolicyError, match="duplicate key"):
        load_yaml_mapping("a: 1\n'a': 2\n")
    with pytest.raises(PolicyError, match="duplicate key"):
        load_yaml_mapping("outer:\n  k: 1\n  k: 2\n")


def test_python_tag_rejected() -> None:
    with pytest.raises(PolicyError):
        load_yaml_mapping("policy_id: !!python/object/apply:os.system ['echo pwned']\n")


def test_oversized_document_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    # T-02-02: an alias bomb padded one byte past the cap. The parser must never see it.
    bomb = "a: &a [x, x, x, x, x, x, x, x, x]\n" + "".join(
        f"{c}: &{c} [*{p}, *{p}, *{p}, *{p}, *{p}, *{p}, *{p}, *{p}, *{p}]\n"
        for p, c in zip("abcdefgh", "bcdefghi", strict=True)
    )
    text = bomb + "#" * (MAX_POLICY_BYTES + 1 - len(bomb.encode("utf-8")))
    assert len(text.encode("utf-8")) == MAX_POLICY_BYTES + 1

    def parser_must_not_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("the YAML parser ran on an oversized document")

    monkeypatch.setattr("yaml.load", parser_must_not_run)
    with pytest.raises(PolicyError, match=str(MAX_POLICY_BYTES)):
        load_yaml_mapping(text)


def test_oversized_file_rejected(tmp_path: Path) -> None:
    with pytest.raises(PolicyError, match=str(MAX_POLICY_BYTES)):
        _load(tmp_path, "a: " + "x" * MAX_POLICY_BYTES)


@pytest.mark.parametrize("field", ALL_FIELDS)
def test_every_limit_field_is_required(
    tmp_path: Path, policy_yaml: PolicyYaml, field: str
) -> None:
    # D-08 / D-12: absence is never "unlimited" or "demands nothing".
    with pytest.raises(PolicyError, match=field):
        _load(tmp_path, policy_yaml(drop=(field,)))


def test_yaml_bool_rejected_for_int_limit(tmp_path: Path, policy_yaml: PolicyYaml) -> None:
    text = policy_yaml().replace("max_tokens_per_run: 100", "max_tokens_per_run: yes")
    with pytest.raises(PolicyError, match="max_tokens_per_run"):
        _load(tmp_path, text)
    # The other half: a plain YAML integer is still a valid cost (model-level strict breaks this).
    assert "max_cost_per_day: 25\n" in policy_yaml()
    assert _load(tmp_path, policy_yaml()).max_cost_per_day == Decimal("25")


def test_unknown_capability_rejected(tmp_path: Path, policy_yaml: PolicyYaml) -> None:
    with pytest.raises(PolicyError, match=r"requires\.0"):
        _load(tmp_path, policy_yaml(requires=["durable_pause"]))


def test_duplicate_list_entries_rejected(tmp_path: Path, policy_yaml: PolicyYaml) -> None:
    with pytest.raises(PolicyError, match="allowed_tools"):
        _load(tmp_path, policy_yaml(allowed_tools=["search", "search"]))


def test_error_message_carries_no_environment_paths(
    tmp_path: Path, policy_yaml: PolicyYaml
) -> None:
    # T-02-09: the user's own policy path is fine; interpreter/env locations are not.
    with pytest.raises(PolicyError) as info:
        _load(tmp_path, policy_yaml(bogus_field=3))
    message = str(info.value)
    for leak in (sys.prefix, sys.executable, "site-packages"):
        assert leak not in message


# --- POLICY-04: canonical content hash -------------------------------------------------

_HASH_A = """
policy_id: alpha
version: 1
max_tokens_per_run: 100
max_cost_per_day: 25.00
allowed_tools: [search, summarize]
forbidden_tools: [send_email]
required_approval_nodes: [send]
compliance_tags: [soc2, gdpr]
requires: [durable_approval]
"""

# Same rules: different key order, list order, policy_id, version, and 25.0 vs 25.00.
_HASH_B = """
requires: [durable_approval]
compliance_tags: [gdpr, soc2]
version: 7
allowed_tools: [summarize, search]
max_cost_per_day: 25.0
forbidden_tools: [send_email]
policy_id: beta
required_approval_nodes: [send]
max_tokens_per_run: 100
"""


def _policy(text: str) -> Policy:
    return Policy.model_validate(load_yaml_mapping(text))


def test_hash_is_content_addressed() -> None:
    a, b = policy_hash(_policy(_HASH_A)), policy_hash(_policy(_HASH_B))
    assert a == b
    assert len(a) == 64 and set(a) <= set("0123456789abcdef")


@pytest.mark.parametrize(
    ("field", "new_value", "moves_hash"),
    [
        ("max_tokens_per_run", 101, True),
        ("max_cost_per_day", "26", True),
        ("allowed_tools", ["search"], True),
        ("forbidden_tools", [], True),
        ("required_approval_nodes", [], True),
        ("compliance_tags", ["soc2"], True),
        ("requires", [], True),
        # D-11: identity, not content. A version bump must not look like a rule change.
        ("policy_id", "renamed", False),
        ("version", 2, False),
    ],
)
def test_hash_changes_when_a_limit_changes(field: str, new_value: Any, moves_hash: bool) -> None:
    base = _policy(_HASH_A)
    changed = Policy.model_validate({**base.model_dump(mode="json"), field: new_value})
    assert (policy_hash(changed) != policy_hash(base)) is moves_hash


def test_hashed_key_set_is_pinned() -> None:
    # T-02-08: a new field must be deliberately classified as content or identity.
    p = _policy(_HASH_A)
    payload = {k: v for k, v in p.model_dump(mode="json").items() if k not in _IDENTITY_FIELDS}
    assert set(payload) == {
        "max_tokens_per_run",
        "max_cost_per_day",
        "allowed_tools",
        "forbidden_tools",
        "required_approval_nodes",
        "compliance_tags",
        "requires",
    }
    # Tie the literal to what policy_hash actually digests, not a re-derivation of it.
    assert policy_hash(p) == hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def test_hash_is_stable_across_processes() -> None:
    # T-02-07: an unordered collection field serialized differently under each hash seed.
    p = _policy(_HASH_A)
    child = (
        "import json, sys\n"
        "from eacp.policy import Policy, policy_hash\n"
        "print(policy_hash(Policy.model_validate(json.load(sys.stdin))))\n"
    )
    blob = json.dumps(p.model_dump(mode="json"))
    digests = {
        subprocess.run(
            [sys.executable, "-c", child],
            input=blob,
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        ).stdout.strip()
        for seed in ("0", "1", "2", "3")
    }
    assert digests == {policy_hash(p)}
