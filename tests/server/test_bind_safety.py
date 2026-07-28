"""Tests for network bind safety guards."""

from __future__ import annotations

import pytest

from omnigent.server.bind_safety import assert_safe_network_bind, is_loopback_bind_host


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1", "localhost", "::1"],
)
def test_is_loopback_bind_host_true(host: str) -> None:
    assert is_loopback_bind_host(host) is True


@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "::", "10.0.0.1"],
)
def test_is_loopback_bind_host_false(host: str) -> None:
    assert is_loopback_bind_host(host) is False


def test_assert_safe_network_bind_allows_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIGENT_LOCAL_SINGLE_USER", "1")
    assert_safe_network_bind("127.0.0.1")


def test_assert_safe_network_bind_rejects_single_user_on_wildcard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMNIGENT_LOCAL_SINGLE_USER", "1")
    with pytest.raises(RuntimeError, match="OMNIGENT_LOCAL_SINGLE_USER"):
        assert_safe_network_bind("0.0.0.0")


def test_assert_safe_network_bind_rejects_no_auth_on_wildcard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OMNIGENT_LOCAL_SINGLE_USER", raising=False)
    monkeypatch.setenv("OMNIGENT_AUTH_ENABLED", "0")
    monkeypatch.delenv("OMNIGENT_AUTH_PROVIDER", raising=False)
    with pytest.raises(RuntimeError, match="OMNIGENT_AUTH_ENABLED"):
        assert_safe_network_bind("0.0.0.0")


def test_assert_safe_network_bind_allows_explicit_header_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OMNIGENT_LOCAL_SINGLE_USER", raising=False)
    monkeypatch.setenv("OMNIGENT_AUTH_ENABLED", "0")
    monkeypatch.setenv("OMNIGENT_AUTH_PROVIDER", "header")
    assert_safe_network_bind("0.0.0.0")
