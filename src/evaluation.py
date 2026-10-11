import json
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.retrieval import SearchHit, passes_relevance

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUESTIONS = ROOT / "data" / "avaliacao" / "perguntas.json"

THRESHOLD_CANDIDATES = [round(0.30 + 0.05 * i, 2) for i in range(11)]  # 0,30 a 0,80
KEEP_TARGET = 0.95  # fração mínima das perguntas com resposta que o limiar proposto deve manter (T6)


class EvaluationError(Exception):
    """Erro esperado, com mensagem já pronta para a pessoa."""


@dataclass(frozen=True)
class Expected:
    file: str
    text: str
    page: int | None = None


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    language: str | None
    expected: tuple[Expected, ...]

    @property
    def answerable(self) -> bool:
        return bool(self.expected)


@dataclass(frozen=True)
class EvalSet:
    documents: list[Path]
    questions: list[Question]


def normalize(text: str) -> str:
    """Minúsculas, sem acentos e com espaços repetidos reduzidos (T3)."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", plain).strip()


def _invalid(reason: str) -> EvaluationError:
    return EvaluationError(f"Arquivo de perguntas inválido: {reason}.")


def _parse_expected(qid: str, raw: object, files: set[str]) -> tuple[Expected, ...]:
    if not isinstance(raw, list):
        raise EvaluationError(f"Pergunta {qid}: esperado ausente ou inválido.")
    result = []
    for item in raw:
        if not isinstance(item, dict):
            raise EvaluationError(f"Pergunta {qid}: esperado ausente ou inválido.")
        file, text, page = item.get("arquivo"), item.get("texto"), item.get("pagina")
        if not isinstance(file, str) or not file:
            raise EvaluationError(f"Pergunta {qid}: arquivo ausente ou inválido.")
        if not isinstance(text, str) or not text.strip():
            raise EvaluationError(f"Pergunta {qid}: texto ausente ou inválido.")
        if page is not None and (isinstance(page, bool) or not isinstance(page, int) or page <= 0):
            raise EvaluationError(f"Pergunta {qid}: pagina ausente ou inválido.")
        if file not in files:
            raise EvaluationError(f'Pergunta {qid}: arquivo "{file}" não está em documentos.')
        result.append(Expected(file, text, page))
    return tuple(result)


def load_questions(path: str | Path) -> EvalSet:
    """Lê e valida o arquivo de perguntas (seção 5.1) e confere que os documentos existem."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise _invalid(f"arquivo não encontrado: {path}") from None
    except (OSError, UnicodeDecodeError) as e:
        raise _invalid(f"não foi possível ler {path} ({type(e).__name__})") from None
    except json.JSONDecodeError as e:
        raise _invalid(f"JSON inválido na linha {e.lineno} ({e.msg})") from None
    if not isinstance(data, dict):
        raise _invalid("o conteúdo deve ser um objeto com documentos e perguntas")

    raw_docs, raw_questions = data.get("documentos"), data.get("perguntas")
    if not isinstance(raw_docs, list) or not raw_docs or not all(isinstance(d, str) and d for d in raw_docs):
        raise _invalid("documentos deve ser uma lista de caminhos")
    if not isinstance(raw_questions, list) or not raw_questions:
        raise _invalid("perguntas deve ser uma lista não vazia")

    documents = []
    for raw in raw_docs:
        doc = Path(raw) if Path(raw).is_absolute() else ROOT / raw
        if not doc.is_file():
            raise EvaluationError(f"Documento não encontrado: {raw}.")
        documents.append(doc)
    names = [d.name for d in documents]
    if len(set(names)) != len(names):
        raise _invalid("documentos com o mesmo nome de arquivo")

    questions, seen = [], set()
    for position, item in enumerate(raw_questions, 1):
        if not isinstance(item, dict):
            raise EvaluationError(f"Pergunta #{position}: não é um objeto.")
        qid, text = item.get("id"), item.get("pergunta")
        if not isinstance(qid, str) or not qid:
            raise EvaluationError(f"Pergunta #{position}: id ausente ou inválido.")
        if qid in seen:
            raise EvaluationError(f"Pergunta {qid}: id repetido.")
        seen.add(qid)
        if not isinstance(text, str) or not text.strip():
            raise EvaluationError(f"Pergunta {qid}: pergunta ausente ou inválido.")
        language = item.get("idioma")
        if language is not None and not isinstance(language, str):
            raise EvaluationError(f"Pergunta {qid}: idioma ausente ou inválido.")
        expected = _parse_expected(qid, item.get("esperado", []), set(names))
        questions.append(Question(qid, text.strip(), language, expected))
    return EvalSet(documents, questions)


def is_hit(hit: SearchHit, expected: Iterable[Expected]) -> bool:
    """O trecho vem do arquivo esperado e contém o texto-chave (e a página, se informada) (T3)."""
    content = normalize(hit.content)
    return any(
        hit.filename == e.file
        and (e.page is None or hit.page == e.page)
        and normalize(e.text) in content
        for e in expected
    )


def first_hit_rank(hits: Sequence[SearchHit], expected: Iterable[Expected]) -> int | None:
    """Posição (1-based) do primeiro acerto, ou None."""
    expected = tuple(expected)
    for position, hit in enumerate(hits, 1):
        if is_hit(hit, expected):
            return position
    return None


@dataclass(frozen=True)
class Metrics:
    hit_at: dict[int, float]  # k -> fração de perguntas com acerto até a posição k
    mrr: float


def retrieval_metrics(ranks: Sequence[int | None], ks: Iterable[int]) -> Metrics:
    """hit@k e MRR (T4) a partir da posição do 1º acerto de cada pergunta com resposta."""
    total = len(ranks)
    if total == 0:
        return Metrics({k: 0.0 for k in ks}, 0.0)
    hit_at = {k: sum(1 for r in ranks if r is not None and r <= k) / total for k in ks}
    mrr = sum(1 / r for r in ranks if r is not None) / total
    return Metrics(hit_at, mrr)


@dataclass(frozen=True)
class ThresholdRow:
    limit: float
    kept: float  # fração das perguntas com resposta que passam
    blocked: float  # fração das perguntas sem resposta que são barradas


def threshold_table(
    with_answer: Sequence[list[SearchHit]], without_answer: Sequence[list[SearchHit]], method: str
) -> list[ThresholdRow]:
    """Para cada limiar candidato, quanto se mantém e quanto se barra (T6), com a regra de `passes_relevance`."""

    def fraction(items: Sequence[list[SearchHit]], limit: float, passing: bool) -> float:
        if not items:
            return 0.0
        count = sum(1 for hits in items if passes_relevance(hits, method, limit) == passing)
        return count / len(items)

    return [
        ThresholdRow(limit, fraction(with_answer, limit, True), fraction(without_answer, limit, False))
        for limit in THRESHOLD_CANDIDATES
    ]


def suggest_threshold(rows: Sequence[ThresholdRow]) -> float | None:
    """Maior candidato que mantém ao menos 95% das perguntas com resposta (T6), ou None."""
    ok = [r.limit for r in rows if r.kept >= KEEP_TARGET]
    return max(ok) if ok else None
