# F14 — API REST para execução dos fluxos do RAG

| Campo | Valor |
|---|---|
| **Status da spec** | Aprovada (2026-10-10) |
| **Status da implementação** | Pendente |
| **Marco** | M5 (ver ROADMAP) |
| **Depende de** | F05, F06, F07, F08, F09, F11 (e F01 para `init-db` e `check`) |
| **Regras de negócio** | R1–R11 (todas valem pela API, sem mudança) |
| **Seções da arquitetura** | §8 CLI, §8.1 API REST (nova), §9 Configuração |

## 1. Objetivo
Permitir que outros sistemas e pessoas executem, por HTTP, as mesmas funcionalidades que hoje só existem na CLI (cadastrar, reindexar, buscar, perguntar, listar, remover, avaliar e verificar o ambiente), sem usar o terminal.

## 2. Escopo

**Inclui**
- Um endpoint para cada comando da CLI: `init-db`, `check`, `ingest`, `reindex`, `search`, `ask`, `folders`, `list`, `delete` e `eval`, mais `GET /health` e o acompanhamento de tarefas (`/jobs/{id}`).
- Contrato de request, response e erros em JSON, em português nas mensagens.
- Operações longas (`ingest`, `reindex`, `eval`) como tarefas assíncronas.
- Confirmação explícita (`confirm`) no lugar dos `[s/N]` interativos (R10).
- Ponto de encaixe para a autenticação futura (seção 11).

**Não inclui** (fica para outra feature ou fora de escopo)
- **Autenticação e controle de acesso** (por pessoa, grupo ou documento): evolução futura, ver seção 11. Por enquanto, qualquer pessoa que alcance a API pode usar todos os endpoints.
- Interface web.
- Envio (upload) de arquivos pela API: o `ingest` recebe caminhos do disco do servidor, **sem restrição de pastas**, como a CLI (decisão 1, seção 11).
- Streaming de resposta do Claude, histórico de conversa e o menu interativo (é interface de terminal; o modo conversa equivale a chamar `/ask` várias vezes, cada pergunta independente, NEGOCIO §8).
- Nova regra de negócio: a API só chama os serviços que a CLI já usa.

## 3. Regras de negócio aplicáveis

| Regra | O que significa nesta feature |
|---|---|
| R1–R3 | `/ask` responde só com os trechos recuperados, cita fontes e devolve a frase padrão quando não houver informação (sem chamar o Claude se a busca vier vazia ou abaixo do limiar). |
| R4, R9 | `/ingest` ignora duplicados (mesmo `sha256`) e grava cada documento de forma atômica. |
| R5, R6 | `/reindex` e `/ingest` de pasta só processam o que mudou. Um arquivo ausente só sai da base com `prune` **e** `confirm_prune`. |
| R7, R8 | Falhas de arquivo não interrompem o lote; entram no resultado da tarefa com o motivo. |
| R10 | `DELETE` exige `confirm=true`; sem ele, nada é removido e a prévia é devolvida. |
| R11 | Continua valendo: os trechos usados em `/ask` vão ao Claude. |

## 4. Comportamento esperado

### 4.1 Convenções
- Prefixo `/api/v1`, corpo e respostas em JSON (UTF-8). Documentação interativa em `/docs`.
- Campos em `snake_case`. Datas em ISO 8601. Tempos (`elapsed`) em segundos.
- Os nomes dos campos acompanham os dados dos serviços existentes (`SearchOutcome`, `AskOutcome`, `FolderResult`, `FileResult`, `DeleteResult`).
- **Erro padrão** (qualquer status 4xx/5xx):
  ```json
  {"error": {"code": "folder_locked", "message": "Pasta em atualização por outra execução.", "details": {}}}
  ```
- **Tarefas** (`ingest`, `reindex`, `eval`): o `POST` responde `202` com o `job_id`; o resultado sai em `GET /jobs/{job_id}`.
  Estados: `queued` → `running` → `done` | `failed`.

### 4.2 Endpoints

#### `GET /api/v1/health` — o serviço está no ar (sem tocar no banco)
Response `200`:
```json
{"status": "ok"}
```

#### `GET /api/v1/check` — equivale a `check` (F01, F04, F07)
Response `200` (`ok` é `false` se algum item for `fail`; avisos não reprovam):
```json
{
  "ok": true,
  "checks": [
    {"name": "database", "status": "ok", "detail": "PostgreSQL 18.6, extensão vector 0.8.7"},
    {"name": "embedding_model", "status": "ok", "detail": "BAAI/bge-m3 (1024)"},
    {"name": "anthropic", "status": "warn", "detail": "HF_TOKEN ausente (opcional)"}
  ]
}
```
Com falha, o mesmo corpo sai com `ok: false` e status `503`.

#### `POST /api/v1/db/init` — equivale a `init-db` (F01)
Request: sem corpo.
Response `200`:
```json
{"status": "ok", "migrations": ["001_init.sql", "002_file_type_md.sql", "003_busca_textual.sql"]}
```

#### `POST /api/v1/ingest` — equivale a `ingest <arquivo|pasta>` (F05, F08, F13)
Request:
```json
{
  "path": "/dados/documentos/rh",
  "recursive": true,
  "force": false,
  "prune": false,
  "confirm_prune": false
}
```
`recursive` é opcional (se omitido, usa o guardado na pasta ou `true` na primeira vez; só vale para pastas). `path` pode ser um arquivo (`.txt`, `.md`, `.pdf`) ou uma pasta.
Response `202`:
```json
{"job_id": "5f0c2a9e", "status": "queued", "href": "/api/v1/jobs/5f0c2a9e"}
```
Resultado da tarefa (`GET /jobs/5f0c2a9e`, pasta, estado `done`):
```json
{
  "job_id": "5f0c2a9e",
  "kind": "ingest",
  "status": "done",
  "created_at": "2026-10-10T09:00:00",
  "finished_at": "2026-10-10T09:00:35",
  "result": {
    "folder": "/dados/documentos/rh",
    "registered_now": true,
    "recursive": true,
    "files": [
      {"path": "manual.pdf", "outcome": "created", "chunk_count": 143, "detail": ""},
      {"path": "copia.pdf", "outcome": "duplicate", "chunk_count": 0, "detail": "cópia de manual.pdf"},
      {"path": "escaneado.pdf", "outcome": "failed", "chunk_count": 0, "detail": "PDF sem texto selecionável"}
    ],
    "ignored": [{"path": "foto.png", "outcome": "ignored", "detail": "formato não aceito"}],
    "out_of_scope": 0,
    "prune_status": null,
    "elapsed": 35.1
  }
}
```
`outcome`: `created`, `updated`, `unchanged`, `adopted`, `duplicate`, `failed`, `absent`, `removed`, `ignored`. `prune_status`: `null`, `removed`, `declined` (sem `confirm_prune`) ou `cancelled`.
Para um **arquivo**, `result` traz `outcome`, `path`, `document_id`, `chunk_count`, `duplicate_of`, `replaced_previous` e `elapsed`.
A tarefa fica `done` mesmo com arquivos `failed` (como o resumo da CLI); `failed` só indica erro da tarefa inteira (ver 4.3).

#### `POST /api/v1/reindex` — equivale a `reindex <pasta>|--all` (F08)
Request (uma pasta):
```json
{"path": "/dados/documentos/rh", "prune": false, "confirm_prune": false}
```
Request (todas):
```json
{"all": true, "prune": false, "confirm_prune": false}
```
Exige `path` **ou** `all: true` (não os dois). Response `202`: igual ao `ingest`. O resultado da tarefa é `{"folders": [<mesmo objeto do ingest de pasta>, …]}`.

#### `GET /api/v1/jobs/{job_id}` — acompanha uma tarefa
Response `200`: o objeto da tarefa (exemplo acima). Em execução:
```json
{"job_id": "5f0c2a9e", "kind": "ingest", "status": "running", "created_at": "2026-10-10T09:00:00", "progress": {"current": 4, "total": 12, "item": "manual.pdf"}}
```
Falha da tarefa inteira:
```json
{"job_id": "5f0c2a9e", "kind": "reindex", "status": "failed", "error": {"code": "embedding_model_mismatch", "message": "…"}}
```
`404` se o `job_id` não existir.

#### `POST /api/v1/search` — equivale a `search` (F06)
Request:
```json
{"question": "Como funciona o trabalho remoto?", "method": "rrf", "top_k": 5, "fetch_k": 20, "folder": null}
```
`method`: `rrf` (padrão), `semantic` ou `lexical`. `top_k` e `fetch_k` ≥ 1. `folder` opcional limita a busca a documentos dentro da pasta.
Response `200`:
```json
{
  "status": "ok",
  "method": "rrf",
  "top_k": 5,
  "fetch_k": 20,
  "folder": null,
  "hits": [
    {
      "document": "manual_colaborador.txt",
      "path": "/dados/documentos/rh/manual_colaborador.txt",
      "page": 3,
      "section": "Trabalho remoto",
      "text": "O colaborador pode trabalhar de casa até 3 dias por semana…",
      "scores": {"rrf": 0.0328, "semantic": 0.56, "lexical": 0.41}
    }
  ],
  "elapsed": 0.4
}
```
`status`: `ok`, `empty_base` (base sem documentos) ou `no_documents_in_folder`; nesses dois últimos `hits` é `[]` e o status HTTP continua `200`. Os campos exatos de `scores` seguem o `SearchHit` (a conferir na implementação).

#### `POST /api/v1/ask` — equivale a `ask` (F07, F11)
Request: igual ao `/search` (sem `fetch_k` obrigatório).
Response `200`, com resposta:
```json
{
  "status": "ok",
  "answer": "O colaborador pode trabalhar de casa até 3 dias por semana [1].",
  "sources": [
    {"n": 1, "document": "manual_colaborador.txt", "page": 3, "section": "Trabalho remoto"}
  ],
  "truncated": false,
  "cited_none": false,
  "search": {"method": "rrf", "top_k": 5, "hits": 5},
  "elapsed": {"search": 0.4, "answer": 2.1}
}
```
Sem informação (busca vazia, abaixo do limiar `RELEVANCE_THRESHOLD`, ou o Claude não encontrou): `answer` traz a frase padrão da F07, `sources` é `[]`, `status` é `ok`. Se a busca parou antes (base vazia ou pasta sem documentos), `answer` é `null` e `status` é `empty_base` ou `no_documents_in_folder`. O Claude só é chamado quando há trechos acima do limiar. `truncated: true` indica resposta cortada por `max_tokens`.

#### `GET /api/v1/folders` — equivale a `folders` (F09)
Response `200`:
```json
{"folders": [{"path": "/dados/documentos/rh", "recursive": true, "documents": 14, "last_indexed_at": "2026-10-10T09:00:35"}]}
```

#### `GET /api/v1/documents?folder=<pasta>` — equivale a `list [--folder]` (F09)
`folder` é opcional. Response `200`:
```json
{
  "folder": "/dados/documentos/rh",
  "documents": [
    {"id": 1, "path": "/dados/documentos/rh/manual.pdf", "file_type": "pdf", "status": "indexed", "chunks": 143}
  ]
}
```

#### `DELETE /api/v1/documents?path=<arquivo>&confirm=true` — equivale a `delete <arquivo>` (F09, R10)
#### `DELETE /api/v1/folders?path=<pasta>&confirm=true` — equivale a `delete <pasta registrada>` (F09, R10)
Sem `confirm=true`, nada é removido e a resposta é `409` com a prévia:
```json
{"error": {"code": "confirmation_required", "message": "Confirme a remoção com confirm=true.", "details": {"kind": "folder", "target": "/dados/documentos/rh", "documents": 14, "chunks": 1820, "paths": ["…"]}}}
```
Com `confirm=true`, `200`:
```json
{"status": "removed", "kind": "folder", "target": "/dados/documentos/rh", "documents": 14, "chunks": 1820, "paths": ["…"]}
```
`404` se o alvo não existir na base. A remoção de pasta também respeita a trava por pasta (`409 folder_locked`).

#### `POST /api/v1/evaluations` — equivale a `eval` (F11)
Request (todos os campos opcionais, com os mesmos padrões da CLI):
```json
{
  "questions_file": "data/avaliacao/perguntas.json",
  "strategies": ["structured", "recursive", "sentence", "fixed"],
  "max_chars": [500, 900, 1400],
  "methods": ["rrf", "semantic", "lexical"],
  "top_k": 5,
  "answers": false
}
```
`answers: true` chama o Claude de verdade (consome cota). Response `202`: igual ao `ingest`. Resultado da tarefa:
```json
{
  "kind": "evaluation",
  "status": "done",
  "result": {
    "questions": 24,
    "rows": [
      {"strategy": "structured", "max_chars": 900, "method": "rrf", "hit_at_1": 0.94, "hit_at_k": 0.94, "mrr": 0.94, "chunks": 46}
    ],
    "threshold": {"proposed": 0.55, "current": 0.50},
    "answers": null
  }
}
```
Os nomes de `rows` e `threshold` seguem o relatório de `src/evaluation_service.py` (a conferir na implementação). A avaliação usa tabelas temporárias e não toca nos dados reais.

### 4.3 Erros e códigos HTTP

| Situação | HTTP | `error.code` |
|---|---|---|
| Parâmetro inválido (método, `top_k` < 1, `path` e `all` juntos) | 400 | `invalid_parameter` |
| Corpo fora do esquema (tipo errado, campo obrigatório ausente) | 422 | `validation_error` |
| Pasta, documento ou tarefa inexistente | 404 | `not_found` |
| Caminho de `ingest`/`reindex` inexistente no servidor | 404 | `not_found` |
| Pasta em atualização por outra execução (trava da F08) | 409 | `folder_locked` |
| `EMBEDDING_MODEL` diferente do registrado (F04) | 409 | `embedding_model_mismatch` |
| `DELETE` sem `confirm=true` | 409 | `confirmation_required` |
| Arquivo com formato não aceito ou PDF sem texto (arquivo avulso) | 422 | `unsupported_file` |
| Claude indisponível, chave ou modelo inválidos | 502 | `llm_unavailable` |
| Banco indisponível ou esquema ausente | 503 | `database_unavailable` |
| Erro inesperado | 500 | `internal_error` (sem traceback no corpo) |

Falhas de arquivos dentro de um lote **não** geram erro HTTP: aparecem em `files[].outcome = "failed"` (R7).

### 4.4 Execução
- Subir: `python -m src.api` (Uvicorn; `API_HOST` padrão `127.0.0.1`, `API_PORT` padrão `8000`).
- **Sem autenticação e sem restrição de caminhos nesta fase:** quem alcança a API lê qualquer pasta do servidor (TXT, MD e PDF) e remove documentos. Por isso o padrão escuta só em `127.0.0.1`. Abrir para a rede (`API_HOST=0.0.0.0`) é decisão consciente de quem sobe a API e deve vir acompanhada da seção 11.
- **CORS desligado:** nenhuma página web de outro endereço chama a API pelo navegador.
- O modelo de embeddings é carregado **uma vez** (reaproveitando `EmbedderCache`, `src/search_service.py`) na primeira chamada que precisa dele, e fica em memória.
- `ingest`, `reindex` e `eval` rodam em **fila de um único trabalhador** (uma tarefa por vez; as demais ficam `queued`), para não competir pelo modelo de embeddings nem pela GPU. A trava por pasta da F08 continua valendo. `search`, `ask` e as listagens respondem na hora, fora da fila. As tarefas ficam **em memória** e somem ao reiniciar a API (o cadastro é atômico, então nada fica pela metade; basta repetir).

## 5. Interface

**Mapa CLI → API**

| Comando da CLI | Endpoint | Tipo |
|---|---|---|
| `init-db` | `POST /api/v1/db/init` | síncrono |
| `check` | `GET /api/v1/check` | síncrono |
| — | `GET /api/v1/health` | síncrono |
| `ingest <arquivo\|pasta> [--recursive/--no-recursive] [--force] [--prune]` | `POST /api/v1/ingest` | tarefa (202) |
| `reindex <pasta>\|--all [--prune]` | `POST /api/v1/reindex` | tarefa (202) |
| — | `GET /api/v1/jobs/{job_id}` | síncrono |
| `search "<pergunta>" [--method] [--top-k] [--fetch-k] [--folder] [--full]` | `POST /api/v1/search` | síncrono (`--full`: o corpo sempre traz o trecho inteiro) |
| `ask "<pergunta>" [--method] [--top-k] [--fetch-k] [--folder]` | `POST /api/v1/ask` | síncrono |
| `folders` | `GET /api/v1/folders` | síncrono |
| `list [--folder]` | `GET /api/v1/documents` | síncrono |
| `delete <arquivo>` | `DELETE /api/v1/documents` | síncrono |
| `delete <pasta>` | `DELETE /api/v1/folders` | síncrono |
| `eval [...]` | `POST /api/v1/evaluations` | tarefa (202) |
| menu (sem argumentos) | — (sem endpoint) | — |

**Módulos e funções** (proposta; a assinatura final sai na implementação)

| Arquivo | Responsabilidade | Funções / classes |
|---|---|---|
| `src/api/__init__.py`, `src/api/__main__.py` | Criar a aplicação e subir o Uvicorn (`python -m src.api`). | `create_app()` |
| `src/api/schemas.py` | Modelos de request e response (Pydantic). | `SearchRequest`, `AskRequest`, `IngestRequest`, `ReindexRequest`, `EvaluationRequest`, `ErrorBody` |
| `src/api/routes.py` | Um único `APIRouter` com todas as rotas (ponto de encaixe da autenticação futura). | funções de rota finas que chamam os serviços |
| `src/api/jobs.py` | Fila e registro das tarefas. | `JobStore`, `submit()`, `get()` |
| `src/api/errors.py` | Converter `SearchError`, `AskError`, `FolderError`, `ManagementError`, `IngestError` em respostas de erro. | `register_handlers(app)` |

Serviços reaproveitados, sem mudança de regra: `search_service.run_search`, `answer_service.run_ask`, `folder_ingestion.ingest_folder` e `reindex_folders`, `ingestion.process_file`, `management_service.list_folders`, `list_documents` e `delete_target`, `evaluation_service` e os testes do `check` da CLI. Se algum deles escreve na tela ou pede `input()` (por exemplo, `Reporter` e `Confirm`), a API passa um `Reporter` que alimenta `progress` e um `Confirm` que devolve o valor de `confirm`/`confirm_prune`.

## 6. Dados
Sem mudanças no esquema (as tarefas ficam em memória; ver pontos em aberto).

## 7. Configuração

| Parâmetro | Padrão | Onde se define |
|---|---|---|
| `API_HOST` | `127.0.0.1` | `.env` |
| `API_PORT` | `8000` | `.env` |

## 8. Dependências externas
- `fastapi` e `uvicorn` em `requirements.txt` (decisão 3; o `pydantic` vem junto).
- Nenhum serviço novo; usa o mesmo banco, o mesmo modelo de embeddings e o mesmo Claude da CLI.

## 9. Critérios de aceite — roteiro de teste manual
Não há testes automatizados (ARQUITETURA §14). Este roteiro é o teste.

**Pré-condições:**
- `python -m src.cli check` ok; banco com os dados de `data/` e `data/amostras/`.
- API no ar: `python -m src.api`; variável `B=http://127.0.0.1:8000/api/v1`; sem configuração de pastas (sem restrição de caminhos).

| # | Passo | Comando / ação | Resultado esperado |
|---|---|---|---|
| 1 | Saúde | `curl $B/health` | `200` `{"status":"ok"}` |
| 2 | Check | `curl $B/check` | `200`, `ok: true`, mesmos itens do `python -m src.cli check` |
| 3 | init-db idempotente | `curl -X POST $B/db/init` | `200`, lista as 3 migrações; repetir não falha |
| 4 | Cadastrar arquivo | `curl -X POST $B/ingest -H 'Content-Type: application/json' -d '{"path":".../manual_colaborador.txt"}'` | `202` com `job_id`; `GET /jobs/{id}` chega a `done` com `outcome` `created` ou `unchanged` |
| 5 | Cadastrar pasta | `POST /ingest` com a pasta `data/amostras` | `done`; `files` e `ignored` coerentes com o resumo da CLI; falhas aparecem como `failed` com motivo, sem derrubar o lote (R7) |
| 6 | Duplicado | `POST /ingest` com cópia de um arquivo já cadastrado | `outcome: duplicate` com a origem em `detail` (R4) |
| 7 | PDF sem texto | `POST /ingest` no PDF sem texto | `422 unsupported_file` (arquivo avulso) ou `failed` dentro de pasta (R8) |
| 8 | Reindex | `POST /reindex` `{"path":"…"}` e `{"all":true}` | `done`; sem mudanças: tudo `unchanged` e rápido (R5) |
| 9 | Ausente sem prune | apagar um arquivo da pasta e repetir o reindex | `absent`, continua na base (R6) |
| 10 | Prune sem confirmação | `{"prune":true}` sem `confirm_prune` | `prune_status: declined`, nada removido (R10) |
| 11 | Prune confirmado | `{"prune":true,"confirm_prune":true}` | `removed`, `GET /documents` sem o arquivo |
| 12 | Caminho inexistente | `POST /ingest` `{"path":"/nao/existe"}` | `404 not_found`; nada registrado em `folders` |
| 13 | Fila de uma tarefa por vez | duas `POST /reindex` seguidas (pastas diferentes) | a primeira fica `running` e a segunda `queued`; depois as duas ficam `done` |
| 14 | Busca | `POST /search` `{"question":"trabalho remoto"}` | `hits` com documento, página, seção e pontuações |
| 15 | Busca por método e pasta | `method: lexical`, `semantic`; `folder` | resultados compatíveis com `python -m src.cli search` |
| 16 | Busca inválida | `{"question":"x","method":"abc"}` e `top_k: 0` | `422`/`400` com `error.code` |
| 17 | Pergunta | `POST /ask` `{"question":"Como funciona o trabalho remoto?"}` | `answer` com `[1]` e `sources` com documento e página (R1, R2) |
| 18 | Sem resposta | `POST /ask` sobre assunto fora da base | frase padrão, `sources: []` (R3) |
| 19 | Sem chamar o Claude | `ask` fora do assunto com chave inválida | frase padrão, sem `502` (limiar da F11) |
| 20 | Chave inválida | `ask` sobre assunto da base com chave inválida | `502 llm_unavailable` |
| 21 | Pastas e documentos | `GET /folders` e `GET /documents?folder=…` | iguais a `folders` e `list` |
| 22 | Delete sem confirmação | `DELETE /documents?path=…` | `409 confirmation_required` com prévia; nada removido (R10) |
| 23 | Delete confirmado | `DELETE /documents?path=…&confirm=true` | `200 removed`; some de `GET /documents` |
| 24 | Delete de pasta | `DELETE /folders?path=…&confirm=true` | `200 removed` com contagens |
| 25 | Alvo inexistente | `DELETE /documents?path=/nao/existe&confirm=true` | `404 not_found` |
| 26 | Avaliação | `POST /evaluations` com `strategies:["structured"]`, `max_chars:[900]`, `methods:["rrf"]` | `done`; métricas iguais às do `python -m src.cli eval` (hit@1 0,94 para `rrf`) |
| 27 | Tarefa inexistente e reinício | `GET /jobs/xyz`; reiniciar a API e consultar um `job_id` antigo | `404 not_found` nos dois casos (tarefas em memória) |
| 28 | Modelo divergente | trocar `EMBEDDING_MODEL` no `.env`, subir a API, `POST /ingest` | tarefa `failed`/`409 embedding_model_mismatch`, nada gravado |
| 29 | Banco fora | parar o PostgreSQL e chamar `/search` | `503 database_unavailable`, sem traceback |
| 30 | Escuta local e CORS | `lsof -i :8000`; `curl -H 'Origin: http://outro.exemplo' -i $B/health` | escuta só em `127.0.0.1`; resposta sem cabeçalhos `Access-Control-Allow-*` |
| 31 | Paridade com a CLI | repetir os passos 14, 17 e 21 pela CLI | mesmos documentos, páginas e fontes |

## 10. Impacto em outras features

| Feature | Roteiros a repetir (#) | Motivo |
|---|---|---|
| F05, F08 | cadastro de arquivo, pasta, `--prune`, trava | a API chama o mesmo código; qualquer ajuste de `Reporter` ou `Confirm` pode afetar a CLI |
| F06, F07 | busca e pergunta | idem para `run_search`/`run_ask` |
| F09 | `folders`, `list`, `delete` | idem |
| F10 | menu e modo conversa | o menu usa os mesmos serviços |
| F11 | `eval` | a avaliação roda dentro da API |
| F01 | `check`, `init-db` | reaproveitados pela API |

## 11. Riscos e decisões
**Decisões tomadas** (com o motivo)
- **A API é uma camada fina sobre os serviços existentes**: sem regra nova, para a CLI e a API não divergirem.
- **Sem autenticação nesta fase** (decisão do usuário). A API nasce com um único `APIRouter` para a dependência de autenticação e autorização entrar em um só lugar depois, e o padrão é escutar só em `127.0.0.1`.
- **`confirm`/`confirm_prune` no lugar do `[s/N]`**: preserva a R10 sem terminal.
- **Operações longas viram tarefas** (`202` + `/jobs/{id}`): um cadastro de PDF grande leva dezenas de segundos.

**Evoluções futuras (registradas, não implementadas)**
- **Autenticação** da API (token, chave de API ou SSO) e **controle de acesso por pessoa, grupo ou documento**: junto do item "Controle de acesso" do NEGOCIO §9.
  - Autorização aplicada no filtro de `search`, `ask`, `documents` e `delete` (resultados e remoções só do que a pessoa pode ver).
  - Dono ou lista de acesso (ACL) em `documents`, com migração própria.
  - Limite de taxa e registro de auditoria.
  - Restringir as pastas que a API pode ler (lista de pastas permitidas, por exemplo `INGEST_ROOTS`) e avaliar o upload de arquivos nesse momento.
- Upload de arquivos (`multipart/form-data`), interface web e `psycopg_pool` (adiado desde a F05).

**Decisões do usuário nos pontos que estavam em aberto** (2026-10-10)
1. **Caminhos no servidor: sem restrição**, como a CLI. Risco aceito: sem autenticação, quem alcança a API lê qualquer pasta do servidor. Mitigação: escuta só em `127.0.0.1` por padrão. A lista de pastas permitidas fica como evolução futura.
2. **Tarefas em memória**, sem tabela nova.
3. **FastAPI + Uvicorn.**
4. **Fila de um único trabalhador** (uma tarefa por vez).
5. **`DELETE` pelo caminho** (`?path=`), como a CLI.
6. **Prefixo `/api/v1`** e **CORS desligado**.

**Pontos em aberto** (precisam de resposta antes de implementar)
- Nenhum de desenho. Ficam só os nomes exatos de campos de `scores` (busca) e de `rows`/`threshold` (avaliação), a conferir nos serviços durante a implementação.

## 12. Documentação a atualizar
- `.spec/ROADMAP.md`: linha F14, marco M5 e status.
- `.spec/ARQUITETURA.md`: §8.1 API REST, §9 (variáveis e dependências), §10 (`src/api/`).
- `.spec/NEGOCIO.md`: §9 (API planejada) e §10.
- `.claude/CLAUDE.md`: estado do projeto.
- `README.md` e `.env.example` (`API_HOST`, `API_PORT`): só após a implementação.
- `requirements.txt`: `fastapi` e `uvicorn`.

## 13. Definição de pronto
- [x] Spec aprovada pela pessoa responsável (2026-10-10)
- [ ] Código implementado somente no que a spec descreve
- [ ] Todos os passos do roteiro (seção 9) executados e aprovados
- [ ] Roteiros de regressão (seção 10) repetidos
- [ ] Documentação da seção 12 atualizada
- [ ] Status atualizado nesta spec e no ROADMAP

## 14. Registro de verificação

| Data | Quem executou | Resultado | Observações / falhas encontradas |
|---|---|---|---|
| | | | |
