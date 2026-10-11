"""Tarefas assíncronas da API (F14, 4.4): em memória, fila de um único trabalhador."""

import queue
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from src.api.errors import ApiError, to_api_error


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Job:
    job_id: str
    kind: str
    status: str = "queued"  # queued | running | done | failed
    created_at: str = field(default_factory=_now)
    finished_at: str | None = None
    result: dict | None = None
    error: ApiError | None = None
    progress: dict | None = None

    def set_progress(self, current: int, total: int, item: str) -> None:
        self.progress = {"current": current, "total": total, "item": item}

    def to_dict(self) -> dict:
        data: dict = {"job_id": self.job_id, "kind": self.kind, "status": self.status, "created_at": self.created_at}
        if self.status == "running" and self.progress:
            data["progress"] = self.progress
        if self.finished_at:
            data["finished_at"] = self.finished_at
        if self.result is not None:
            data["result"] = self.result
        if self.error:
            data["error"] = {"code": self.error.code, "message": self.error.message}
        return data


class JobFailed(Exception):
    """A tarefa terminou com erro da tarefa inteira, mas com resultado parcial a guardar."""

    def __init__(self, error: ApiError, result: dict | None = None) -> None:
        super().__init__(error.message)
        self.error = error
        self.result = result


# função da tarefa: recebe o Job (para atualizar o progresso) e devolve o resultado em dict
JobFunction = Callable[[Job], dict]


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._queue: queue.Queue[tuple[Job, JobFunction]] = queue.Queue()
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None

    def submit(self, kind: str, function: JobFunction) -> Job:
        job = Job(uuid.uuid4().hex[:8], kind)
        with self._lock:
            self._jobs[job.job_id] = job
            if self._worker is None:
                self._worker = threading.Thread(target=self._run, name="api-jobs", daemon=True)
                self._worker.start()
        self._queue.put((job, function))
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def _run(self) -> None:
        while True:
            job, function = self._queue.get()
            job.status = "running"
            try:
                job.result = function(job)
                job.status = "done"
            except JobFailed as e:
                job.result, job.error, job.status = e.result, e.error, "failed"
            except BaseException as e:  # a tarefa nunca derruba o trabalhador
                job.error, job.status = to_api_error(e) if isinstance(e, Exception) else ApiError(
                    "internal_error", "Tarefa interrompida."
                ), "failed"
            job.finished_at = _now()
