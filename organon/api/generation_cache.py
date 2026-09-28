"""In-memory cache of generations.

A request is computed once, whether callers arrive together
(merged) or one after another (replayed until expiry). The
computation runs in its own task, so a caller disconnecting does
not cancel it. Events are recorded and replayed to each consumer,
so `/generate/stream` and `/generate` share one computation.

Per-process cache: the `Procfile` starts a single worker.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable
from typing import Generic, TypeVar

E = TypeVar("E")

DEFAULT_TTL_SECONDS = 15 * 60
DEFAULT_MAX_ENTRIES = 128


class _Job(Generic[E]):
    """One computation, recording its events for replay."""

    def __init__(self, producer: AsyncIterator[E], clock: Callable[[], float]) -> None:
        self.events: list[E] = []
        self.error: BaseException | None = None
        self.done = False
        self.finished_at = 0.0
        self._clock = clock
        self._changed = asyncio.Condition()
        self._task = asyncio.create_task(self._run(producer))

    async def _run(self, producer: AsyncIterator[E]) -> None:
        try:
            async for event in producer:
                async with self._changed:
                    self.events.append(event)
                    self._changed.notify_all()
        except BaseException as exc:
            self.error = exc
            if isinstance(exc, asyncio.CancelledError):
                raise
        finally:
            async with self._changed:
                self.finished_at = self._clock()
                self.done = True
                self._changed.notify_all()

    async def replay(self) -> AsyncIterator[E]:
        seen = 0
        while True:

            def has_news(after: int = seen) -> bool:
                return len(self.events) > after or self.done

            async with self._changed:
                await self._changed.wait_for(has_news)
            while seen < len(self.events):
                yield self.events[seen]
                seen += 1
            if self.done:
                break
        if self.error is not None:
            raise self.error


class GenerationCache(Generic[E]):
    """Cache of computations keyed by request.

    `keep(events)` decides whether a finished computation is worth
    keeping (not a possibly transient source failure). A computation
    that raised is never kept.
    """

    def __init__(
        self,
        keep: Callable[[list[E]], bool],
        ttl: float = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Configure the retention policy and the clock."""
        self._keep = keep
        self._ttl = ttl
        self._max_entries = max_entries
        self._clock = clock
        self._jobs: OrderedDict[str, _Job[E]] = OrderedDict()

    def _reusable(self, job: _Job[E]) -> bool:
        if not job.done:
            return True
        return (
            job.error is None
            and self._clock() - job.finished_at < self._ttl
            and self._keep(job.events)
        )

    def _evict(self) -> None:
        for key in [k for k, job in self._jobs.items() if job.done and not self._reusable(job)]:
            del self._jobs[key]
        while len(self._jobs) > self._max_entries:
            oldest_done = next((k for k, job in self._jobs.items() if job.done), None)
            if oldest_done is None:
                break
            del self._jobs[oldest_done]

    def clear(self) -> None:
        """Drop every cached computation."""
        self._jobs.clear()

    def stream(self, key: str, factory: Callable[[], AsyncIterator[E]]) -> AsyncIterator[E]:
        """Replay the events of `key`, running `factory()` if needed."""
        job = self._jobs.get(key)
        if job is None or not self._reusable(job):
            job = _Job(factory(), self._clock)
            self._jobs[key] = job
        self._jobs.move_to_end(key)
        self._evict()
        return job.replay()
