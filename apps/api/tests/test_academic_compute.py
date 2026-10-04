"""Cross-route CPU admission and HTTP-disconnect lifecycle regressions."""

import asyncio
import json
from decimal import Decimal
from threading import Event
from time import monotonic, sleep

import pytest

from app.api.routes.student import get_student_service
from app.core.academic_compute import AcademicComputeLimiter
from app.core.auth import CurrentUser, get_current_user
from app.degree_path.models import DegreePathCapacityError, DegreePathComputationTimeout
from app.main import app
from apps.api.tests.test_degree_path_api import _sample_degree_path_result


@pytest.mark.anyio
async def test_shared_cpu_admission_release_and_lightweight_responsiveness():
    limiter = AcademicComputeLimiter(1)
    entered = Event()
    release = Event()

    def slow(_check):
        entered.set()
        assert release.wait(2)
        return "ok"

    first = asyncio.create_task(limiter.run(slow))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        start = monotonic()
        with pytest.raises(DegreePathCapacityError):
            await limiter.run(lambda _check: "second")
        assert monotonic() - start < 0.1
        assert await asyncio.wait_for(asyncio.sleep(0.01), 0.5) is None
    finally:
        release.set()
    assert await first == "ok"
    await asyncio.sleep(0)
    assert limiter.in_use == 0
    assert await limiter.run(lambda _check: "next") == "next"


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["exception", "timeout"])
async def test_shared_cpu_slot_released_after_failure(mode):
    limiter = AcademicComputeLimiter()
    stopped = Event()

    def calculate(check):
        try:
            if mode == "exception":
                raise RuntimeError("worker failed")
            while True:
                check()
                sleep(0.001)
        finally:
            stopped.set()

    error = RuntimeError if mode == "exception" else DegreePathComputationTimeout
    with pytest.raises(error):
        await limiter.run(calculate, deadline=monotonic() + 0.03)
    assert await asyncio.to_thread(stopped.wait, 1)
    for _ in range(100):
        if limiter.in_use == 0:
            break
        await asyncio.sleep(0.001)
    assert limiter.in_use == 0
    assert await limiter.run(lambda _check: 1) == 1


@pytest.mark.anyio
async def test_http_disconnect_stops_worker_and_watcher_then_allows_next_request():
    limiter = AcademicComputeLimiter()
    entered = Event()
    stopped = Event()

    class Service:
        calls = 0

        async def get_degree_paths(self, _owner, *, cancel_event, **_kwargs):
            self.calls += 1
            if self.calls == 2:
                return await limiter.run(lambda _check: _sample_degree_path_result())

            def calculate(check):
                entered.set()
                try:
                    while True:
                        check()
                        sleep(0.001)
                finally:
                    stopped.set()

            return await limiter.run(calculate, cancel_event=cancel_event)

    service = Service()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id="00000000-0000-0000-0000-000000000001")
    app.dependency_overrides[get_student_service] = lambda: service

    async def invoke(disconnect: bool):
        events = asyncio.Queue()
        body = json.dumps({"max_credit_hours_per_semester": 15}).encode()
        await events.put({"type": "http.request", "body": body, "more_body": False})
        sent = []
        async def send(message):
            sent.append(message)
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "POST", "scheme": "http", "path": "/api/v1/me/degree-paths",
            "raw_path": b"/api/v1/me/degree-paths", "query_string": b"",
            "root_path": "", "client": ("127.0.0.1", 1), "server": ("test", 80),
            "headers": [(b"content-type", b"application/json")],
        }
        task = asyncio.create_task(app(scope, events.get, send))
        if disconnect:
            assert await asyncio.to_thread(entered.wait, 1)
            await events.put({"type": "http.disconnect"})
        await asyncio.wait_for(task, 2)
        return sent

    try:
        first = await invoke(True)
        assert await asyncio.to_thread(stopped.wait, 1)
        for _ in range(100):
            if limiter.in_use == 0:
                break
            await asyncio.sleep(0.001)
        assert limiter.in_use == 0
        assert first[0]["status"] == 504
        assert not any(task.get_name().startswith("degree-path-disconnect") for task in asyncio.all_tasks())
        second = await invoke(False)
        assert second[0]["status"] == 200
    finally:
        app.dependency_overrides.clear()
