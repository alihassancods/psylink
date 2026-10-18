"""Sliding-window limiter: the cap, the window, per-key isolation, and Retry-After."""

import pytest

from app.core.ratelimit import SlidingWindowRateLimiter


def test_allows_exactly_limit_then_refuses() -> None:
    limiter = SlidingWindowRateLimiter(3, 60.0)
    assert [limiter.check("u", now=t) for t in (0.0, 1.0, 2.0)] == [True, True, True]
    assert limiter.check("u", now=3.0) is False


def test_a_rejected_attempt_does_not_extend_the_window() -> None:
    """Recording rejects would let noise push the legitimate user's budget away."""
    limiter = SlidingWindowRateLimiter(1, 60.0)
    assert limiter.check("u", now=0.0) is True
    for stamp in (1.0, 2.0, 3.0):
        assert limiter.check("u", now=stamp) is False
    # The window still runs from the one allowed call at 0.0.
    assert limiter.check("u", now=59.0) is False
    assert limiter.check("u", now=61.0) is True


def test_window_expiry_restores_the_budget_one_at_a_time() -> None:
    limiter = SlidingWindowRateLimiter(2, 10.0)
    assert limiter.check("u", now=0.0) is True
    assert limiter.check("u", now=5.0) is True
    assert limiter.check("u", now=6.0) is False
    assert limiter.check("u", now=10.5) is True  # the 0.0 hit has aged out
    assert limiter.check("u", now=11.0) is False  # 5.0 and 10.5 still in window


def test_keys_are_independent() -> None:
    limiter = SlidingWindowRateLimiter(1, 60.0)
    assert limiter.check("a", now=0.0) is True
    assert limiter.check("b", now=0.0) is True
    assert limiter.check("a", now=0.0) is False


def test_remaining_and_retry_after() -> None:
    limiter = SlidingWindowRateLimiter(2, 60.0)
    assert limiter.remaining("u", now=0.0) == 2
    limiter.check("u", now=0.0)
    limiter.check("u", now=10.0)
    assert limiter.remaining("u", now=10.0) == 0
    assert limiter.check("u", now=10.0) is False
    assert limiter.retry_after("u", now=10.0) == 50  # oldest hit was at 0.0
    assert limiter.retry_after("other", now=10.0) == 0


def test_reset_clears_state() -> None:
    limiter = SlidingWindowRateLimiter(1, 60.0)
    limiter.check("a", now=0.0)
    limiter.check("b", now=0.0)
    limiter.reset("a")
    assert limiter.check("a", now=0.0) is True
    assert limiter.check("b", now=0.0) is False
    limiter.reset()
    assert limiter.check("b", now=0.0) is True


@pytest.mark.parametrize(("limit", "window"), [(0, 60.0), (-1, 60.0), (5, 0.0), (5, -1.0)])
def test_bad_configuration_fails_at_construction(limit: int, window: float) -> None:
    with pytest.raises(ValueError):
        SlidingWindowRateLimiter(limit, window)


def test_pruning_bounds_memory_over_a_long_lived_key() -> None:
    limiter = SlidingWindowRateLimiter(2, 10.0)
    for stamp in range(500):
        limiter.check("u", now=float(stamp))
    assert len(limiter._hits["u"]) <= 3  # only the live window is retained
