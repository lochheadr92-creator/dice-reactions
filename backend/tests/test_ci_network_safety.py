"""Deterministic guard: non-live tests must not reach gateway.invoke_llm."""

import pytest

import gateway


def test_gateway_invoke_llm_blocked_in_deterministic_suite():
    with pytest.raises(RuntimeError, match="blocked"):
        gateway.invoke_llm(messages=[], model="test")