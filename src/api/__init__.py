"""API REST do RAG (F14): as mesmas operações da CLI por HTTP, sem autenticação."""

from fastapi import FastAPI

from src.api.errors import register_handlers
from src.api.jobs import JobStore
from src.api.routes import router
from src.search_service import EmbedderCache


def create_app() -> FastAPI:
    # sem CORS: nenhuma página de outro endereço chama a API pelo navegador
    app = FastAPI(title="RAG Training API", version="1")
    app.state.jobs = JobStore()
    app.state.embedder_cache = EmbedderCache()  # modelo carregado uma vez, na primeira chamada que precisa dele
    register_handlers(app)
    app.include_router(router, prefix="/api/v1")
    return app
