import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")

LLM_MODEL = os.getenv("LLM_MODEL")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")

DATABASE_URL = os.getenv("DATABASE_URL")

# limiar mínimo de similaridade (cosseno) do melhor trecho; vazio = sem limiar (F11)
RELEVANCE_THRESHOLD = os.getenv("RELEVANCE_THRESHOLD", "0.50")  # definido na medição da F11 (spec, seção 14)

# API REST (F14): só local por padrão; a API não tem autenticação
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
