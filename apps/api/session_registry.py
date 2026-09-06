from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Callable

from fastapi import HTTPException

from shared.config import JOB_RETENTION_MAX, JOB_RETENTION_TTL_SECONDS

RUNNING = {"queued", "routing", "running", "merging", "formatting"}


class JobRegistry:
    def __init__(
        self,
        *,
        max_jobs: int = JOB_RETENTION_MAX,
        ttl_seconds: int = JOB_RETENTION_TTL_SECONDS,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.max_jobs = max_jobs
        self.ttl_seconds = ttl_seconds
        self.clock = clock or time.time
        self.jobs: dict[str, dict] = {}

    def create(self, query: str) -> dict:
        now = self.clock()
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        job = {
            "job_id": job_id,
            "status": "queued",
            "query": query,
            "created_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
            "activated_agents": [],
            "timeline": [],
            "warnings": [],
            "error": None,
            "result": None,
            "pdf_bytes": None,
            "handle": None,
            "last_access": now,
        }
        self.jobs[job_id] = job
        self.evict()
        return job

    def get(self, job_id: str) -> dict:
        job = self.jobs.get(job_id)
        if job is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "job_not_found", "message": "Job no longer available — please ask again."},
            )
        job["last_access"] = self.clock()
        return job

    def evict(self) -> None:
        now = self.clock()
        for job_id, job in list(self.jobs.items()):
            if job.get("status") in RUNNING:
                continue
            created = job.get("last_access")
            if created is None:
                created = now
            if now - created >= self.ttl_seconds:
                del self.jobs[job_id]

        overflow = len(self.jobs) - self.max_jobs
        if overflow <= 0:
            return
        completed = [
            (job_id, job)
            for job_id, job in self.jobs.items()
            if job.get("status") not in RUNNING
        ]
        completed.sort(key=lambda item: item[1].get("last_access") if item[1].get("last_access") is not None else 0)
        for job_id, _job in completed[:overflow]:
            del self.jobs[job_id]
