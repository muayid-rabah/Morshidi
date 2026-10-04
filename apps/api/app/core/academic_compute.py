"""Process-local admission for pure, CPU-heavy academic calculations."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from threading import BoundedSemaphore, Event, Lock
from time import monotonic
from typing import TypeVar

from app.degree_path.models import DegreePathCapacityError, DegreePathComputationTimeout

T = TypeVar("T")
ACADEMIC_COMPUTE_BUDGET_SECONDS = 50.0


class AcademicComputeLimiter:
    """Fail fast when full; retain a slot until its worker really exits."""

    def __init__(self, capacity: int = 1) -> None:
        if capacity < 1:
            raise ValueError("Academic compute capacity must be positive")
        self.capacity = capacity
        self._slots = BoundedSemaphore(capacity)
        self._state_lock = Lock()
        self._in_use = 0

    @property
    def in_use(self) -> int:
        with self._state_lock:
            return self._in_use

    async def run(
        self,
        calculate: Callable[[Callable[[], None]], T],
        *,
        deadline: float | None = None,
        cancel_event: Event | None = None,
    ) -> T:
        if not self._slots.acquire(blocking=False):
            raise DegreePathCapacityError("Academic calculation capacity is busy")
        with self._state_lock:
            self._in_use += 1
        cancellation = cancel_event if cancel_event is not None else Event()
        cutoff = deadline if deadline is not None else monotonic() + ACADEMIC_COMPUTE_BUDGET_SECONDS
        worker: asyncio.Task[T] | None = None

        def check_budget() -> None:
            if cancellation.is_set() or monotonic() >= cutoff:
                raise DegreePathComputationTimeout("Academic computation budget expired")

        def finish(task: asyncio.Task[T]) -> None:
            with self._state_lock:
                self._in_use -= 1
            self._slots.release()
            if not task.cancelled():
                task.exception()  # Consume an abandoned worker failure.

        try:
            check_budget()
            worker = asyncio.create_task(asyncio.to_thread(calculate, check_budget))
            worker.add_done_callback(finish)
            async with asyncio.timeout_at(cutoff):
                return await asyncio.shield(worker)
        except TimeoutError as error:
            cancellation.set()
            raise DegreePathComputationTimeout("Academic computation budget expired") from error
        except asyncio.CancelledError:
            cancellation.set()
            raise
        finally:
            if worker is None:
                with self._state_lock:
                    self._in_use -= 1
                self._slots.release()
