"""Phase 8 §5.5: TTL cache wrapper - hits vs misses, invalidation, expiry."""
import asyncio

import pytest

from app.core.cache import AsyncTTLCache


@pytest.mark.asyncio
async def test_get_or_set_only_calls_factory_once_within_ttl():
    cache = AsyncTTLCache(ttl_seconds=60)
    call_count = 0

    async def factory():
        nonlocal call_count
        call_count += 1
        return "value"

    result1 = await cache.get_or_set("key", factory)
    result2 = await cache.get_or_set("key", factory)

    assert result1 == "value"
    assert result2 == "value"
    assert call_count == 1


@pytest.mark.asyncio
async def test_expired_entry_triggers_factory_again():
    cache = AsyncTTLCache(ttl_seconds=0.05)
    call_count = 0

    async def factory():
        nonlocal call_count
        call_count += 1
        return call_count

    first = await cache.get_or_set("key", factory)
    await asyncio.sleep(0.1)
    second = await cache.get_or_set("key", factory)

    assert first == 1
    assert second == 2


@pytest.mark.asyncio
async def test_invalidate_forces_refetch():
    cache = AsyncTTLCache(ttl_seconds=60)
    call_count = 0

    async def factory():
        nonlocal call_count
        call_count += 1
        return call_count

    await cache.get_or_set("key", factory)
    cache.invalidate("key")
    result = await cache.get_or_set("key", factory)

    assert result == 2
