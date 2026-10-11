"""Rotas da API (F14). Camada fina: só chamam os serviços que a CLI usa.

Um único `APIRouter`: é o ponto onde a autenticação e a autorização entram no futuro (seção 11 da spec).
"""

import re
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src import db, management_service
from src.answer_service import relevance_threshold, run_ask
from src.api.errors import ApiError
from src.api.jobs import Job, JobFailed
from src.api.schemas import AskRequest, EvaluationRequest, IngestRequest, ReindexRequest, SearchRequest
from src.chunking import STRATEGIES
from src.evaluation import DEFAULT_QUESTIONS
from src.folder_ingestion import FolderResult, Reporter, ingest_folder, reindex_folders
from src.ingestion import ingest_file
from src.loaders import inspect_document
from src.retrieval import METHODS
from src.search_service import SearchOutcome, run_search

router = APIRouter()


# ---------- conversões ----------

def _iso(value) -> str | None:
    return value.isoformat(timespec="seconds") if value else None


def _num(value) -> float | None:
    return None if value is None else float(value)


def hit_dict(hit) -> dict:
    return {
        "document": hit.filename,
        "path": hit.source_path,
        "page": hit.page,
        "section": hit.section,
        "text": hit.content,
        "scores": {
            "score": float(hit.score),  # do método usado (rrf, cosseno ou ts_rank_cd)
            "semantic": _num(hit.semantic_score),
            "semantic_rank": hit.semantic_rank,
            "lexical": _num(hit.lexical_score),
            "lexical_rank": hit.lexical_rank,
        },
    }


def search_dict(outcome: SearchOutcome) -> dict:
    return {
        "status": outcome.status,
        "method": outcome.method,
        "top_k": outcome.top_k,
        "fetch_k": outcome.fetch_k,
        "folder": outcome.folder,
        "hits": [hit_dict(h) for h in outcome.hits],
        "elapsed": round(outcome.elapsed, 2),
    }


def folder_dict(result: FolderResult) -> dict:
    return {
        "folder": result.folder,
        "registered_now": result.registered_now,
        "recursive": result.recursive,
        "files": [
            {"path": f.path, "outcome": f.outcome, "chunk_count": f.chunk_count, "detail": f.detail}
            for f in result.files
        ],
        "ignored": [{"path": f.path, "outcome": f.outcome, "detail": f.detail} for f in result.ignored],
        "out_of_scope": result.out_of_scope,
        "prune_status": None if result.prune_status in (None, "none") else result.prune_status,
        "elapsed": round(result.elapsed, 1),
        "error": result.error,
        "error_code": result.error_code,
    }


def _check_search_params(method: str, top_k: int, fetch_k: int) -> None:
    if method not in METHODS:
        raise ApiError("invalid_parameter", f'Método desconhecido: "{method}". Use: {", ".join(METHODS)}.')
    if top_k < 1 or fetch_k < 1:
        raise ApiError("invalid_parameter", "top_k e fetch_k devem ser maiores que zero.")


def _accepted(job: Job) -> JSONResponse:
    href = f"/api/v1/jobs/{job.job_id}"
    return JSONResponse({"job_id": job.job_id, "status": job.status, "href": href}, status_code=202)


class _JobReporter(Reporter):
    def __init__(self, job: Job) -> None:
        self.job = job

    def file_start(self, index: int, total: int, rel: str):
        self.job.set_progress(index, total, rel)
        return None


# ---------- saúde, ambiente e banco ----------

@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/check")
def check() -> JSONResponse:
    items = db.run_checks()
    ok = not any(i.status == "fail" for i in items)
    body = {"ok": ok, "checks": [{"name": i.name, "status": i.status, "detail": i.detail} for i in items]}
    return JSONResponse(body, status_code=200 if ok else 503)


@router.post("/db/init")
def init_database() -> dict:
    db.init_db()
    return {"status": "ok", "migrations": db.migration_names()}


# ---------- cadastro (tarefas) ----------

@router.post("/ingest", status_code=202)
def ingest(body: IngestRequest, request: Request) -> JSONResponse:
    path = Path(body.path).resolve()
    if not path.exists():
        raise ApiError("not_found", f"Caminho não encontrado no servidor: {path}")
    cache, jobs = request.app.state.embedder_cache, request.app.state.jobs
    confirm_prune = body.confirm_prune

    if path.is_dir():

        def run_folder(job: Job) -> dict:
            result = ingest_folder(
                path, body.recursive, body.force, body.prune, _JobReporter(job),
                lambda folder, paths, missing: confirm_prune, cache,
            )
            data = folder_dict(result)
            if result.fatal:
                raise JobFailed(ApiError(result.fatal_code or "internal_error", result.fatal), data)
            if result.error:
                raise JobFailed(ApiError(result.error_code or "internal_error", result.error), data)
            return data

        return _accepted(jobs.submit("ingest", run_folder))

    if body.recursive is not None or body.prune:
        raise ApiError("invalid_parameter", "recursive e prune só se aplicam a pastas.")
    inspect_document(path)  # formato não aceito ou PDF sem texto: 422 na hora, sem entrar na fila

    def run_file(job: Job) -> dict:
        def progress(page: int, total: int, chunks: int, rate: float) -> None:
            job.set_progress(page, total, path.name)

        result = ingest_file(path, progress, body.force, cache)
        return {
            "outcome": result.outcome,
            "path": str(result.path),
            "document_id": result.document_id,
            "chunk_count": result.chunk_count,
            "duplicate_of": result.duplicate_of,
            "replaced_previous": result.replaced_previous,
            "elapsed": round(result.elapsed, 1),
        }

    return _accepted(jobs.submit("ingest", run_file))


@router.post("/reindex", status_code=202)
def reindex(body: ReindexRequest, request: Request) -> JSONResponse:
    if body.all == (body.path is not None):
        raise ApiError("invalid_parameter", "Informe path ou all=true, não os dois nem nenhum.")
    cache, jobs = request.app.state.embedder_cache, request.app.state.jobs
    target = Path(body.path).resolve() if body.path else None
    if target is not None:
        conn = db.connect()
        try:
            from src import repository

            registered = repository.get_source(conn, str(target)) is not None
        finally:
            conn.close()
        if not registered:
            raise ApiError("not_found", f"{target} não está registrada. Cadastre com POST /api/v1/ingest.")
    confirm_prune = body.confirm_prune

    def run(job: Job) -> dict:
        folders, fatal = [], None
        for result in reindex_folders(
            target, body.prune, _JobReporter(job), lambda folder, paths, missing: confirm_prune, cache
        ):
            folders.append(folder_dict(result))
            fatal = fatal or result.fatal and ApiError(result.fatal_code or "internal_error", result.fatal)
        if fatal:
            raise JobFailed(fatal, {"folders": folders})
        return {"folders": folders}

    return _accepted(jobs.submit("reindex", run))


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request) -> dict:
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise ApiError("not_found", f"Tarefa {job_id} não existe.")
    return job.to_dict()


# ---------- consulta ----------

@router.post("/search")
def search(body: SearchRequest, request: Request) -> dict:
    _check_search_params(body.method, body.top_k, body.fetch_k)
    outcome = run_search(
        body.question, body.method, body.top_k, body.fetch_k, body.folder, request.app.state.embedder_cache
    )
    return search_dict(outcome)


@router.post("/ask")
def ask(body: AskRequest, request: Request) -> dict:
    _check_search_params(body.method, body.top_k, body.fetch_k)
    result = run_ask(
        body.question, body.method, body.top_k, body.fetch_k, body.folder,
        embedder_source=request.app.state.embedder_cache,
    )
    search_part = result.search
    return {
        "status": search_part.status,
        "answer": result.answer,
        "sources": [
            {"n": n, "document": hit.filename, "path": hit.source_path, "page": hit.page, "section": hit.section}
            for n, hit in result.sources
        ],
        "truncated": result.truncated,
        "cited_none": result.cited_none,
        "search": {
            "method": search_part.method,
            "top_k": search_part.top_k,
            "fetch_k": search_part.fetch_k,
            "folder": search_part.folder,
            "hits": len(search_part.hits),
        },
        "elapsed": {"search": round(search_part.elapsed, 2), "answer": round(result.answer_elapsed, 2)},
    }


# ---------- gestão da base ----------

@router.get("/folders")
def folders() -> dict:
    return {
        "folders": [
            {
                "path": s.path,  # null = documentos avulsos
                "recursive": s.recursive,
                "documents": s.documents,
                "chunks": s.chunks,
                "last_indexed_at": _iso(s.last_indexed_at),
            }
            for s in management_service.list_folders()
        ]
    }


@router.get("/documents")
def documents(folder: str | None = None) -> dict:
    listing = management_service.list_documents(folder)
    return {
        "folder": str(Path(folder).resolve()) if folder else None,
        "documents": [
            {
                "id": d.id,
                "path": d.source_path,
                "file_type": d.file_type,
                "status": d.status,
                "pages": d.pages,
                "chunks": d.chunks,
            }
            for d in listing
        ],
    }


def _delete(path: str, confirm: bool, expected_kind: str) -> JSONResponse:
    def confirm_callback(kind: str, target: str, paths: list[str], chunks: int) -> bool:
        if kind != expected_kind:
            use = "DELETE /api/v1/folders" if kind == "folder" else "DELETE /api/v1/documents"
            raise ApiError("not_found", f"{target} não é {'um documento' if kind == 'folder' else 'uma pasta'}; use {use}.")
        return confirm

    result = management_service.delete_target(path, confirm_callback)
    data = {
        "kind": result.kind,
        "target": result.target,
        "documents": result.documents,
        "chunks": result.chunks,
        "paths": result.paths,
    }
    if result.status != "removed":
        raise ApiError("confirmation_required", "Confirme a remoção com confirm=true.", data)
    return JSONResponse({"status": "removed", **data})


@router.delete("/documents")
def delete_document(path: str, confirm: bool = False) -> JSONResponse:
    return _delete(path, confirm, "document")


@router.delete("/folders")
def delete_folder(path: str, confirm: bool = False) -> JSONResponse:
    return _delete(path, confirm, "folder")


# ---------- avaliação (tarefa) ----------

_STEP = re.compile(r"^\[(\d+)/(\d+)\]")


@router.post("/evaluations", status_code=202)
def evaluations(body: EvaluationRequest, request: Request) -> JSONResponse:
    if body.top_k < 1 or any(m < 1 for m in body.max_chars):
        raise ApiError("invalid_parameter", "top_k e max_chars devem ser maiores que zero.")
    if not body.strategies or not body.max_chars or not body.methods:
        raise ApiError("invalid_parameter", "strategies, max_chars e methods não podem ser vazios.")
    for name, values, allowed in (("strategies", body.strategies, STRATEGIES), ("methods", body.methods, METHODS)):
        bad = [v for v in values if v not in allowed]
        if bad:
            raise ApiError("invalid_parameter", f"{name}: valor desconhecido {bad[0]!r}. Use: {', '.join(allowed)}.")
    questions = Path(body.questions_file or DEFAULT_QUESTIONS)
    if not questions.is_file():
        raise ApiError("not_found", f"Arquivo de perguntas não encontrado: {questions}")
    cache = request.app.state.embedder_cache

    def run(job: Job) -> dict:
        from src.evaluation_service import run_eval

        def progress(message: str) -> None:
            step = _STEP.match(message)
            current, total = (int(step.group(1)), int(step.group(2))) if step else (0, 0)
            job.set_progress(current, total, message)

        outcome = run_eval(
            questions, body.strategies, body.max_chars, body.methods, body.top_k, body.answers, progress, cache
        )
        rows = [
            {
                "strategy": cfg.strategy,
                "max_chars": cfg.max_chars,
                "method": method,
                "hit_at_1": metrics.hit_at[1],
                "hit_at_k": metrics.hit_at[outcome.top_k],
                "mrr": metrics.mrr,
                "chunks": cfg.chunk_count,
            }
            for cfg in outcome.configs
            for method, metrics in cfg.metrics.items()
        ]
        answers = None
        if outcome.answers is not None:
            answers = {
                "method": outcome.answers_method,
                "correct": sum(1 for a in outcome.answers if a.status == "ok"),
                "total": len(outcome.answers),
                "results": [
                    {"question_id": a.question_id, "status": a.status, "detail": a.detail, "called_claude": a.called_claude}
                    for a in outcome.answers
                ],
            }
        return {
            "questions": len(outcome.eval_set.questions),
            "top_k": outcome.top_k,
            "rows": rows,
            "threshold": {
                "proposed": outcome.suggestion,
                "current": relevance_threshold(),
                "method": outcome.gate_method,
                "table": [{"limit": r.limit, "kept": r.kept, "blocked": r.blocked} for r in outcome.threshold_rows],
            },
            "answers": answers,
            "elapsed": round(outcome.elapsed, 1),
        }

    return _accepted(request.app.state.jobs.submit("evaluation", run))
