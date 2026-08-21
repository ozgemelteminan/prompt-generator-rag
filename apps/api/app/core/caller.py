"""Caller identity boundary for limits and authoritative usage."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CallerContext:
    """Stable workspace identity, replaceable by authenticated identity later."""

    id: str
