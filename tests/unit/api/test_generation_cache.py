"""Cache de génération : appels concurrents fusionnés, résultat rejoué jusqu'à expiration, échecs
jamais conservés."""

from __future__ import annotations

import asyncio

import pytest

from organon.api.generation_cache import GenerationCache


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _cache(clock=None, **kw):
    return GenerationCache(keep=lambda events: events[-1] == "fin", clock=clock or Clock(), **kw)


def _producer(log, name="a", delay=0.0, events=("x", "fin")):
    async def gen():
        log.append(name)
        for e in events:
            await asyncio.sleep(delay)
            yield e

    return gen


async def _collect(cache, key, factory):
    return [e async for e in cache.stream(key, factory)]


@pytest.mark.asyncio
async def test_concurrent_calls_share_a_single_computation():
    log: list[str] = []
    cache = _cache()
    a, b = await asyncio.gather(
        _collect(cache, "k", _producer(log, delay=0.01)),
        _collect(cache, "k", _producer(log, delay=0.01)),
    )
    assert log == ["a"]
    assert a == b == ["x", "fin"]


@pytest.mark.asyncio
async def test_completed_result_replayed_without_recomputation():
    log: list[str] = []
    cache = _cache()
    await _collect(cache, "k", _producer(log))
    assert await _collect(cache, "k", _producer(log)) == ["x", "fin"]
    assert log == ["a"]


@pytest.mark.asyncio
async def test_different_keys_computed_separately():
    log: list[str] = []
    cache = _cache()
    await _collect(cache, "k1", _producer(log, "a"))
    await _collect(cache, "k2", _producer(log, "b"))
    assert log == ["a", "b"]


@pytest.mark.asyncio
async def test_expiry_after_ttl():
    log: list[str] = []
    clock = Clock()
    cache = _cache(clock, ttl=60)
    await _collect(cache, "k", _producer(log))
    clock.now = 61
    await _collect(cache, "k", _producer(log))
    assert log == ["a", "a"]


@pytest.mark.asyncio
async def test_failure_not_cached_and_propagated_to_all_consumers():
    log: list[str] = []

    async def boom():
        log.append("boom")
        yield "x"
        raise RuntimeError("panne")

    cache = _cache()
    results = await asyncio.gather(
        _collect(cache, "k", boom), _collect(cache, "k", boom), return_exceptions=True
    )
    assert all(isinstance(r, RuntimeError) for r in results)
    assert log == ["boom"]
    await _collect(cache, "k", _producer(log))
    assert log == ["boom", "a"]


@pytest.mark.asyncio
async def test_non_cacheable_result_recomputed():
    log: list[str] = []
    cache = _cache()
    partial = _producer(log, events=("x", "erreur"))
    await _collect(cache, "k", partial)
    await _collect(cache, "k", partial)
    assert log == ["a", "a"]


@pytest.mark.asyncio
async def test_consumer_disconnect_does_not_stop_the_computation():
    log: list[str] = []
    cache = _cache()
    stream = cache.stream("k", _producer(log, delay=0.02, events=("x", "y", "fin")))
    assert await stream.__anext__() == "x"
    await stream.aclose()
    await asyncio.sleep(0.15)
    assert await _collect(cache, "k", _producer(log)) == ["x", "y", "fin"]
    assert log == ["a"]


@pytest.mark.asyncio
async def test_bounded_size_evicts_the_oldest():
    log: list[str] = []
    cache = _cache(max_entries=2)
    for k in ("k1", "k2", "k3"):
        await _collect(cache, k, _producer(log, k))
    await _collect(cache, "k1", _producer(log, "k1bis"))
    assert log == ["k1", "k2", "k3", "k1bis"]
