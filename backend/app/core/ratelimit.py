"""A minimal in-process sliding-window rate limiter.

Deliberately not Redis and not a decorator framework: this is one guard on one expensive
endpoint, and the process is the only thing that has to agree about the count. The trade-off
is real and stated in the README — with several workers each keeps its own window, so the
ceiling becomes ``limit * workers``. Tightening that means moving the counters to Redis or
Postgres, not rewriting this.

Timestamps come from an optional ``now`` argument so tests never sleep.
"""

import threading
import time
from collections import defaultdict


class SlidingWindowRateLimiter:
    """Allow up to ``limit`` calls per ``window_seconds`` per key."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _live_hits(self, key: str, current: float) -> list[float]:
        """Hits inside the window, pruning anything older. Caller must hold the lock."""
        hits = [hit for hit in self._hits[key] if hit > current - self.window_seconds]
        if hits:
            self._hits[key] = hits
        else:
            self._hits.pop(key, None)
        return hits

    def check(self, key: str, *, now: float | None = None) -> bool:
        """Record an attempt and report whether it is allowed.

        Only allowed calls are counted. A rejected attempt did no work and cost nothing, so
        recording it would let someone hammering the endpoint push the legitimate user's own
        window further away.
        """
        current = time.monotonic() if now is None else now
        with self._lock:
            hits = self._live_hits(key, current)
            if len(hits) >= self.limit:
                return False
            self._hits[key] = [*hits, current]
            return True

    def remaining(self, key: str, *, now: float | None = None) -> int:
        """How many calls are still allowed in the current window."""
        current = time.monotonic() if now is None else now
        with self._lock:
            return max(0, self.limit - len(self._live_hits(key, current)))

    def retry_after(self, key: str, *, now: float | None = None) -> int:
        """Seconds until the oldest hit in the window expires; 0 when under the limit."""
        current = time.monotonic() if now is None else now
        with self._lock:
            hits = self._live_hits(key, current)
            if len(hits) < self.limit:
                return 0
            return max(1, round(hits[0] + self.window_seconds - current))

    def reset(self, key: str | None = None) -> None:
        """Forget counts — for tests, or after a configuration change."""
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


#: One transcribe call costs money and an external round trip, so it is capped per patient.
TRANSCRIBE_LIMIT = 10
TRANSCRIBE_WINDOW_SECONDS = 3600.0

transcribe_limiter = SlidingWindowRateLimiter(TRANSCRIBE_LIMIT, TRANSCRIBE_WINDOW_SECONDS)
