"""Startup guards for network-exposed server binds.

A loopback ``omnigent server`` may run in explicit single-user header mode
(``OMNIGENT_LOCAL_SINGLE_USER=1``). Binding a non-loopback address with that
marker — or with auth fully disabled — exposes the agent API (including shell
tools) to the network without authentication.
"""

from __future__ import annotations

import ipaddress
import os

from omnigent.server.auth import _auth_enabled, local_single_user_enabled

_LOOPBACK_NAMES = frozenset({"127.0.0.1", "localhost", "::1"})


def is_loopback_bind_host(host: str) -> bool:
    """Return whether ``host`` is a loopback bind address.

    :param host: Bind host from CLI/config, e.g. ``"127.0.0.1"`` or ``"0.0.0.0"``.
    :returns: ``True`` when the address is loopback-only.
    """
    normalized = host.strip().lower()
    if normalized in _LOOPBACK_NAMES:
        return True
    bare = normalized.strip("[]")
    try:
        return ipaddress.ip_address(bare).is_loopback
    except ValueError:
        return False


def assert_safe_network_bind(host: str) -> None:
    """Refuse startup when a network bind would be unauthenticated.

    :param host: Resolved bind host.
    :raises RuntimeError: When ``host`` is network-exposed but the process
        env is in single-user or no-auth posture.
    """
    if is_loopback_bind_host(host):
        return

    if local_single_user_enabled():
        raise RuntimeError(
            f"Refusing to bind {host!r}: OMNIGENT_LOCAL_SINGLE_USER is only "
            "allowed on loopback (127.0.0.1). Enable multi-user auth "
            "(OMNIGENT_AUTH_ENABLED=1) for network-exposed servers."
        )

    raw_provider = os.environ.get("OMNIGENT_AUTH_PROVIDER", "")
    provider_explicit = bool(raw_provider and raw_provider.strip())
    if not _auth_enabled() and not provider_explicit:
        raise RuntimeError(
            f"Refusing to bind {host!r}: network-exposed servers require "
            "OMNIGENT_AUTH_ENABLED=1 or an explicit OMNIGENT_AUTH_PROVIDER "
            "(e.g. header behind a trusted identity proxy)."
        )
