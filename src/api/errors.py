"""Conversão dos erros dos serviços na resposta de erro padrão da API (F14, seção 4.3)."""

import logging

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src import db
from src.answer_service import AskError
from src.embeddings import EmbeddingError
from src.evaluation import EvaluationError
from src.folder_ingestion import FolderError
from src.generation import GenerationError
from src.ingestion import IngestError
from src.loaders import LoaderError
from src.management_service import ManagementError
from src.search_service import SearchError

log = logging.getLogger("uvicorn.error")

STATUS_BY_CODE = {
    "invalid_parameter": 400,
    "validation_error": 422,
    "not_found": 404,
    "folder_locked": 409,
    "folder_overlap": 409,
    "embedding_model_mismatch": 409,
    "confirmation_required": 409,
    "unsupported_file": 422,
    "llm_unavailable": 502,
    "database_unavailable": 503,
    "internal_error": 500,
}


class ApiError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.status = status or STATUS_BY_CODE[code]


def to_api_error(exc: Exception) -> ApiError:
    """Traduz o erro de um serviço; o que não é esperado vira `internal_error`, sem traceback."""
    if isinstance(exc, ApiError):
        return exc
    if isinstance(exc, db.ModelMismatchError):
        return ApiError("embedding_model_mismatch", str(exc))
    if isinstance(exc, db.DbError):
        return ApiError("database_unavailable", str(exc))
    if isinstance(exc, (FolderError, ManagementError, AskError)):
        return ApiError(exc.code, str(exc))
    if isinstance(exc, (SearchError, EvaluationError)):
        return ApiError("invalid_parameter", str(exc))
    if isinstance(exc, GenerationError):
        return ApiError("llm_unavailable", str(exc))
    if isinstance(exc, LoaderError):
        return ApiError("unsupported_file", str(exc))
    if isinstance(exc, (IngestError, EmbeddingError)):
        return ApiError("internal_error", str(exc))
    if isinstance(exc, psycopg.OperationalError):
        return ApiError("database_unavailable", "Banco indisponível. Confira o PostgreSQL e a DATABASE_URL.")
    if isinstance(exc, psycopg.errors.UndefinedTable):
        return ApiError("database_unavailable", "Esquema do banco ausente. Execute POST /api/v1/db/init.")
    log.exception("Erro inesperado", exc_info=exc)
    return ApiError("internal_error", "Erro inesperado. Veja o log do servidor.")


def error_response(error: ApiError) -> JSONResponse:
    body = {"error": {"code": error.code, "message": error.message, "details": error.details}}
    return JSONResponse(body, status_code=error.status)


def register_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        details = {"fields": [{"loc": list(e["loc"]), "message": e["msg"]} for e in exc.errors()]}
        return error_response(ApiError("validation_error", "Requisição fora do esquema.", details))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return error_response(ApiError("not_found", "Recurso não encontrado."))
        return error_response(ApiError("invalid_parameter", str(exc.detail), status=exc.status_code))

    async def _expected(request: Request, exc: Exception):
        return error_response(to_api_error(exc))

    # erros esperados dos serviços: tratados aqui, sem traceback no log
    for expected in (
        db.DbError, FolderError, ManagementError, AskError, SearchError, EvaluationError,
        GenerationError, LoaderError, IngestError, EmbeddingError, psycopg.OperationalError,
        psycopg.errors.UndefinedTable,
    ):
        app.add_exception_handler(expected, _expected)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        return error_response(to_api_error(exc))  # inesperado: corpo sem traceback, log com traceback
