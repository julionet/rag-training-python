import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import psycopg

from src import config, db, repository
from src.chunking import MAX_CHARS, OVERLAP_CHARS, chunk_pages
from src.embeddings import EmbeddingError, embed_chunks
from src.evaluation import (
    EvalSet,
    EvaluationError,
    Metrics,
    ROOT,
    ThresholdRow,
    first_hit_rank,
    is_hit,
    load_questions,
    retrieval_metrics,
    suggest_threshold,
    threshold_table,
)
from src.loaders import load_document
from src.retrieval import FETCH_K, SearchHit, search
from src.search_service import EmbedderCache, EmbedderSource

Progress = Callable[[str], None]


@dataclass
class ConfigResult:
    strategy: str
    max_chars: int
    chunk_count: int
    metrics: dict[str, Metrics]  # método -> métricas
    gate_hits: dict[str, list[SearchHit]] = field(default_factory=dict)  # id da pergunta -> trechos (método do limiar)


@dataclass(frozen=True)
class AnswerResult:
    question_id: str
    status: str  # "ok" | "fail" | "no_base"
    detail: str
    called_claude: bool = False


@dataclass
class EvalOutcome:
    eval_set: EvalSet
    top_k: int
    ks: list[int]
    methods: list[str]
    main_method: str
    configs: list[ConfigResult]
    best: ConfigResult
    gate_method: str | None  # "rrf" ou "semantic"; None sem busca vetorial
    threshold_rows: list[ThresholdRow]
    suggestion: float | None
    answers: list[AnswerResult] | None
    answers_method: str
    elapsed: float


def _overlap(max_chars: int) -> int:
    return round(max_chars * OVERLAP_CHARS / MAX_CHARS)  # mesma proporção do padrão (T8)


def _create_temp_tables(conn: psycopg.Connection) -> None:
    """Tabelas temporárias `chunks` e `documents` escondem as reais na conexão (T1)."""
    for table in ("documents", "chunks"):
        conn.execute(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING DEFAULTS INCLUDING GENERATED)")


def _load_config(conn, docs, strategy, max_chars, embedder) -> int:
    """Divide, vetoriza e grava os documentos nas tabelas temporárias. Devolve o nº de trechos."""
    conn.execute("DELETE FROM pg_temp.chunks")
    conn.execute("DELETE FROM pg_temp.documents")
    chunk_id = 0
    total = 0
    for doc_id, (path, doc) in enumerate(docs, 1):
        model = embedder.model if strategy == "semantic" else None
        chunks = list(chunk_pages(doc.pages, strategy, model, max_chars, _overlap(max_chars)))
        if embedder:
            pairs = list(embed_chunks(embedder, chunks))
        else:
            zero = np.zeros(db.EMBEDDING_DIM, dtype=np.float32)  # sem busca vetorial, o vetor não é usado
            pairs = [(c, zero) for c in chunks]
        conn.execute(
            "INSERT INTO pg_temp.documents (id, source_path, filename, file_type, sha256, pages, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, 'indexed')",
            (doc_id, str(path.resolve()), doc.filename, doc.file_type, doc.sha256, len(doc.pages)),
        )
        rows = []
        for chunk, vector in pairs:
            chunk_id += 1
            rows.append((chunk_id, doc_id, chunk.chunk_index, chunk.page, chunk.section, chunk.content, vector))
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO pg_temp.chunks (id, document_id, chunk_index, page, section, content, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                rows,
            )
        total += len(rows)
    return total


def _evaluate_config(conn, eval_set, vectors, strategy, max_chars, chunk_count, methods, gate_method, top_k, ks):
    metrics: dict[str, Metrics] = {}
    gate_hits: dict[str, list[SearchHit]] = {}
    fetch_k = max(FETCH_K, top_k)
    answerable = [q for q in eval_set.questions if q.answerable]
    for method in methods:
        ranks = []
        for q in answerable:
            hits = search(conn, q.text, vectors.get(q.id), method, top_k, fetch_k)
            ranks.append(first_hit_rank(hits, q.expected))
            if method == gate_method:
                gate_hits[q.id] = hits
        metrics[method] = retrieval_metrics(ranks, ks)
    if gate_method:
        for q in eval_set.questions:
            if not q.answerable:
                gate_hits[q.id] = search(conn, q.text, vectors.get(q.id), gate_method, top_k, fetch_k)
    return ConfigResult(strategy, max_chars, chunk_count, metrics, gate_hits)


def _run_answers(eval_set, method, top_k, embedder_source, progress: Progress) -> list[AnswerResult]:
    from src.answer_service import is_not_found, run_ask

    conn = db.connect()
    try:
        missing = {
            p.name for p in eval_set.documents if repository.find_by_path(conn, str(p.resolve())) is None
        }
    finally:
        conn.close()
    for name in sorted(missing):
        print(
            f"Documento não cadastrado na base: {name}. Cadastre com: python -m src.cli ingest data/avaliacao",
            file=sys.stderr,
        )

    folder = str(ROOT / "data")  # cobre as três pastas do corpus e exclui o resto da base
    results = []
    total = len(eval_set.questions)
    for number, q in enumerate(eval_set.questions, 1):
        progress(f"[{number}/{total}] {q.id}")
        absent = sorted({e.file for e in q.expected} & missing)
        if absent:
            results.append(AnswerResult(q.id, "no_base", f"{', '.join(absent)} não cadastrado"))
            continue
        outcome = run_ask(q.text, method, top_k, FETCH_K, folder, embedder_source=embedder_source)
        called = outcome.answer_elapsed > 0
        if outcome.search.status != "ok":
            results.append(AnswerResult(q.id, "fail", "base vazia ou sem documentos na pasta de dados", called))
        elif not q.answerable:
            if outcome.answer is not None and is_not_found(outcome.answer):
                detail = "não encontrei" + ("" if called else ", sem chamar o Claude")
                results.append(AnswerResult(q.id, "ok", detail, called))
            else:
                results.append(AnswerResult(q.id, "fail", 'respondeu com informação; esperado "não encontrei"', called))
        elif outcome.answer is None or is_not_found(outcome.answer):
            results.append(AnswerResult(q.id, "fail", 'respondeu "não encontrei"; esperado a informação', called))
        else:
            right = [hit for _, hit in outcome.sources if is_hit(hit, q.expected)]
            if right:
                results.append(AnswerResult(q.id, "ok", f"fonte: {right[0].filename}, p. {right[0].page}", called))
            else:
                results.append(AnswerResult(q.id, "fail", "a fonte citada não confere com o esperado", called))
    return results


def run_eval(
    questions_path: str | Path,
    strategies: Sequence[str],
    max_chars_list: Sequence[int],
    methods: Sequence[str],
    top_k: int,
    answers: bool = False,
    progress: Progress | None = None,
    embedder_source: EmbedderSource | None = None,
) -> EvalOutcome:
    """Fluxo da seção 4.1 da F11. Nunca grava nas tabelas reais (T1)."""
    progress = progress or (lambda message: None)
    started = time.perf_counter()
    if answers:
        for name in ("ANTHROPIC_API_KEY", "LLM_MODEL"):
            if not getattr(config, name):
                raise EvaluationError(f"{name} não definida. Copie .env.example para .env e preencha.")

    eval_set = load_questions(questions_path)
    docs = [(p, load_document(p)) for p in eval_set.documents]
    methods = list(methods)
    need_model = any(m in ("rrf", "semantic") for m in methods) or "semantic" in strategies
    gate_method = "rrf" if "rrf" in methods else ("semantic" if "semantic" in methods else None)
    main_method = "rrf" if "rrf" in methods else methods[0]
    ks = sorted({k for k in (1, 3, top_k) if k <= top_k})
    cache = embedder_source or EmbedderCache()

    conn = db.connect()
    configs: list[ConfigResult] = []
    try:
        embedder, vectors = None, {}
        if need_model:
            model_name = config.EMBEDDING_MODEL
            if not model_name:
                raise EmbeddingError("EMBEDDING_MODEL não definida. Copie .env.example para .env e preencha.")
            db.ensure_embedding_model(conn, model_name)  # falha antes de carregar o modelo
            embedder = cache(model_name)
            progress("Vetorizando as perguntas")
            matrix = embedder.embed([q.text for q in eval_set.questions])
            vectors = {q.id: matrix[i] for i, q in enumerate(eval_set.questions)}

        combos = [(s, m) for s in strategies for m in max_chars_list]
        with conn.transaction():
            _create_temp_tables(conn)
            for number, (strategy, max_chars) in enumerate(combos, 1):
                progress(f"[{number}/{len(combos)}] {strategy} {max_chars}")
                count = _load_config(conn, docs, strategy, max_chars, embedder)
                configs.append(
                    _evaluate_config(
                        conn, eval_set, vectors, strategy, max_chars, count, methods, gate_method, top_k, ks
                    )
                )
            raise psycopg.Rollback()  # descarta as tabelas temporárias
    finally:
        conn.close()

    best = configs[0]
    for result in configs[1:]:
        a, b = result.metrics[main_method], best.metrics[main_method]
        if (a.mrr, a.hit_at[1]) > (b.mrr, b.hit_at[1]):
            best = result

    rows: list[ThresholdRow] = []
    suggestion = None
    if gate_method:
        with_answer = [best.gate_hits[q.id] for q in eval_set.questions if q.answerable]
        without = [best.gate_hits[q.id] for q in eval_set.questions if not q.answerable]
        rows = threshold_table(with_answer, without, gate_method)
        suggestion = suggest_threshold(rows)

    answer_results = None
    if answers:
        answer_results = _run_answers(eval_set, main_method, top_k, cache, progress)

    return EvalOutcome(
        eval_set, top_k, ks, methods, main_method, configs, best, gate_method, rows, suggestion,
        answer_results, main_method, time.perf_counter() - started,
    )
