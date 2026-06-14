from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from threading import Condition, Thread
from uuid import uuid4

from pydantic import BaseModel

from app.config import Settings
from app.models import RefreshSource
from app.services.portfolio import REFRESH_STEP_LABELS, refresh_snapshot, refresh_steps_for_source


RefreshJobStatus = str


class RefreshJob(BaseModel):
    id: str
    source: RefreshSource
    label: str
    status: RefreshJobStatus
    queued_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    stage: str = "Queued"
    step_source: str | None = None
    current_step: int = 0
    total_steps: int = 1
    error: str | None = None
    duplicate_of: str | None = None
    elapsed_seconds: float = 0


_condition = Condition()
_jobs: dict[str, RefreshJob] = {}
_queue: deque[str] = deque()
_worker_started = False
_MAX_FINISHED_JOBS = 12


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _source_label(source: RefreshSource) -> str:
    return {
        "all": "Refresh all",
        "binance": "Binance",
        "binance_ledger": "Binance ledger",
        "ibkr": "IBKR",
        "ibkr_history": "IBKR history",
        "manual": "Manual cash and assets",
        "market_data": "Market prices",
        "fx": "FX rates",
        "prices_fx": "Prices and FX",
    }.get(source, source)


def _view(job: RefreshJob) -> RefreshJob:
    end = job.completed_at or _now()
    start = job.started_at or job.queued_at
    return job.model_copy(update={"elapsed_seconds": max(0, (end - start).total_seconds())})


def _trim_finished_jobs() -> None:
    finished = [
        job
        for job in sorted(_jobs.values(), key=lambda item: item.completed_at or item.queued_at, reverse=True)
        if job.status in {"success", "error"}
    ]
    for job in finished[_MAX_FINISHED_JOBS:]:
        _jobs.pop(job.id, None)


def _find_active_source_job(source: RefreshSource) -> RefreshJob | None:
    for job in sorted(_jobs.values(), key=lambda item: item.queued_at, reverse=True):
        if job.source == source and job.status in {"queued", "running"}:
            return job
    return None


def start_refresh_job(settings: Settings, source: RefreshSource) -> RefreshJob:
    with _condition:
        existing = _find_active_source_job(source)
        if existing:
            return _view(existing.model_copy(update={"duplicate_of": existing.id}))

        steps = refresh_steps_for_source(source)
        job = RefreshJob(
            id=str(uuid4()),
            source=source,
            label=_source_label(source),
            status="queued",
            queued_at=_now(),
            stage="Queued",
            total_steps=len(steps) + 1,
        )
        _jobs[job.id] = job
        _queue.append(job.id)
        _ensure_worker_locked(settings)
        _condition.notify()
        return _view(job)


def list_refresh_jobs() -> list[RefreshJob]:
    with _condition:
        return [
            _view(job)
            for job in sorted(_jobs.values(), key=lambda item: item.queued_at, reverse=True)
        ]


def _ensure_worker_locked(settings: Settings) -> None:
    global _worker_started
    if _worker_started:
        return
    _worker_started = True
    worker = Thread(target=_worker_loop, args=(settings,), daemon=True)
    worker.start()


def _worker_loop(settings: Settings) -> None:
    while True:
        with _condition:
            while not _queue:
                _condition.wait()
            job_id = _queue.popleft()
            job = _jobs.get(job_id)
            if not job:
                continue
            _jobs[job_id] = job.model_copy(
                update={
                    "status": "running",
                    "started_at": _now(),
                    "stage": "Starting",
                    "current_step": 0,
                    "error": None,
                }
            )

        try:
            def progress(step_source: str, stage: str, current_step: int, total_steps: int) -> None:
                with _condition:
                    current = _jobs.get(job_id)
                    if not current:
                        return
                    _jobs[job_id] = current.model_copy(
                        update={
                            "stage": stage or REFRESH_STEP_LABELS.get(step_source, step_source),
                            "step_source": step_source,
                            "current_step": current_step,
                            "total_steps": total_steps,
                        }
                    )

            refresh_snapshot(settings, job.source, progress=progress)
            with _condition:
                current = _jobs.get(job_id)
                if current:
                    _jobs[job_id] = current.model_copy(
                        update={
                            "status": "success",
                            "stage": "Complete",
                            "completed_at": _now(),
                            "current_step": current.total_steps,
                            "error": None,
                        }
                    )
                    _trim_finished_jobs()
        except Exception as exc:
            with _condition:
                current = _jobs.get(job_id)
                if current:
                    _jobs[job_id] = current.model_copy(
                        update={
                            "status": "error",
                            "stage": "Failed",
                            "completed_at": _now(),
                            "error": str(exc),
                        }
                    )
                    _trim_finished_jobs()
