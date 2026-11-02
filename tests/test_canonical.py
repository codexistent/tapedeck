from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tapedeck.canonical import canonical_json, canonicalize_args, normalize, sha256

json_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(-(2**40), 2**40)
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(),
    lambda children: (
        st.lists(children, max_size=4) | st.dictionaries(st.text(max_size=8), children, max_size=4)
    ),
    max_leaves=12,
)


@given(st.dictionaries(st.text(max_size=8), json_values, max_size=6))
def test_key_order_never_matters(obj: dict[str, Any]) -> None:
    reversed_obj = dict(reversed(list(obj.items())))
    assert canonical_json(obj) == canonical_json(reversed_obj)


@given(json_values)
def test_idempotent(value: Any) -> None:
    import json

    once = canonical_json(value)
    assert canonical_json(json.loads(once)) == once


def test_integral_floats_hash_like_ints() -> None:
    assert canonical_json({"amount": 59.0}) == canonical_json({"amount": 59}) == '{"amount":59}'
    assert sha256([1.0, 2]) == sha256([1, 2.0])
    assert canonical_json(19.99) == "19.99"


def test_rejects_nan_and_non_string_keys() -> None:
    with pytest.raises(ValueError):
        normalize(float("nan"))
    with pytest.raises(TypeError):
        normalize({1: "x"})


def test_canonicalize_args_ignore_and_casefold() -> None:
    a = canonicalize_args(
        {"query": "  Refund   POLICY ", "request_id": "r1"},
        ignore=["request_id"],
        casefold=["query"],
    )
    b = canonicalize_args(
        {"query": "refund policy", "request_id": "r2"}, ignore=["request_id"], casefold=["query"]
    )
    assert a == b == '{"query":"refund policy"}'
