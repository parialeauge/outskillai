import pytest
from fastapi import HTTPException

from apps.api.session_registry import JobRegistry
from shared.config import JOB_RETENTION_TTL_SECONDS


class FakeClock:
    def __init__(self, now: float = 0.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_completed_job_past_ttl_is_evicted_running_job_stays():
    clock = FakeClock(0)
    registry = JobRegistry(clock=clock)
    old = registry.create("old query")
    old["status"] = "completed"
    running = registry.create("running query")
    running["status"] = "running"
    clock.now = JOB_RETENTION_TTL_SECONDS + 1
    registry.evict()
    with pytest.raises(HTTPException) as exc:
        registry.get(old["job_id"])
    assert exc.value.status_code == 404
    assert exc.value.detail["error"] == "job_not_found"
    assert registry.get(running["job_id"])["status"] == "running"


def test_evict_never_drops_running_jobs_when_over_max():
    clock = FakeClock(0)
    registry = JobRegistry(max_jobs=2, ttl_seconds=JOB_RETENTION_TTL_SECONDS, clock=clock)
    first = registry.create("one")
    first["status"] = "completed"
    second = registry.create("two")
    second["status"] = "completed"
    running = registry.create("three")
    running["status"] = "running"
    registry.evict()
    with pytest.raises(HTTPException):
        registry.get(first["job_id"])
    assert registry.get(running["job_id"])["status"] == "running"
