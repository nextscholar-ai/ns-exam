"""Phase 7 §5.8: token-bucket rate limiter behaviour."""
from app.core.rate_limit import RateLimiter


def test_allows_up_to_capacity_then_blocks():
    limiter = RateLimiter(default_capacity=3, default_refill_per_second=0.0)
    key = "test-key"
    assert limiter.allow(key) is True
    assert limiter.allow(key) is True
    assert limiter.allow(key) is True
    assert limiter.allow(key) is False  # 4th request in the same instant is blocked


def test_strict_bucket_is_smaller_than_default():
    limiter = RateLimiter(
        default_capacity=100, default_refill_per_second=0.0,
        strict_capacity=2, strict_refill_per_second=0.0,
    )
    key = "auth-caller"
    assert limiter.allow(key, strict=True) is True
    assert limiter.allow(key, strict=True) is True
    assert limiter.allow(key, strict=True) is False


def test_refill_over_time_allows_more_requests():
    import time

    limiter = RateLimiter(default_capacity=1, default_refill_per_second=1000.0)
    key = "refill-key"
    assert limiter.allow(key) is True
    assert limiter.allow(key) is False
    time.sleep(0.01)  # ~10 tokens refill at 1000/s
    assert limiter.allow(key) is True
