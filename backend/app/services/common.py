"""Shared event-mode checks and audit reference generation."""

from __future__ import annotations

import secrets

from ..models import Event, EventMode


def reference(prefix: str) -> str:
    """Return a random, human-readable reference prefixed for its ledger or audit purpose."""
    return f"{prefix}-{secrets.token_hex(8).upper()}"


def event_supports(event: Event, system: str) -> bool:
    """Return whether an event enables the requested money or coupon system."""
    return event.mode.value == system or event.mode == EventMode.both
