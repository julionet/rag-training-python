# F15 — Contêineres (Dockerfile e Docker Compose)

| Campo | Valor |
|---|---|
| **Status da spec** | Aprovada (2026-10-11) |
| **Status da implementação** | Verificada (2026-10-11) |
| **Marco** | M6 (ver ROADMAP) |
| **Depende de** | F01, F05–F09 (comandos da CLI); F14 para o serviço `api` |
| **Regras de negócio** | Nenhuma nova. R10 e as demais continuam valendo, sem mudança |
| **Seções da arquitetura** | §15 Contêineres, §8 CLI, §8.1 API REST, §9 Configuração |

## 1. Objetivo
Permitir que qualquer pessoa da equipe suba o banco (PostgreSQL com pgvector) e a aplicação (API e CLI) com `docker compose up`, sem instalar PostgreSQL, pgvector nem Python na máquina, com o mesmo `Dockerfile` e o mesmo `docker-compose.yml` em macOS, Windows e Linux.

## 2. Escopo

**Inclui**
- `Dockerfile` único (uma imagem para a API e para a CLI), `docker-compose.yml`, `.dockerignore`, `.gitattributes` e, se necessário, um script de entrada em `docker/`.
- Serviços `db`, `api` e `cli` (perfil `tools`).
- Volumes nomeados para os dados do PostgreSQL e para o cache do modelo de embeddings; pasta de documentos montada somente leitura.
- Fixação das versões das 7 bibliotecas diretas no `requirements.txt` e da versão do Python da imagem.
- `.env.example` ampliado e seção "Docker" no `README.md` (comandos para bash e PowerShell, requisitos, backup).
- Roteiro manual executado nos três sistemas oficiais.

**Não inclui**
- Kubernetes ou outra orquestração, HTTPS, proxy reverso, CI/CD, publicação em registry.
- GPU no contêiner (o `Embedder` só conhece MPS e CPU; no contêiner roda sempre em CPU).
- Autenticação da API e uso em servidor da equipe (só uso local nesta fase).
- Migrar uma base local existente para o Docker: a base do Docker começa vazia.
- Mudanças em regras de negócio, no esquema SQL ou na lógica dos serviços. A única mudança de código previsível é nenhuma (ver seção 5); se aparecer, a spec é atualizada antes.

## 3. Regras de negócio aplicáveis

| Regra | O que significa nesta feature |
|---|---|
| R10 | A confirmação de remoção continua obrigatória. Na CLI via `docker compose run`, é preciso terminal interativo (`-it`, que o Compose liga por padrão); sem terminal, o `delete` recusa, como hoje. |
| R11 | Continua valendo: os trechos usados em `ask` são enviados ao provedor de LLM. A imagem não muda isso. |
| Demais | Sem mudança. Os resultados de `search` e `ask` devem ser iguais aos da instalação local. |

## 4. Comportamento esperado

### 4.1 Fluxo principal
1. A pessoa copia `.env.example` para `.env` e preenche `ANTHROPIC_API_KEY`, `POSTGRES_PASSWORD` e `DOCS_DIR` (pasta de documentos do computador).
2. `docker compose build` constrói a imagem da aplicação.
3. `docker compose up -d` sobe o `db` (volume novo: cria usuário, banco e extensão `vector`) e, quando o `db` está saudável, a `api`.
4. `docker compose run --rm cli init-db` aplica as migrações (passo explícito, nada automático).
5. `docker compose run --rm cli check` confere ambiente, banco e variáveis.
6. `docker compose run --rm cli ingest /data/docs` cadastra os documentos. No primeiro uso, o modelo `BAAI/bge-m3` é baixado para o volume de cache (precisa de internet).
7. `docker compose run --rm cli ask "pergunta"` ou `POST http://127.0.0.1:8000/api/v1/ask` respondem como na instalação local.
8. `docker compose down` para tudo sem apagar dados; `docker compose up -d` volta com banco e modelo intactos. `down -v` apaga os volumes (e portanto a base).

### 4.2 Fluxos alternativos e erros

| Situação | Comportamento esperado | Mensagem / saída |
|---|---|---|
| `.env` sem `POSTGRES_PASSWORD` | O Compose recusa subir | `required variable POSTGRES_PASSWORD is missing a value` (usa `${POSTGRES_PASSWORD:?...}` com mensagem em português) |
| `.env` sem `DOCS_DIR` | O Compose recusa subir | Mensagem em português indicando a variável |
| `cli ingest` antes de `init-db` | Erro claro já existente da F01/F05 | Mensagem atual da aplicação |
| Sem internet no primeiro uso | O download do modelo falha; nada é gravado no banco | Erro do Hugging Face repassado pela aplicação |
| Volume do banco já existente | `setup_admin.sql` **não** roda de novo (comportamento da imagem); senha antiga prevalece | Documentado no README (trocar a senha exige `ALTER ROLE` ou `down -v`) |
| Pasta de `DOCS_DIR` inexistente | Compose cria/recusa conforme o sistema | README orienta a criar a pasta antes |
| Caminho do computador usado no comando (ex.: `/Users/ana/docs`) | `ingest` falha com "arquivo ou pasta não encontrado" | Mensagem atual; README lembra de usar `/data/docs/...` |
| Memória do Docker abaixo de 4 GB | Processo pode ser encerrado (código 137) ao carregar o modelo | README documenta o mínimo e como ajustar |
| Porta 8000 ocupada no computador | O Compose falha ao publicar | README explica `API_PORT` no `.env` (porta do host) |

### 4.3 Saída para a pessoa
```
$ docker compose ps
NAME             SERVICE   STATUS                   PORTS
rag-db           db        Up (healthy)             5432/tcp
rag-api          api       Up (healthy)             127.0.0.1:8000->8000/tcp

$ curl http://127.0.0.1:8000/api/v1/health
{"status": "ok"}
```
O `5432/tcp` aparece só como porta exposta na rede interna do Compose, **sem** publicação no computador.

## 5. Interface

**Comandos** (não há comando novo na CLI nem endpoint novo na API)

| Comando | Argumentos e opções | Descrição |
|---|---|---|
| `docker compose build` | | Constrói a imagem da aplicação |
| `docker compose up -d` | | Sobe `db` e `api` |
| `docker compose run --rm cli <comando>` | Qualquer comando da CLI (`init-db`, `check`, `ingest`, `reindex`, `search`, `ask`, `folders`, `list`, `delete`, `eval`) | Executa a CLI na mesma imagem, em um contêiner descartável (perfil `tools`) |
| `docker compose down` / `down -v` | | Para tudo / para e apaga volumes (**apaga a base**) |

**Arquivos**

| Arquivo | Responsabilidade |
|---|---|
| `Dockerfile` | Multi-etapas: etapa de construção instala as dependências (torch em versão CPU, versões fixadas); etapa final copia só `src/`, `sql/`, `data/avaliacao/` (o `eval` lê `data/avaliacao/perguntas.json` a partir da raiz do projeto, `src/evaluation.py`) e as dependências, roda como usuário sem privilégio. `CMD ["python", "-m", "src.cli"]` (sem `ENTRYPOINT`, para a `api` poder trocar o comando por `python -m src.api`; a `cli` define o `entrypoint` no Compose). Sem `torch` com CUDA: instalado do índice CPU do PyTorch |
| `docker-compose.yml` | Serviços `db`, `api`, `cli`; volumes; rede; saúde; variáveis |
| `.dockerignore` | Exclui `.env` e `.env.*`, `.venv`, `.git`, `.claude`, `.spec`, `__pycache__`, `*.pyc`, `.DS_Store`, `data/amostras/real.pdf`, `data/amostras/grande.pdf` e `scripts/` do contexto. Mantém `.env.example` fora também (não é usado na imagem) |
| `.gitattributes` | `*.sh text eol=lf` e `*.sql text eol=lf` (o Git no Windows converteria para CRLF e quebraria os scripts dentro do contêiner) |
| `docker/init-db.sh` | Script de inicialização do banco (LF, ver `.gitattributes`): chama `sql/setup_admin.sql` com a senha. Montado em `/docker-entrypoint-initdb.d/` |
| `requirements.txt` | Versões das 7 bibliotecas diretas fixadas com `==` (seção 8) |

**Serviços do Compose**

| Serviço | Imagem | Detalhes |
|---|---|---|
| `db` | `pgvector/pgvector:0.8.7-pg18` (tag fixada, ver seção 11) | Volume nomeado `rag_pgdata` montado em `/var/lib/postgresql`, sem `PGDATA` (ver seção 11). `POSTGRES_PASSWORD` do `.env`. `docker/init-db.sh` montado em `/docker-entrypoint-initdb.d/` (só roda com volume novo) chama o `sql/setup_admin.sql`, montado somente leitura em `/sql/`, passando a senha por `-v rag_password`: `rag_user` **não** é superusuário. (O `setup_admin.sql` sozinho em `initdb.d` não serviria: ele exige `-v rag_password` e sai sem fazer nada quando falta.) Healthcheck `pg_isready -h 127.0.0.1 -U rag_user -d rag_training_db` (com `-h 127.0.0.1` só fica saudável depois da inicialização: o servidor temporário da primeira subida não escuta em TCP). **Sem `ports`**. |
| `api` | imagem da aplicação | `command: python -m src.api`, `API_HOST=0.0.0.0` e `API_PORT=8000` **dentro** do contêiner (o `API_PORT` do `.env` vale só para a porta do computador), porta publicada `127.0.0.1:${API_PORT:-8000}:8000`. `depends_on: db: condition: service_healthy`. Healthcheck chama `GET /api/v1/health` com o Python da imagem (sem instalar `curl`). Volumes: cache do modelo e documentos. |
| `cli` | mesma imagem | `profiles: ["tools"]`, `entrypoint: ["python", "-m", "src.cli"]`, mesmos volumes e variáveis da `api`, `depends_on` o `db` saudável. Não sobe com `up`. |

**Variáveis definidas pelo Compose para `api` e `cli`** (sobrepõem o `.env` do desenvolvimento local, sem editá-lo):
`DATABASE_URL=postgresql://rag_user:${POSTGRES_PASSWORD}@db:5432/rag_training_db`, `HF_HOME=/cache/huggingface`, `API_HOST=0.0.0.0`, `API_PORT=8000`. `ANTHROPIC_API_KEY`, `HF_TOKEN`, `LLM_MODEL`, `EMBEDDING_MODEL` e `RELEVANCE_THRESHOLD` vêm do `.env` por `env_file`/`environment`.

## 6. Dados
Sem mudanças no esquema nem em migrações. Persistência por volumes nomeados:

| Volume | Conteúdo | Observação |
|---|---|---|
| `rag_pgdata` | Dados do PostgreSQL (única cópia dos vetores) | Backup por `pg_dump` (seção 4 do README) |
| `rag_hfcache` | Cache do Hugging Face (`HF_HOME`), ~4,3 GB (medido em 2026-10-11) | Perde-se só tempo: o modelo é baixado de novo |
| Bind `DOCS_DIR` → `/data/docs` | Documentos, **somente leitura** | Não é volume nomeado; é a pasta da pessoa |

A tabela `sources` guarda os caminhos **de dentro do contêiner** (`/data/docs/...`).

## 7. Configuração

| Parâmetro | Padrão | Onde se define |
|---|---|---|
| `POSTGRES_PASSWORD` | sem padrão (obrigatória) | `.env` (nunca versionado) |
| `DOCS_DIR` | sem padrão (obrigatória) | `.env`; exemplos: `~/docs` (macOS/Linux), `C:\Users\ana\docs` (Windows) |
| `API_PORT` | `8000` | `.env`; porta **do computador** em `127.0.0.1` (dentro do contêiner é sempre 8000) |
| `APP_UID` / `APP_GID` | `1000` | `.env` e argumentos de build; só relevantes no Linux, para o usuário do contêiner ler o bind mount |
| `ANTHROPIC_API_KEY`, `LLM_MODEL`, `HF_TOKEN`, `EMBEDDING_MODEL`, `RELEVANCE_THRESHOLD` | como no `.env.example` atual | `.env` |
| `DATABASE_URL`, `HF_HOME`, `API_HOST` | definidas pelo Compose | `docker-compose.yml` |

O `.env.example` ganha um bloco "Docker" com `POSTGRES_PASSWORD=<SENHA>`, `DOCS_DIR=` e `API_PORT=8000`, mantendo o placeholder `<SENHA>`. A senha **nunca** aparece em arquivo versionado nem em `ENV` do Dockerfile.

## 8. Dependências externas

- **Docker Engine/Desktop** com **Docker Compose v2** (`docker compose`). Versão mínima a registrar no README ao fechar a implementação (referência da máquina de desenvolvimento: Docker 29.8.2, Compose 5.5.1).
- **Imagem do banco:** `pgvector/pgvector` com **tag fixada por versão** (`0.8.7-pg18`, ver seção 11). **Conferido em 2026-10-11 no Docker Hub:** a tag `0.8.7-pg18` existe e publica `linux/amd64` e `linux/arm64`.
- **Imagem base da aplicação:** `python:3.12-slim` (a mesma versão do `.venv`, 3.12.14). **Conferido:** publica amd64 e arm64.
- **Bibliotecas diretas** (versões do `.venv` que funcionam hoje, a fixar com `==`):

  | Pacote | Versão |
  |---|---|
  | `anthropic` | 1.8.0 |
  | `sentence-transformers` | 6.1.0 |
  | `numpy` | 2.5.3 |
  | `python-dotenv` | 1.2.3 |
  | `psycopg[binary]` | 3.3.6 |
  | `pymupdf4llm` | 1.28.2 |
  | `pgvector` | 0.5.1 |
  | `fastapi` | 0.141.1 |
  | `uvicorn` | 0.54.0 |

  (São 9 linhas no arquivo, contando `fastapi` e `uvicorn` da F14; o ARQUITETURA §15 fala em "7" por ter sido escrito antes. Esta spec fixa **todas as 9**.)
- **Pacotes para amd64 e arm64, conferidos no PyPI (2026-10-11):** `torch` 2.14.x, `numpy`, `psycopg-binary` e `pymupdf` (`cp310-abi3`) têm wheels `manylinux` para `x86_64` e `aarch64`. `pymupdf4llm` é Python puro.
- **`torch` em versão CPU:** instalado antes do restante, a partir do índice `https://download.pytorch.org/whl/cpu`, para a imagem não carregar bibliotecas CUDA no amd64. Dependências indiretas (como `torch` e `transformers`) não são travadas.
- Internet no primeiro uso (download do modelo) e para a API do provedor de LLM.

## 9. Critérios de aceite — roteiro de teste manual

**Pré-condições:** Docker com Compose v2 funcionando; ≥ 4 GB de memória para o Docker; ~8 GB de disco livres; `.env` preenchido com `ANTHROPIC_API_KEY`, `POSTGRES_PASSWORD` e `DOCS_DIR` apontando para uma pasta que contenha uma cópia de `data/amostras/` e `data/manual_colaborador.txt`; nenhum volume `rag_*` pré-existente (`docker volume ls`). Executar o roteiro completo em cada sistema oficial.

| # | Passo | Comando / ação | Resultado esperado |
|---|---|---|---|
| 1 | Construir a imagem | `docker compose build` | Termina sem erro. Funciona sem editar nenhum arquivo versionado |
| 2 | Imagem sem segredos | `docker history --no-trunc <imagem>` e `docker run --rm --entrypoint env <imagem>` | Nenhum `ANTHROPIC_API_KEY`, `HF_TOKEN` nem senha; sem `.env`, `.venv`, `.git`, `real.pdf` e `grande.pdf` (`docker run --rm --entrypoint ls <imagem> -a /app`) |
| 3 | Usuário sem privilégio | `docker compose run --rm --entrypoint id cli` | UID diferente de 0 |
| 4 | Subir com banco vazio | `docker compose up -d` e `docker compose ps` | `db` e `api` `healthy`. A `api` só inicia depois do `db` saudável |
| 5 | Rede do banco | `docker compose ps` e `docker compose port db 5432` | `db` sem porta publicada: a coluna `PORTS` mostra só `5432/tcp` e `port db 5432` não devolve endereço (no Compose 5.5.1 imprime `invalid IP:0`; `docker inspect` mostra `PortBindings` vazio). **Não usar `psql -h 127.0.0.1 -p 5432` do computador:** em quem já tem PostgreSQL local nessa porta, o teste conectaria no banco errado. A API aparece só como `127.0.0.1:8000` |
| 6 | API fora do alcance de outras máquinas | De outro computador da rede: `curl http://<IP-do-host>:8000/api/v1/health` | Conexão recusada |
| 7 | Saúde | `curl http://127.0.0.1:8000/api/v1/health` | `{"status": "ok"}` |
| 8 | Inicializar | `docker compose run --rm cli init-db` | Mensagem de sucesso e lista das migrações 001–003 aplicadas |
| 9 | Verificar | `docker compose run --rm cli check` | Itens `[OK]` para `DATABASE_URL` (host `db`), extensão `vector`, tabelas e `ANTHROPIC_API_KEY`. Embeddings sem aviso ainda (base vazia) |
| 10 | Cadastrar (1º uso) | `docker compose run --rm cli ingest /data/docs` | Modelo baixado para `rag_hfcache`; resumo com documentos novos e eventuais falhas esperadas (ex.: PDF sem texto) |
| 11 | Caminho errado | `docker compose run --rm cli ingest /Users/ana/docs` (ou caminho do computador) | Erro claro de arquivo/pasta não encontrado |
| 12 | Buscar | `docker compose run --rm cli search "E-5107"` | Mesmo trecho e mesma ordem da instalação local (F06) |
| 13 | Perguntar | `docker compose run --rm cli ask "posso trabalhar de casa?"` | Resposta em português com fontes (F07), igual à da instalação local |
| 14 | API | `POST /api/v1/ask` com a mesma pergunta; `GET /api/v1/folders` | Mesmo conteúdo do passo 13; `folders` lista `/data/docs` |
| 15 | Documentos somente leitura | `docker compose run --rm --entrypoint sh cli -c "touch /data/docs/x"` | Falha por sistema de arquivos somente leitura |
| 16 | Persistência | `docker compose down`, depois `docker compose up -d`, depois `cli list` | Documentos e trechos continuam. O `ask` do passo 13 **não baixa o modelo de novo** (sem mensagem de download) |
| 17 | Reiniciar a máquina/Docker | Reiniciar o Docker e repetir `up -d` e passo 16 | Mesmo resultado |
| 18 | Reindexar sem mudança | `docker compose run --rm cli reindex --all` | Tudo "sem mudança" (R5/R6 com caminhos do contêiner) |
| 19 | Remoção | `docker compose run --rm cli delete /data/docs/<arquivo>` e responder `s` | Pede confirmação e remove; o arquivo no computador continua intacto |
| 20 | Backup | `docker compose exec db pg_dump -U rag_user rag_training_db > backup.sql` | Arquivo não vazio. (Restauração conforme README) |
| 21 | Paridade entre sistemas | Comparar a saída dos passos 12 e 13 entre macOS, Windows e Linux | Mesmos trechos e mesma ordem (a redação da resposta do LLM pode variar levemente; as fontes devem coincidir) |
| 22 | Variáveis obrigatórias | Remover `POSTGRES_PASSWORD` do `.env` e rodar `docker compose config` | Erro em português pedindo a variável |
| 23 | Apagar volumes | `docker compose down -v`, depois `up -d` e `init-db` | Base vazia de novo (confirma que `down` sem `-v` é o que preserva) |
| 24 | Tempo de `grande.pdf` | Cadastrar `grande.pdf` (copiado para `DOCS_DIR`) com `ingest` | Conclui; registrar o tempo na seção 14 (sem meta fixa) |
| 25 | Windows: fim de linha | No Windows, clonar o repositório e rodar os passos 1, 4 e 8 | O `setup_admin.sql` montado roda sem erro (LF preservado pelo `.gitattributes`) |
| 26 | Linux: permissão | No Ubuntu, `DOCS_DIR` com arquivos do usuário `1000` e do usuário `1001` | Com `APP_UID`/`APP_GID` corretos o `ingest` lê os arquivos; caso contrário, o erro é claro e o README explica o ajuste |

**Consultas úteis para conferir o banco**
```
docker compose exec db psql -U rag_user -d rag_training_db -c "SELECT count(*) FROM documents;"
docker compose exec db psql -U rag_user -d rag_training_db -c "SELECT path FROM sources;"
```

## 10. Impacto em outras features

| Feature | Roteiros a repetir (#) | Motivo |
|---|---|---|
| F01 | `init-db` e `check` (passos 8 e 9 desta spec) | Novo ambiente de execução e `DATABASE_URL` com host `db` |
| F05 / F08 | `ingest` e `reindex` de pasta | Caminhos agora são os do contêiner |
| F06 / F07 | `search` e `ask` | Paridade de resultados |
| F09 | `list` e `delete` | Confirmação com terminal do contêiner |
| F14 | `GET /health` e os demais endpoints, em especial `ask` e um `ingest` com `/jobs/{id}` | API escutando em `0.0.0.0` dentro do contêiner |
| Instalação local | `pip install -r requirements.txt` em um ambiente limpo e `check` | O `requirements.txt` agora tem versões fixadas |

## 11. Riscos e decisões

**Decisões tomadas** (ARQUITETURA §15, 2026-10-11)
- Uso só local; API em `127.0.0.1`; banco sem porta publicada.
- Uma imagem e um `Dockerfile`; `api` e `cli` (perfil `tools`) usam a mesma.
- Documentos por `DOCS_DIR`, somente leitura em `/data/docs`; base do Docker começa vazia.
- Imagem do banco `pgvector/pgvector` com tag fixada por versão (`0.8.7-pg18`).
- Versões diretas fixadas com `==`; indiretas não.
- Suporte oficial: macOS Apple Silicon, Windows 11 (Docker Desktop com WSL 2), Ubuntu LTS 22.04/24.04 (amd64); uma pessoa da equipe por sistema.
- Modelo de embeddings em volume de cache, baixado no primeiro uso, não incluído na imagem.
- **Sem alteração de código da aplicação:** `API_HOST` e `DATABASE_URL` já vêm de variáveis de ambiente.
- **`data/avaliacao/` entra na imagem** (cerca de 25 KB) para o `eval` funcionar no contêiner; foi um ajuste feito na implementação, ao montar o `.dockerignore` (2026-10-11). Os documentos de `data/avaliacao/` são cadastrados com `ingest /app/data/avaliacao`.
- **Acesso ao banco por fora do contêiner não existe por padrão** (decisão do usuário, 2026-10-11): o banco do Docker não publica porta, então não disputa a 5432 com um PostgreSQL local. Acesso por `docker compose exec db psql -U rag_user -d rag_training_db`. A única porta do computador é a da API (`API_PORT`, padrão 8000; mudar se a API local estiver rodando ao mesmo tempo).
- Contêiner roda só em CPU. O `Embedder` usa MPS apenas quando disponível (o Docker no Mac não o expõe); isso é aceito.
- O ajuste do `requirements.txt` vale também para quem instala sem Docker.

**Riscos**
- Primeiro `ingest` lento (download de ~4,3 GB no volume + CPU) e mais memória: documentado.
- Se `torch` CPU no índice do PyTorch não existir para alguma plataforma, cair para o `torch` do PyPI (no arm64 já é CPU). A decisão é tomada ao construir.
- O healthcheck da `api` carrega o aplicativo, mas não o modelo (o `/health` não toca no banco): `healthy` não garante que o modelo já foi baixado.

**Decisões do alinhamento da spec** (2026-10-11)
- **Volume do PostgreSQL 18:** seguir o padrão da imagem. O volume `rag_pgdata` é montado em `/var/lib/postgresql`, **sem** definir `PGDATA`. Motivo: é o caminho que as imagens do PostgreSQL 18 passaram a adotar (dados em `/var/lib/postgresql/18/docker`), o que facilita atualizar de versão. **Conferido em 2026-10-11** (`docker run --rm pgvector/pgvector:pg18 env`): `PGDATA=/var/lib/postgresql/18/docker` e a imagem declara `VOLUME /var/lib/postgresql`, o que confirma o ponto de montagem.
- **Versão do pgvector:** fixar a **tag por versão** (`0.8.7-pg18`, igual ao pgvector do ambiente local), e não a tag móvel `pg18`. Motivo: reprodutibilidade e mesma versão do banco para toda a equipe, no mesmo espírito de fixar as bibliotecas Python. **Conferido em 2026-10-11:** a tag `0.8.7-pg18` existe em amd64 e arm64 e a imagem traz `default_version = '0.8.7'` e PostgreSQL 18.6, os mesmos do ambiente local. Atualizar a versão passa a ser uma decisão consciente.
- **Backup do banco:** responsabilidade de **quem roda o Compose**. O README documenta `pg_dump`, a restauração e o aviso de que `down -v` apaga a base; nada é automático e não há serviço de backup. Motivo: uso só local e base reconstruível a partir dos documentos. Se a base virar compartilhada, o backup entra na feature de servidor, junto da autenticação.

**Pontos em aberto:** nenhum. As conferências da imagem do banco foram feitas em 2026-10-11 (Docker 29.8.2, Compose 5.5.1, macOS arm64).

## 12. Documentação a atualizar
- `README.md`: seção "Docker" (requisitos e versões mínimas de Docker/Compose, passo a passo em bash e PowerShell, `DOCS_DIR` por sistema, caminhos `/data/docs`, backup e restauração com `pg_dump`, troca de senha, ajuste de memória no Docker Desktop e `.wslconfig`, internet no primeiro uso, aviso de que a base do Docker começa vazia).
- `.env.example`: bloco Docker (`POSTGRES_PASSWORD`, `DOCS_DIR`, `API_PORT`, `APP_UID`, `APP_GID`).
- `requirements.txt`: versões fixadas.
- `.spec/ARQUITETURA.md` §10 (estrutura: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.gitattributes`) e §15 (marcar como implementada).
- `.spec/ROADMAP.md`: status da F15 e do M6 (parcial, até a F16).
- `.spec/NEGOCIO.md` §9: marcar o item de contêiner como implementado.
- `.claude/CLAUDE.md`: mover a F15 de "planejada" para "implementada e verificada" ao concluir.

## 13. Definição de pronto
- [x] Spec aprovada pela pessoa responsável
- [x] Código implementado somente no que a spec descreve
- [x] Todos os passos do roteiro (seção 9) executados e aprovados, **em macOS (Apple Silicon), Windows 11 (WSL 2) e Ubuntu LTS (amd64)**
- [x] Roteiros de regressão (seção 10) repetidos
- [x] Documentação da seção 12 atualizada
- [x] Status atualizado nesta spec e no ROADMAP

## 14. Registro de verificação

**Execução 1 — macOS Apple Silicon (arm64), 2026-10-11** — Docker 29.8.2, Compose 5.5.1, executada por Claude Code a pedido do usuário. Parcial neste sistema; os passos pendentes foram concluídos depois, conforme a tabela final.

| # | Resultado | Observação |
|---|---|---|
| 1 | OK | `docker compose build` sem erro; imagem final 2,21 GB |
| 2 | OK | Sem `ANTHROPIC_API_KEY`, `HF_TOKEN`, senha nem `.env` no `history` e no `env`; `/app` só com `src`, `sql` e `data/avaliacao` |
| 3 | OK | `uid=1000(app)` |
| 4 | OK | `db` e `api` `healthy`; a `api` só iniciou depois do `db` |
| 5 | OK | `PortBindings` vazio; `docker compose port db 5432` imprime `invalid IP:0` |
| 6 | **Pendente** | Precisa de um segundo computador na rede. A publicação é `127.0.0.1:<API_PORT>->8000` |
| 7 | OK | `{"status":"ok"}` |
| 8 | OK | Migrações aplicadas (vector 0.8.7, 4 tabelas, 4 índices) |
| 9 | OK | `0 falhas, 1 aviso` (modelo ainda não registrado, esperado) |
| 10 | OK | 11 cadastrados, 4 falharam e 1 ignorado (os esperados dos arquivos de borda), 84,3 s com o download do modelo |
| 11 | OK | `Arquivo não encontrado: /Users/ana/docs` |
| 12 | OK | `E-5107` em 1º lugar (semântico #1 0,42, textual #1 1,00) |
| 13 | OK | Resposta em português com fonte `manual_colaborador.txt`, página 1, seção "Trabalho remoto" |
| 14 | OK | `POST /ask` com a mesma fonte; `GET /folders` lista `/data/docs` (11 documentos, 27 trechos) |
| 15 | OK | `Read-only file system` |
| 16 | OK | `down` e `up -d` sem `-v`: documentos intactos e `ask` sem novo download (cache do modelo no volume) |
| 17 | **Parcial** | Só `docker compose restart`; não reiniciei o Docker Desktop/daemon |
| 18 | OK | `reindex --all`: 11 sem mudanças, 4 falhas e 1 ignorado, 0,2 s |
| 19 | OK | Sem terminal (`-T`): recusa; com terminal: `n` não remove e `s` remove, e o arquivo no computador continua |
| 20 | OK | `pg_dump` (137 KB), apagar um documento, restaurar como `postgres` e a base volta; busca igual depois |
| 21 | **Pendente** | Precisa dos outros sistemas. Verificação parcial: o vetor da mesma frase no host (MPS) e no contêiner (CPU) tem cosseno 1,0000 |
| 22 | OK | Sem `POSTGRES_PASSWORD` ou `DOCS_DIR`, o Compose recusa com a mensagem em português |
| 23 | OK | `down -v` removeu os dois volumes; `up -d` e `init-db` voltaram com a base vazia |
| 24 | OK | `grande.pdf`: 36 páginas, 143 trechos, **132,9 s** em CPU no contêiner (inclui carregar o modelo) |
| 25 | **Pendente** | Windows |
| 26 | **Pendente** | Linux |

**Regressão da instalação local (seção 10), 2026-10-11:** venv novo com `pip install -r requirements.txt` (32 s, `pip check` sem conflitos, as 9 versões fixadas instaladas). Com ele: `check` com 0 falhas e 0 avisos contra a base local; imports de `src.cli`, `src.api`, `src.embeddings` e `src.loaders`; `search` e a API (`/health`, `/folders`) funcionando. Sem regressão.

Achados que mudaram a spec durante a execução: `docker/init-db.sh` no lugar do `setup_admin.sql` direto; healthcheck do banco com `-h 127.0.0.1`; `API_PORT=8000` fixo dentro do contêiner; `data/avaliacao/` na imagem; `CMD` no lugar de `ENTRYPOINT`; restauração como `postgres` sem `--no-owner`; cache do modelo de 4,3 GB (e não 2,3 GB).

Versão do pgvector na imagem: 0.8.7 (PostgreSQL 18.6). Porta 8000 do computador estava ocupada pela API local, usada `API_PORT=8001`.

| Data | Quem executou | Sistema / arquitetura / versões do Docker e do Compose | Resultado | Observações (tempo de `grande.pdf`, versão do pgvector na imagem, falhas) |
|---|---|---|---|---|
| 2026-10-11 | Claude Code (a pedido do usuário) | macOS Apple Silicon (arm64), Docker 29.8.2, Compose 5.5.1 | Aprovado, exceto os passos 6, 17 (parcial), 21, 25 e 26, que dependiam de outros sistemas | `grande.pdf` em 132,9 s; pgvector 0.8.7 |
| 2026-10-11 | Usuário (informado em conversa) | Windows 11 (WSL 2), Ubuntu LTS (amd64) e demais passos pendentes (6, 17, 21, 25, 26) | **Aprovado: o usuário informou que todos os testes passaram** | Versões do Docker/Compose, tempos de `grande.pdf` nesses sistemas e eventuais observações **não foram enviadas**; registrar aqui se houver |
