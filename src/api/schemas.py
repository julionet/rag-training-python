"""Modelos de request da API (F14). A validação de valores (método, top_k) fica nas rotas, que devolvem 400."""

from pydantic import BaseModel

from src.retrieval import FETCH_K, TOP_K


class SearchRequest(BaseModel):
    question: str
    method: str = "rrf"
    top_k: int = TOP_K
    fetch_k: int = FETCH_K
    folder: str | None = None


class AskRequest(SearchRequest):
    pass


class IngestRequest(BaseModel):
    path: str
    recursive: bool | None = None
    force: bool = False
    prune: bool = False
    confirm_prune: bool = False


class ReindexRequest(BaseModel):
    path: str | None = None
    all: bool = False
    prune: bool = False
    confirm_prune: bool = False


class EvaluationRequest(BaseModel):
    questions_file: str | None = None
    strategies: list[str] = ["structured", "recursive", "sentence", "fixed"]
    max_chars: list[int] = [500, 900, 1400]
    methods: list[str] = ["rrf", "semantic", "lexical"]
    top_k: int = TOP_K
    answers: bool = False


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict = {}
