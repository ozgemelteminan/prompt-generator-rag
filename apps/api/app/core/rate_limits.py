"""Replaceable single-process rate-limiting boundary."""

from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from time import monotonic


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int | None = None


class InMemoryRateLimiter:
    """Thread-safe sliding-window limiter for one API process."""

    def __init__(self, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self._requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(
        self, *, caller_id: str, action: str, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        now = self._clock()
        key = (caller_id, action)
        with self._lock:
            timestamps = self._requests[key]
            while timestamps and timestamps[0] <= now - window_seconds:
                timestamps.popleft()
            if len(timestamps) >= limit:
                retry_after = max(1, int(timestamps[0] + window_seconds - now + 0.999))
                return RateLimitDecision(False, retry_after)
            timestamps.append(now)
        return RateLimitDecision(True)
