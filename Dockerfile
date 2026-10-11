# Imagem única da aplicação (API e CLI). Spec: .spec/features/F15-conteineres.md
# Funciona em linux/amd64 e linux/arm64 (sem `platform:` fixada).

# ---- etapa 1: dependências -------------------------------------------------
FROM python:3.12-slim AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# torch em versão CPU primeiro (no amd64 o pacote padrão traz bibliotecas CUDA);
# o PyPI continua como fonte extra, caso alguma plataforma não tenha o pacote CPU.
RUN pip install torch --extra-index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# ---- etapa 2: imagem final -------------------------------------------------
FROM python:3.12-slim

ARG APP_UID=1000
ARG APP_GID=1000

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN groupadd --gid ${APP_GID} app \
    && useradd --uid ${APP_UID} --gid ${APP_GID} --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /cache/huggingface /data/docs \
    && chown -R app:app /cache

COPY --from=build /opt/venv /opt/venv

WORKDIR /app
COPY src ./src
COPY sql ./sql
# o `eval` lê data/avaliacao/perguntas.json a partir da raiz do projeto
COPY data/avaliacao ./data/avaliacao

USER app

# Segredos e DATABASE_URL vêm do Compose, nunca da imagem.
CMD ["python", "-m", "src.cli"]
