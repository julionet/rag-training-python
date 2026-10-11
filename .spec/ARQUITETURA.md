# ARQUITETURA — Evolução da aplicação RAG (TXT + MD + PDF, PostgreSQL/pgvector)

Status: **implementada e verificada (F01–F14, marcos M1 a M5).** Este documento descreve a arquitetura adotada; trechos marcados com "F12" ou "removido" registram o que existia antes.
Visão de uso e instalação: [README.md](../README.md).

## 1. Objetivos e restrições

- Aceitar **apenas** arquivos `.txt`, `.md` e `.pdf` (PDF só com texto selecionável, **sem OCR**).
- Usar **PostgreSQL** como banco vetorial (extensão **pgvector**).
- Manter o **SentenceTransformer** (`BAAI/bge-m3`) como modelo de embeddings, com melhorias.
- Revisar o chunking e adotar uma estratégia mais eficiente como padrão.
- Interface **somente CLI**, unificada.
- Manter a finalidade de estudo: os conceitos (chunking, busca semântica, lexical, híbrida) continuam visíveis e comparáveis.
- Suportar **várias pastas** de documentos, indexadas uma a uma, com **todas consultadas juntas** (com filtro opcional por pasta).
- **Reindexação incremental** por pasta: só processa arquivos novos ou alterados.
- Suportar **arquivos grandes** (PDFs de centenas de páginas) sem estourar memória (seção 6.1).
- Menu interativo na CLI além dos comandos diretos.

## 2. Decisão: evoluir ou refazer?

**Evoluir.** A divisão em camadas (`chunking`, `embeddings`, `generation`, `fusion`) está boa, e o prompt de geração é sólido (só contexto, citações, defesa contra injection). O que muda de verdade é armazenamento e entrada:

| Antes (removido na F12) | Evolução (implementada) |
|---|---|
| `vector_store.py` (numpy + JSON) | Repositório Postgres + pgvector |
| `lexical_search.py` (BM25 em memória) | Busca textual do Postgres (`tsvector`, config `portuguese`) |
| Leitura de TXT dentro dos pipelines | Módulo `loaders` (TXT, MD e PDF) |
| `rag.py` + `hybrid_rag.py` | Um único pipeline |
| Scripts soltos | CLI unificada |

## 3. Embeddings — manter SentenceTransformer + `BAAI/bge-m3`

O modelo é adequado: multilíngue (bom em português), 1024 dimensões, contexto de até 8192 tokens, e gera vetores normalizados (cosseno = produto escalar). Não há motivo para trocar. Melhorias:

- `Embedder` com `device` automático (MPS no Mac, senão CPU), `batch_size` configurável e `max_seq_length` explícito.
- Carregar o modelo **uma vez** por processo.
- Gravar nome e dimensão do modelo em `app_meta` na **primeira** vetorização, sem nunca sobrescrever. Se `EMBEDDING_MODEL` mudar, a vetorização é **bloqueada** com a orientação de **reindexar** (vetores de modelos diferentes não são comparáveis); a checagem do nome ocorre antes de carregar o modelo (F04).
- `embed_chunks(embedder, chunks)` vetoriza `Chunk.embedding_text` em fluxo e lotes (padrão 64). Trecho acima de `max_seq_length` (8192 tokens) gera **aviso**, sem bloquear (F04).
- **Troca de modelo:** hoje só é possível bloqueando e reindexando manualmente; a troca planejada está em §16 (F16).
- Observação: o bge-m3 também tem modos esparso e multi-vetor, mas isso exige outra biblioteca (FlagEmbedding). Fica **fora do escopo**; a parte lexical é coberta pelo Postgres.

## 4. Ingestão de arquivos

Novo módulo `src/loaders.py` com `inspect_document(path) -> DocumentInfo` (valida o arquivo, calcula o `sha256` e conta as páginas), `iter_pages(path)` (entrega uma `Page` por vez, para PDFs grandes) e `load_document(path) -> Document` (tudo em memória, para arquivos pequenos):

- `Document`: `filename`, `file_type`, `sha256`, `pages: list[Page]` (`Page`: `number`, `text`). `DocumentInfo`: `filename`, `file_type`, `sha256`, `page_count`.
- **TXT e MD**: leitura em UTF-8, com fallback para `utf-8-sig`/`latin-1`. Todo o texto vira a página 1. O `.md` tem tipo próprio (`md`) e segue o mesmo caminho do TXT; os títulos `#` viram a seção dos trechos (F13).
- **PDF**: `pymupdf4llm` (PyMuPDF) converte cada página em **Markdown**, preservando títulos e tabelas. O número da página fica como metadado.
- PDF sem texto extraível (provável escaneado): erro claro, sem indexar.
- Qualquer outra extensão: rejeitada com mensagem explícita.
- **Reindexação incremental** (identidade = caminho do arquivo, mudança = `sha256`):
  - arquivo novo → indexa;
  - mesmo caminho e mesmo hash → ignora (idempotente);
  - mesmo caminho e hash diferente → apaga os chunks antigos e reindexa, tudo em uma transação;
  - **conteúdo duplicado** (mesmo `sha256` de um documento já indexado em outro caminho, mesma pasta ou outra) → **ignorado**, sem gerar chunks. O resumo da ingestão informa "duplicado de `<caminho do original>`". O índice único em `sha256` garante isso também no banco;
  - se um arquivo existente for editado e o novo conteúdo for idêntico ao de outro documento, os chunks antigos são removidos e o arquivo é reportado como duplicado;
  - se o original sair do banco (`--prune` ou `delete`), um duplicado antes ignorado passa a ser indexado na próxima ingestão ou reindexação (cobre o caso de arquivo movido de pasta);
  - arquivo sumiu da pasta → removido do banco só com `--prune` (nunca por padrão), **depois de listar e pedir confirmação** `[s/N]`, apenas em terminal interativo (F08);
  - `--force` reindexa tudo.
- **Várias pastas:** cada pasta indexada é registrada em `sources`. Pode-se indexar uma a uma, em vezes diferentes. A busca (`ask`) usa **todos** os documentos de todas as pastas por padrão, com filtro opcional `--folder <pasta>`.
- **F08 (implementado):** a pasta é registrada em `sources` (caminho resolvido; pastas não se sobrepõem). Uma **trava por pasta** (lock consultivo do PostgreSQL) recusa uma segunda atualização da mesma pasta. A varredura ignora e lista arquivos ocultos (`.nome`) e links simbólicos, além de formatos não aceitos. Um arquivo alterado que passa a ser idêntico a outro documento é reportado como duplicado e a versão anterior é removida. Arquivo avulso encontrado na pasta, com mesmo caminho e conteúdo, é vinculado à pasta sem revetorizar. Em pasta não recursiva, documentos já cadastrados em subpastas ficam na base, sem atualização, com aviso no resumo.
- Extensões são casadas sem diferenciar maiúsculas (`.PDF`); arquivos de outros formatos na pasta são listados como ignorados.

## 5. Chunking

**Manter** as 4 estratégias atuais (`fixed`, `sentence`, `recursive`, `semantic`) como material de estudo e comparação, com estas correções:

- `recursive_chunks`: não perder pontuação ao dividir por `". "`.
- `split_sentences`: tratar abreviações comuns e números (ex.: "Sr.", "R$ 1.000,00").
- `semantic_chunks`: impor `min_chars` e `max_chars`.

**Novo padrão proposto: chunking estruturado por Markdown (`structured_chunks`).**

1. Divide o documento por títulos (`#`, `##`, `###`), mantendo a hierarquia.
2. Dentro de cada seção, divide por parágrafo, depois por sentença e só por último por tamanho (a lógica recursiva atual).
3. Cada chunk guarda o **caminho do título** (ex.: `Manual do Colaborador > Férias`). Esse caminho entra como prefixo do texto usado no embedding e na busca textual, mas o conteúdo exibido ao usuário continua limpo.
4. Tamanho alvo ~800–1000 caracteres (~200–250 tokens), overlap ~10–15%, com o limite validado em tokens pelo tokenizer do bge-m3.
5. Tabelas de PDF não são partidas no meio de uma linha.
6. Metadados por chunk: `source`, `page`, `section`, `chunk_index`.
7. Tipo `Chunk(chunk_index, page, section, content)` com `embedding_text` (seção + conteúdo); entrada única `chunk_pages(pages, strategy, ...)`. Um trecho **nunca cruza a fronteira de página**; a seção continua valendo nas páginas seguintes (ver F03).

**Por quê:** PDFs e TXT com títulos perdem contexto quando o chunk não diz a que seção pertence ("o limite é R$ 120" sem saber que é refeição). O prefixo de seção melhora a recuperação, e a divisão por estrutura evita cortes no meio de ideias.

**Não vamos presumir que é melhor: vamos medir.** O comando `eval` (F11) usa um conjunto de perguntas com o trecho esperado e compara as estratégias por **hit rate@k** e **MRR**.

## 6. PostgreSQL + pgvector

### Esquema (`sql/001_init.sql`)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE sources (              -- pastas registradas para indexação
  id              BIGSERIAL PRIMARY KEY,
  path            TEXT NOT NULL UNIQUE,   -- caminho absoluto da pasta
  recursive       BOOLEAN NOT NULL DEFAULT true,
  last_indexed_at TIMESTAMPTZ
);

CREATE TABLE documents (
  id          BIGSERIAL PRIMARY KEY,
  source_id   BIGINT REFERENCES sources(id) ON DELETE CASCADE,  -- NULL = arquivo avulso
  source_path TEXT NOT NULL UNIQUE,   -- caminho absoluto do arquivo
  filename    TEXT NOT NULL,
  file_type   TEXT NOT NULL CHECK (file_type IN ('txt', 'md', 'pdf')),  -- 'md' entra pela migração 002 (F13)
  sha256      TEXT NOT NULL,          -- detecta arquivo alterado
  pages       INT  NOT NULL,
  status      TEXT NOT NULL DEFAULT 'indexed' CHECK (status IN ('indexing', 'indexed', 'failed')),
  error       TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX documents_sha256_uniq ON documents (sha256);  -- conteúdo duplicado é ignorado (seção 4)

CREATE TABLE chunks (
  id          BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index INT    NOT NULL,
  page        INT,
  section     TEXT,
  content     TEXT   NOT NULL,
  embedding   vector(1024) NOT NULL,
  tsv         tsvector GENERATED ALWAYS AS (to_tsvector('portuguese', content)) STORED,  -- F06: migração 003 passa a ser seção (peso C) + conteúdo (peso A)
  -- tsv_en    tsvector (inglês, mesma expressão) e índice chunks_tsv_en_gin: criados pela migração 003 (F06)
  UNIQUE (document_id, chunk_index)
);

CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_tsv_gin        ON chunks USING gin (tsv);

CREATE TABLE app_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL      -- embedding_model, embedding_dim
);
```

A dimensão `1024` é a do bge-m3. Trocar de modelo com outra dimensão exige nova migração.

### Busca híbrida dentro do Postgres

Duas consultas candidatas (`fetch_k`, padrão 10 a 20) combinadas por **RRF em SQL**:

```sql
WITH semantic AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> %(q)s) AS rank
  FROM chunks ORDER BY embedding <=> %(q)s LIMIT %(fetch_k)s
),
lexical AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY ts_rank_cd(tsv, query) DESC) AS rank
  FROM chunks, websearch_to_tsquery('portuguese', %(text)s) query
  WHERE tsv @@ query
  ORDER BY ts_rank_cd(tsv, query) DESC LIMIT %(fetch_k)s
)
SELECT c.*, COALESCE(1.0/(60+s.rank),0) + COALESCE(1.0/(60+l.rank),0) AS score
FROM chunks c
LEFT JOIN semantic s ON s.id = c.id
LEFT JOIN lexical  l ON l.id = c.id
WHERE s.id IS NOT NULL OR l.id IS NOT NULL
ORDER BY score DESC LIMIT %(top_k)s;
```

- Métodos expostos: `rrf` (padrão), `semantic`, `lexical`. O `weighted` pode permanecer como opção didática, calculado em Python.
- Isso resolve o tokenizer sem acentos: a config `portuguese` do Postgres cuida de acentos, stemming e stopwords.
- **F06 (implementado):** a busca textual usa duas colunas, `tsv` (português) e `tsv_en` (inglês), ambas sobre seção (peso `C`) + conteúdo (peso `A`). A pergunta vira uma lista de palavras sem as palavras vazias de **ambos** os idiomas, combinadas por **OU** (`to_tsquery`), e o rank textual é o maior `ts_rank_cd` entre os dois idiomas. O filtro de pasta é por prefixo do caminho do arquivo (`starts_with(source_path, pasta/)`). A busca fica em `src/retrieval.py` (`search`) e `src/search_service.py` (`run_search`).
- **Atenção a validar:** códigos como `E-5107` podem ser tokenizados de forma diferente pelo `to_tsvector`. Isso será verificado manualmente com o documento de exemplo. Se falhar, a alternativa é uma coluna adicional com `simple`.
- Busca vetorial inicialmente **exata** nas verificações com poucos documentos, com HNSW para volume maior (ajuste de `ef_search` se necessário).

### 6.1 Arquivos grandes

Estimativa de ordem de grandeza (a medir na fase 1/3): um PDF de 500 páginas gera cerca de 1.500 a 2.500 chunks. O gargalo é o **embedding no Mac**, não o Postgres: o bge-m3 é um modelo grande (~570M parâmetros) e a indexação desse PDF pode levar de alguns minutos a algumas dezenas de minutos, conforme o hardware. Medidas previstas:

- **Processamento em fluxo:** o PDF é lido página a página; o texto é dividido em chunks e processado em lotes (ex.: 64 chunks por lote), sem manter o documento inteiro em memória.
- **Gravação por lote** (`COPY` ou `executemany`) em vez de um INSERT por chunk.
- **Barra de progresso** (páginas/chunks processados e tempo estimado).
- **Retomada:** `documents.status` (`indexing`/`indexed`/`failed`) permite detectar uma ingestão interrompida e refazê-la; o documento só passa a `indexed` quando termina, e nunca aparece parcial nas buscas (a busca filtra por `status = 'indexed'`).
- **Limites configuráveis:** tamanho máximo de arquivo e de páginas (padrão a definir) com mensagem clara ao exceder.
- **Falha isolada:** um arquivo corrompido não interrompe a indexação da pasta e aparece no resumo final com o motivo. **F08:** a falha **não** é gravada no banco (`failed`/`error` ficam sem uso): o arquivo é tentado de novo na próxima execução e, se já havia uma versão cadastrada, ela é mantida.
- Índice HNSW: a criação é incremental, e para cargas muito grandes é possível criá-lo depois da carga inicial.

### Camada de acesso

- `psycopg` 3 + `psycopg_pool` + `pgvector` (adaptador de vetor). SQL explícito, **sem ORM**.
- `src/db.py` (conexão, adaptador `pgvector` e migração) e `src/repository.py` (`find_by_sha256`, `find_by_path`, `add_document`; depois `search`, `list_documents`, `delete_document`). `src/ingestion.py` orquestra o cadastro (`ingest_file`).
- `psycopg_pool` foi **adiado** (F05): a CLI usa uma conexão por execução; o pool só faz sentido com API/web.
- Ingestão de um documento em **uma transação** (documento e chunks gravados juntos ou nada).

## 7. Geração

Mantém o `Generator` e o prompt atuais, com ajustes:

- Se a recuperação retornar vazio (ou abaixo de um limiar mínimo de relevância: `RELEVANCE_THRESHOLD`, cosseno do melhor trecho, 0,50 por padrão, F11; não vale em `lexical`), responde a frase padrão **sem chamar o LLM**.
- Fontes citadas com **arquivo e página**, no contexto enviado ao LLM e na saída da CLI.
- Ler a resposta filtrando blocos `type == "text"`, em vez de `content[0].text`.
- **Vários provedores de LLM:** hoje só o Claude responde. A troca para outros provedores está planejada na §17 (F17); o prompt e as regras desta seção valem para todos.

## 8. CLI unificada — `python -m src.cli`

| Comando | Função |
|---|---|
| `init-db` | Confere conexão e extensão `vector` e aplica todas as migrações `sql/NNN_*.sql` em ordem (idempotente, em uma transação). O modelo de embeddings é gravado em `app_meta` pela **F04**, não aqui. |
| `ingest <arquivo\|pasta> [--recursive/--no-recursive] [--force] [--prune]` | Indexa um arquivo ou uma pasta (incremental, ver seção 4). Pastas são registradas em `sources`. Na F05 aceitava só um arquivo; **a F08 acrescentou pastas e as opções**: `--prune` lista os ausentes e pede confirmação `[s/N]` em terminal interativo; `--force` revetoriza mesmo sem mudança. |
| `reindex <pasta>\|--all [--prune]` | **F08:** reprocessa as pastas registradas, só arquivos novos ou alterados, com o `recursive` guardado em `sources`. Exige `<pasta>` ou `--all`. |
| `search "<pergunta>" [--method rrf\|semantic\|lexical] [--top-k N] [--fetch-k N] [--folder <pasta>] [--full]` | **F06:** mostra os trechos recuperados (arquivo, página, seção, pontuações), sem chamar o Claude. O `ask` (F07) reaproveita a busca. |
| `ask "<pergunta>" [--method rrf\|semantic\|lexical] [--top-k N] [--fetch-k N] [--folder <pasta>]` | **F07:** recupera (F06) e responde sobre **todas** as pastas (ou só a filtrada), em português, mostrando só as fontes citadas (arquivo, página, seção). Busca vazia responde "não encontrei" sem chamar o Claude; sem limiar de relevância até a F11. Código em `src/answer_service.py` e `src/generation.py` (`Generator.answer_hits`). |
| `folders` | **F09 (implementado):** lista pastas registradas, nº de documentos e data da última indexação. |
| `list [--folder <pasta>]` | **F09 (implementado):** lista documentos, status e quantidade de chunks. |
| `delete <arquivo\|pasta>` | **F09 (implementado, `src/management_service.py`):** remove o documento (ou todos os da pasta) e seus chunks. Pede confirmação. |
| `eval [--questions …] [--strategies …] [--max-chars …] [--methods …] [--top-k N] [--answers]` | **F11 (implementado, `src/evaluation.py` e `src/evaluation_service.py`):** mede hit rate@k e MRR por estratégia e tamanho de trecho em tabelas temporárias (sem tocar na base real), compara métodos e propõe o limiar de relevância; `--answers` roda o `ask` real nas perguntas de `data/avaliacao/perguntas.json`. |
| `check` | Verifica variáveis do `.env`, conexão, extensão, tabelas e índices (F01). A verificação dos embeddings (F04) compara o `EMBEDDING_MODEL` do `.env` com o registrado em `app_meta` e a dimensão, sem carregar o modelo; a do Claude (F07) confere só a presença de `ANTHROPIC_API_KEY` e `LLM_MODEL`, sem chamar a API. |
| `menu` (padrão sem argumentos) | **F10 (implementado, `src/menu.py`):** menu interativo (abaixo) quando há terminal; sem terminal, mostra a ajuda. |

### Menu interativo

Menu numerado em terminal puro (`input()`, sem dependência extra), que reutiliza os mesmos serviços dos comandos:

```
=== RAG Training ===
1) Adicionar/indexar pasta
2) Reindexar uma pasta
3) Reindexar todas as pastas
4) Listar pastas e documentos
5) Fazer uma pergunta
6) Remover pasta ou documento
7) Verificar ambiente
0) Sair
```

A opção 5 abre um modo de conversa que mantém o método e o filtro de pasta até o usuário sair.

*(F12: os scripts de comparação do fluxo antigo foram removidos; ficam em `scripts/` apenas os de apoio aos roteiros e o `check_setup`.)*

## 8.1 API REST — `python -m src.api` (F14, verificada)

Mesmas operações da CLI por HTTP, definidas em [features/F14-api-rest.md](features/F14-api-rest.md). Implementada em `src/api/`.

- **Camada fina:** as rotas só chamam os serviços que a CLI usa (`search_service`, `answer_service`, `folder_ingestion`, `ingestion`, `management_service`, `evaluation_service`, `check`). Não há regra de negócio na API.
- **Contrato:** prefixo `/api/v1`, JSON, erro padrão `{"error": {"code", "message", "details"}}`.
- **Endpoints:** `GET /health`, `GET /check`, `POST /db/init`, `POST /ingest`, `POST /reindex`, `GET /jobs/{id}`, `POST /search`, `POST /ask`, `GET /folders`, `GET /documents`, `DELETE /documents`, `DELETE /folders`, `POST /evaluations`.
- **Tarefas:** `ingest`, `reindex` e `eval` respondem `202` e são acompanhadas em `/jobs/{id}`; ficam **em memória**, em fila de um trabalhador; o modelo de embeddings é carregado uma vez.
- **Confirmação:** o `[s/N]` da CLI vira `confirm` (`DELETE`) e `confirm_prune` (`ingest` e `reindex`).
- **Sem autenticação e sem restrição de caminhos nesta fase** (CORS desligado). Todas as rotas ficam em um único `APIRouter` para a dependência de autenticação e autorização (por pessoa, grupo ou documento) entrar depois em um só lugar; até lá, o padrão escuta só em `127.0.0.1`.
- **Pacote:** `src/api/` (`__main__.py`, `routes.py`, `schemas.py`, `jobs.py`, `errors.py`); dependências: `fastapi` e `uvicorn` (aprovadas).

## 9. Configuração e dependências

`.env` / `.env.example`:

```
ANTHROPIC_API_KEY=
HF_TOKEN=
LLM_MODEL=
EMBEDDING_MODEL=BAAI/bge-m3
DATABASE_URL=postgresql://rag_user:<SENHA>@localhost:5432/rag_training_db
RELEVANCE_THRESHOLD=0.50
API_HOST=127.0.0.1   # F14: endereço da API; só 127.0.0.1 por padrão
API_PORT=8000        # F14
```

Banco: `rag_training_db`; usuário: `rag_user`. A **senha fica só no `.env`** (que está no `.gitignore`), nunca neste arquivo nem no `.env.example`, que usa o placeholder `<SENHA>`.

(O `.env.example` já usa `LLM_MODEL`; a variável antiga `MODEL` foi corrigida.)

Adicionar a `requirements.txt`, cada pacote junto da feature que o usa: `psycopg[binary]` (F01), `psycopg_pool` e `pgvector` (F05/F06) e `pymupdf4llm` (F02). `rank-bm25` foi removido na F12. A F14 acrescenta `fastapi` e `uvicorn` (o `pydantic` vem junto).

## 10. Estrutura alvo

```
.spec/                 (NEGOCIO.md, ARQUITETURA.md, ROADMAP.md, features/_TEMPLATE.md e as specs FNN-*.md)
src/
  config.py  loaders.py  chunking.py  embeddings.py
  db.py  repository.py  ingestion.py  folder_ingestion.py  retrieval.py  search_service.py  answer_service.py
  generation.py  management_service.py  menu.py  evaluation.py  evaluation_service.py  cli.py
  api/                 (F14: __init__.py  __main__.py  routes.py  schemas.py  jobs.py  errors.py)
sql/setup_admin.sql    (preparação manual, uma vez: usuário, banco e extensão; exige superusuário)
sql/001_init.sql  002_file_type_md.sql  003_busca_textual.sql
scripts/               (check_setup, read_document, chunk_document, embed_document, compare_chunking)
data/                  (manual_colaborador.txt, amostras/, avaliacao/)
```

`retrieval.py` concentra os métodos de busca em SQL e o limiar de relevância. *(F12: não existe `pipeline.py`; o fluxo ficou em `search_service.py` e `answer_service.py`. Os scripts de comparação do fluxo antigo foram removidos; o `eval` da F11 faz a avaliação.)*

## 11. Fases de implementação

0. **Ambiente:** pgvector 0.8.7 já instalado via Homebrew (Postgres 18.6); falta criar o banco `rag_training_db` e o usuário `rag_user`, e `CREATE EXTENSION vector` (a criação da extensão exige superusuário ou permissão equivalente, então é feita uma vez pelo administrador do Postgres).
1. **Loaders** TXT/MD/PDF + verificação manual (PDF de amostra com texto e um sem texto).
2. **Camada Postgres:** `db.py`, `repository.py`, `init-db`.
3. **Ingestão e CLI** (`ingest`, `list`, `delete`).
4. **Busca híbrida em SQL** + `ask`, com paridade de resultados com o comportamento atual para as perguntas do manual.
5. **Chunking estruturado** + script de avaliação (hit rate/MRR); decidir o padrão com base nos números.
6. **Limpeza do legado (F12, concluída):** removidos `vector_store.py`, `lexical_search.py`, `fusion.py`, `rag.py` e `hybrid_rag.py`. **`data/index/` foi removido na F12**, revogando a decisão anterior de mantê-lo; o `data/manual_colaborador.txt` fica.

## 12. Critérios de aceite

- `ingest` aceita `.txt`, `.md` e `.pdf` e rejeita outros formatos; PDF sem texto gera erro claro.
- Reingerir o mesmo arquivo não duplica chunks; arquivo alterado substitui os chunks antigos; `reindex` só reprocessa o que mudou.
- O mesmo conteúdo em dois caminhos (mesma pasta ou pastas diferentes) é indexado uma única vez, e o duplicado é informado no resumo.
- Indexar duas pastas diferentes e perguntar sem filtro usa documentos das duas; com `--folder` usa só a escolhida.
- Um PDF grande (a definir, ex.: 300+ páginas) é indexado com progresso visível, sem consumo de memória proporcional ao arquivo inteiro, e uma falha no meio não deixa documento parcial nas buscas.
- `ask` devolve resposta com citações e fontes contendo arquivo e página.
- Perguntas de exemplo do manual (`E-5107`, "posso trabalhar de casa", limite de refeição) retornam o chunk correto em `rrf`.
- Sem contexto relevante, a resposta é a frase padrão e **nenhuma chamada ao LLM é feita**.
- Trocar `EMBEDDING_MODEL` sem reindexar gera um aviso claro. *(A troca em si é a F16, §16.)*
- *(F17, §17)* A resposta funciona com qualquer provedor aprovado, indica qual a gerou, e trocar de provedor não exige reindexar.
- **Sem testes automatizados:** todos os testes são **manuais**, executados conforme os critérios de aceite de cada feature (ver seção 14).

## 13. Pontos a confirmar (não assumidos)

- Limites padrão de tamanho de arquivo/páginas (seção 6.1).
- Layout real dos PDFs (colunas, tabelas, cabeçalhos e rodapés repetidos): só é possível validar com amostras do usuário. Pode ser necessário remover cabeçalhos e rodapés repetidos.
- Limiar mínimo de relevância e tamanho final dos chunks: serão definidos com a avaliação da fase 5, não de antemão.
- **F15, F16 e F17:** os pontos em aberto de cada uma estão no fim das seções 15, 16 e 17.

Resolvidos: banco `rag_training_db`, usuário `rag_user` (senha só no `.env`); `data/index/` foi removido na F12 (revoga a decisão anterior de mantê-lo); **arquivos duplicados (mesmo `sha256`) são ignorados**; **pgvector 0.8.7** (Homebrew) confirmado instalado, com Postgres 18.6.

## 14. Estratégia de testes

**Decisão:** não haverá testes unitários nem automatizados (sem `pytest` e sem pasta `tests/`). Toda validação é **manual**.

- Cada spec de feature segue o template `.spec/features/_TEMPLATE.md`, cuja **seção 9** traz os **critérios de aceite escritos como roteiro manual**: passos, comando a executar e resultado esperado. A seção 10 lista os roteiros de outras features a repetir (regressão) e a seção 14 registra a execução.
- Os roteiros usam arquivos de exemplo versionados (`data/manual_colaborador.txt`) e PDFs de amostra, incluindo um PDF sem texto e um arquivo corrompido.
- Um banco separado para experimentos pode ser criado manualmente quando for preciso testar sem afetar a base principal.
- Como não há rede de segurança automática, o código deve falhar de forma **clara** (mensagens explícitas) e cada feature deve ser verificada logo após implementada, antes de seguir para a próxima.
- Risco aceito: mudanças futuras podem quebrar comportamentos antigos sem aviso. A mitigação é repetir os roteiros das features anteriores que forem afetadas.

## 15. Contêineres — Dockerfile e Docker Compose (F15, planejada, sem spec)

Objetivo: `docker compose up` sobe o banco e a aplicação sem instalar PostgreSQL, pgvector nem Python na máquina.

**Requisito de plataforma (decisão do usuário):** o mesmo `Dockerfile` e o mesmo `docker-compose.yml` precisam funcionar em **macOS, Windows e Linux**, em processadores **amd64** (Intel/AMD) e **arm64** (Apple Silicon e ARM), sem arquivos separados por sistema. Os requisitos que decorrem disso estão na tabela "Requisitos multiplataforma" abaixo. Esta seção registra o que a spec da F15 precisará decidir e cobrir; **nada disto está implementado**.

**Fatos do projeto que condicionam a F15**
- Python 3.10 ou superior. `requirements.txt` **sem versões fixadas**: `anthropic`, `sentence-transformers`, `numpy`, `python-dotenv`, `psycopg[binary]`, `pymupdf4llm`, `pgvector` (e `fastapi` e `uvicorn` com a F14). A imagem precisa de versões fixadas para ser reproduzível.
- Banco atual: PostgreSQL 18.6 com pgvector 0.8.7; banco `rag_training_db`, usuário `rag_user`; **senha só no `.env`**, nunca na imagem nem em arquivo versionado.
- `sql/setup_admin.sql` (usuário, banco e extensão `vector`) exige superusuário e hoje é manual. O `init-db` aplica `sql/NNN_*.sql` em ordem e é idempotente.
- O `Embedder` escolhe **MPS no Mac, senão CPU** (`src/embeddings.py`); não há ramo para CUDA. **Dentro do contêiner, em qualquer sistema, roda em CPU** (o Docker no Mac não expõe o MPS), mais lento. O código 134 da F04 era do torch com MPS e não se aplica ao contêiner. Usar GPU NVIDIA (Linux e Windows) exigiria suporte a CUDA no `Embedder` e a imagem do torch correspondente: fora do escopo da F15.
- `BAAI/bge-m3` ocupa cerca de 2,3 GB em disco e 1,4 GB em memória e é baixado do Hugging Face na primeira execução (`HF_TOKEN` opcional). Sem cache persistente, cada contêiner novo baixa de novo.
- A API (F14) **não tem autenticação**, aceita qualquer caminho em `ingest` e só deve escutar em `127.0.0.1`.
- O `ingest` lê o disco **do contêiner**: os documentos precisam ser montados por volume, e os caminhos nos comandos são os de dentro do contêiner.

**Arquivos previstos:** `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example` ampliado (valores para o Compose) e seção "Docker" no `README.md`. Se necessário, um script de entrada em `docker/`.

**Decisões de desenho** (as marcadas "decisão do usuário" ou listadas abaixo como decisões já foram tomadas; as demais são propostas a confirmar na spec)
| Tema | Proposta |
|---|---|
| Serviços | `db` (`pgvector/pgvector`, tag `pg18` a confirmar), `api` (F14) e `cli` (perfil `tools`, usado com `docker compose run --rm cli <comando>` para `init-db`, `ingest`, `eval`), **a `api` e a `cli` na mesma imagem**. |
| Imagem da aplicação | Dockerfile multi-etapas, usuário sem privilégio, `torch` em versão CPU para reduzir a imagem, versões fixadas, sem `.env`, `.venv`, `.git` nem PDFs reais (`data/amostras/real.pdf` e `grande.pdf`) no contexto (`.dockerignore`). |
| Volumes | Volume nomeado para os dados do PostgreSQL; volume nomeado para o cache do Hugging Face (`HF_HOME`); **bind mount somente leitura** da pasta de documentos. |
| Rede | Porta da API publicada como `127.0.0.1:8000:8000` (dentro do contêiner a API escuta em `0.0.0.0`; a restrição fica no mapeamento de porta). Banco **sem** porta publicada (ou só em `127.0.0.1`). `DATABASE_URL` com host `db`. |
| Segredos | `ANTHROPIC_API_KEY`, `HF_TOKEN` e a senha do banco por `env_file` ou variáveis do ambiente, nunca `ENV` no Dockerfile. |
| Inicialização do banco | `setup_admin.sql` em `/docker-entrypoint-initdb.d/` (executa só com o volume novo). `init-db` continua um passo explícito da CLI; nenhuma migração automática escondida. |
| Saúde e ordem | `pg_isready` no `db`, `GET /health` (F14) na `api` e `depends_on` com `condition: service_healthy`. |
| Recursos | Documentar o mínimo (≥ 4 GB de memória para o Docker) e que PDFs grandes serão mais lentos em CPU. |
| Backup | Documentar `pg_dump` e restauração; o volume do banco é a única cópia dos vetores. |

**Requisitos multiplataforma (macOS, Windows e Linux; amd64 e arm64)**
| Tema | Requisito |
|---|---|
| Arquitetura | A imagem da aplicação e a do banco precisam existir para **amd64 e arm64** (imagem multi-arquitetura ou `docker buildx`); confirmar que `torch` (versão CPU), `pymupdf4llm` e `psycopg[binary]` têm pacotes para as duas. Nunca fixar `platform:` no Compose. |
| Windows | Suporte por **Docker Desktop com WSL 2**. Documentar os comandos também em **PowerShell** (variáveis de ambiente, caminhos). Memória do WSL 2 pode precisar de ajuste (`.wslconfig`) para os ≥ 4 GB. |
| Fim de linha | Scripts de entrada (`docker/*.sh`) e `setup_admin.sql` precisam de **LF**: acrescentar `.gitattributes` (`*.sh text eol=lf`), pois o Git no Windows converte para CRLF e quebra o `#!/bin/sh` dentro do contêiner. |
| Caminhos | Os comandos usam os caminhos **de dentro do contêiner** (ex.: `/data/docs`), iguais nos três sistemas. O caminho do computador só aparece no `docker-compose.yml`, por variável (ex.: `DOCS_DIR`), com o exemplo de cada sistema (`/home/ana/docs`, `C:\Users\ana\docs`, `~/docs`). |
| Volumes e permissões | Preferir **volumes nomeados** para banco e cache. No bind mount de documentos (somente leitura) o usuário sem privilégio do contêiner precisa conseguir ler; no Linux, definir o `uid`/`gid` por variável (`APP_UID`, `APP_GID`) ou documentar o ajuste. Desempenho de bind mount no Windows/Mac é menor: mesmo assim vale para leitura. |
| Maiúsculas e minúsculas | Linux diferencia `Manual.pdf` de `manual.pdf`; macOS e Windows não. Conferir se algum caminho ou nome de arquivo do projeto depende disso. |
| Rede | Mapear `127.0.0.1:8000:8000` em todos os sistemas (a restrição de rede da F14 vale igual). Para acessar o PostgreSQL do host, não usar `network_mode: host` (não existe no Docker Desktop). |
| Compose | Usar a sintaxe do **Docker Compose v2** (`docker compose`, sem hífen) e sem recursos exclusivos de um sistema. Versão mínima do Docker e do Compose documentada no README. |
| Recursos | ≥ 4 GB de memória para o Docker e cerca de 6 GB de disco (imagem, modelo e banco); em Windows e Mac o limite é configurado no Docker Desktop/WSL 2, em Linux vale a memória do host. |
| Tempo | CPU sem GPU: o cadastro de PDFs grandes é mais lento em qualquer sistema; registrar o tempo medido de `grande.pdf` em cada sistema testado, sem meta fixa. |

**Fora do escopo da F15:** Kubernetes ou outra orquestração, HTTPS e proxy reverso, GPU no contêiner, CI/CD, publicação em registry, autenticação da API (é a evolução de controle de acesso).

**Decisões do usuário nos pontos que estavam em aberto da F15** (2026-10-11)
1. **Uso: só local** nesta fase. API em `127.0.0.1`, banco sem porta publicada. Servidor da equipe (rede, HTTPS, proxy reverso, autenticação) fica para depois da autenticação e do controle de acesso.
2. **Uma imagem, dois usos:** um só `Dockerfile` e uma só imagem; o serviço `api` roda `python -m src.api` e o serviço `cli` (perfil `tools`) usa a mesma imagem com `docker compose run --rm cli <comando>`.
3. **Documentos:** variável `DOCS_DIR` no `.env` (pasta do computador), montada **somente leitura** em `/data/docs`; os comandos usam `/data/docs/...` nos três sistemas. A base do Docker **começa vazia** e os documentos são cadastrados de novo, porque a tabela `sources` guarda caminhos e os de um banco local (`/Users/...`) não existem no contêiner. Migrar uma base local para o Docker não faz parte da F15.
4. **Imagem do banco:** `pgvector/pgvector` oficial com a tag `pg18`. A tag e as arquiteturas **amd64 e arm64 devem ser conferidas no Docker Hub ao escrever a spec**; se não existirem, construir a imagem a partir de `postgres:18` instalando o pgvector. Atenção: nas imagens do PostgreSQL 18 mudou o diretório de dados; conferir o ponto de montagem do volume.
5. **Versões:** fixar com `==` as 7 bibliotecas diretas do `requirements.txt` (as que funcionam hoje no `.venv`) e a versão do Python da imagem. Dependências indiretas não são travadas. A alteração do `requirements.txt` vale também para quem instala sem Docker.
6. **Sistemas com suporte oficial** (o roteiro manual roda em cada um): **macOS Apple Silicon**, **Windows 11 com Docker Desktop (WSL 2)** e **Ubuntu LTS 22.04/24.04 (amd64)**. Windows 10, outras distribuições Linux e macOS Intel ficam como "devem funcionar, não testados". **Uma pessoa da equipe por sistema** executa o roteiro e registra na seção 14.
7. **Modelo de embeddings:** volume nomeado de cache (`HF_HOME`); o modelo é baixado no **primeiro uso** e reaproveitado. Sem modelo dentro da imagem (a troca da F16 não exige rebuild). O primeiro uso precisa de internet; avisar no README. Na F16, a troca de modelo mantém dois modelos em memória: documentar **≥ 6 GB** para essa operação.

**Pontos em aberto da F15:** nenhum de desenho. Ficam a conferir na spec: tag `pg18` e arquiteturas da imagem do banco, versões exatas das bibliotecas, pacotes de `torch` (CPU), `pymupdf4llm` e `psycopg[binary]` para amd64 e arm64, e o ponto de montagem do volume do PostgreSQL 18.

**Roteiro manual previsto (a detalhar na spec):** `docker compose build`; `up` com banco vazio; `init-db`; `check`; `ingest` de `data/amostras`; `search` e `ask` com resultados iguais aos da instalação local **e entre os sistemas**; `GET /health`; reiniciar e confirmar que banco e modelo persistem (sem novo download); `down` e `up` sem `-v`; a API inacessível de outra máquina; banco sem porta publicada; imagem sem `.env` (`docker history` e `docker run ... env`).

**Verificação por sistema:** repetir o roteiro completo em **macOS (Apple Silicon), Windows 11 com Docker Desktop (WSL 2) e Linux (amd64)**, e anotar na seção 14 da spec o sistema, a arquitetura, as versões do Docker/Compose e o tempo de cadastro de `grande.pdf`. O mesmo comando (`docker compose up`) deve funcionar sem edição em cada um, trocando só variáveis do `.env` (ex.: `DOCS_DIR`).

**Regressão prevista:** F01 (`check`, `init-db`), F05/F08 (`ingest` e `reindex` com caminhos do contêiner), F06/F07 e F14 (todos os endpoints).

## 16. Troca do modelo de embeddings — F16 (planejada, sem spec)

Objetivo: trocar `EMBEDDING_MODEL` de forma segura, revetorizando a base inteira, em vez de só bloquear (F04). Esta seção registra o que a spec da F16 precisará decidir e cobrir; **nada disto está implementado**.

**Fatos do projeto que condicionam a F16**
- `app_meta` guarda `embedding_model` e `embedding_dim` na **primeira** vetorização e **nunca sobrescreve** (`register_embedding_model` com `ON CONFLICT DO NOTHING`, em `src/db.py`). Se o `.env` divergir, `ensure_embedding_model` bloqueia **antes de carregar o modelo**, com a orientação de reindexar. Hoje essa orientação não leva a lugar nenhum: `ingest --force` e `reindex` refazem com o modelo **registrado**.
- `chunks.embedding` é `vector(1024) NOT NULL` com índice HNSW `vector_cosine_ops` (`sql/001_init.sql`), e `EMBEDDING_DIM = 1024` é constante em `src/db.py`. Um modelo de **outra dimensão** exige migração (nova coluna ou nova dimensão, recriar o índice); não existe conversão entre espaços vetoriais.
- Os textos (`content`, `tsv`, `tsv_en`) **não dependem do modelo**. Só `embedding` muda. A busca `lexical` segue funcionando durante a troca, e não é preciso reler os arquivos originais.
- O `RELEVANCE_THRESHOLD` 0,50 e os trechos de 900/110 foram medidos com o `bge-m3` na F11. Outro modelo muda a escala do cosseno e o limite de tokens; limiar e tamanho precisam ser revistos com o `eval`.
- Alguns modelos exigem prefixos para consulta e documento (por exemplo, a família E5 usa `query:` e `passage:`) e têm `max_seq_length` diferente (o `bge-m3` usa 8192). Hoje o `Embedder` não aplica prefixos.
- Com a F14, a API tem fila de um trabalhador e devolve `409 embedding_model_mismatch` quando o `.env` diverge; a troca precisa conviver com isso.

**Arquivos previstos:** função de revetorização em `src/embeddings.py` ou módulo novo (ex.: `src/reembedding.py`), subcomando da CLI, `repository.py` (leitura dos trechos em lotes e gravação dos vetores novos), migração `sql/00N_*.sql` para dimensão diferente, item no menu (F10) e endpoint na API (F14), se existirem.

**Decisões de desenho** (as marcadas "decisão do usuário" ou listadas abaixo como decisões já foram tomadas; as demais são propostas a confirmar na spec)
- **Comando dedicado `reembed`** (decisão do usuário): `python -m src.cli reembed --model <novo> [--yes] [--dry-run]`. Sem `--yes` mostra o plano (documentos, trechos, dimensões antiga e nova, tempo estimado) e pede `[s/N]`; sem terminal, recusa. `--dry-run` só valida o modelo e mostra o plano. **Não edita o `.env`**: ao terminar, o banco passa a registrar o modelo novo e a pessoa atualiza `EMBEDDING_MODEL` (e os prefixos); até lá a F04 bloqueia o uso com a mensagem de divergência. Nunca é efeito colateral de mudar o `.env`.
- **Etapas:** (1) validar o modelo novo (carrega, dimensão, `max_seq_length`, prefixos); (2) mostrar o plano (documentos, trechos, dimensões antiga e nova, tempo estimado) e pedir confirmação (R10, R12 propostas no NEGOCIO); (3) revetorizar a partir de `chunks.content`, em lotes e com progresso; (4) trocar `embedding_model`, `embedding_dim` e o índice **só ao final**; (5) rodar o `eval` com o modelo novo e propor o novo limiar.
- **Estratégia A, coluna sombra** (decisão do usuário): cria `embedding_new` (e o índice), preenche em lotes a partir de `chunks.content` enquanto a busca segue com o modelo antigo, e só no fim troca o registro (`app_meta`) e a coluna em **uma transação curta**. Falha ou interrupção deixam a base antiga intacta. Custo: cerca de 20 MB extras para 4.858 trechos (vetores de 1024 dimensões em 4 bytes). As opções B (transação única, sem retomada) e C (novo banco e troca de `DATABASE_URL`) foram descartadas.
- **Interrupção:** **retomável** (consequência da estratégia A: marca quais trechos já têm o vetor novo e o `reembed` continua dali); a base **nunca** fica com vetores de dois modelos visíveis para a busca (R13 proposta).
- **Dimensão diferente:** migração idempotente; a dimensão passa a ser lida de `app_meta` em vez da constante `EMBEDDING_DIM`; o `check` compara a coluna com o modelo registrado.
- **Reversão:** manter o modelo anterior registrado até a conclusão; recomendar `pg_dump` antes (e o documento da F15 descreve o backup).
- **Qualidade:** comparar hit@k e MRR do modelo novo com o `bge-m3` usando `data/avaliacao/` antes de confirmar; registrar o novo `RELEVANCE_THRESHOLD` e, se necessário, revisar `MAX_CHARS` e `OVERLAP_CHARS` (um `reindex --force` pode ser exigido).
- **Prefixos** (decisão do usuário): variáveis opcionais `EMBEDDING_QUERY_PREFIX` e `EMBEDDING_DOC_PREFIX` no `.env` (vazias por padrão, como hoje com o `bge-m3`). O `reembed` grava os valores em `app_meta` junto do modelo; se divergirem do `.env`, a F04 bloqueia como faz com o nome do modelo, porque prefixo diferente gera vetores não comparáveis. O `Embedder` passa a aplicar `EMBEDDING_QUERY_PREFIX` às perguntas e `EMBEDDING_DOC_PREFIX` aos trechos.
- **Durante a troca** (decisão do usuário): `search` e `ask` continuam com o modelo antigo; `ingest`, `reindex`, `delete` e outro `reembed` são **recusados** com mensagem clara, por uma trava global na base (como a trava por pasta da F08; some se o processo cair). Isso evita trechos novos sem o vetor novo. Consequência: o modelo antigo (nas consultas) e o novo (no `reembed`) ficam em memória juntos, cerca de 2,8 GB; no Docker, **≥ 6 GB**. Na API (F14), as rotas de alteração respondem `409` com um código próprio (ex.: `reembed_in_progress`).

**Fora do escopo da F16:** modelos esparsos ou multi-vetor (§3), vários modelos ao mesmo tempo, reranking, troca de dimensão sem reprocessar.

**Modelos para validar a F16** (decisão do usuário): `intfloat/multilingual-e5-large` (1024 dimensões, testa a troca sem mudar a dimensão e os prefixos `query: ` e `passage: `) e `intfloat/multilingual-e5-small` (384 dimensões, testa a migração de dimensão e roda leve em CPU). As dimensões vêm do conhecimento do modelo e **devem ser conferidas nos cartões do Hugging Face** ao escrever a spec. Modelos candidatos para uso real são avaliados com o `eval`, depois.

**Decisões do usuário nos pontos que estavam em aberto da F16** (2026-10-11): estratégia A (coluna sombra); comando `reembed --model <novo>`; prefixos por variáveis registradas no banco; consultas continuam e alterações são recusadas durante a troca; modelos de teste e5-large e e5-small. O espaço em disco deixou de ser uma dúvida (≈ 20 MB para a base atual).

**Pontos em aberto da F16:** nenhum de desenho. Ficam a conferir na spec: dimensões e prefixos dos modelos de teste, tempo real da troca em CPU no Docker (medir), o nome do código de erro da API durante a troca e se a migração de dimensão usa a coluna sombra já na nova dimensão (provável) ou uma migração `sql/00N_*.sql` separada.

**Roteiro manual previsto (a detalhar na spec):** troca para modelo de mesma dimensão; troca para outra dimensão; recusa sem confirmação; interrupção no meio e retomada (nenhuma busca mistura modelos); base vazia; `check` coerente antes, durante e depois; `eval` antes e depois, com novo limiar; busca durante a troca; `ingest` bloqueado durante a troca; reversão.

**Regressão prevista:** F04 (bloqueio por divergência, `check`), F05, F08 (`--force`, `reindex`), F06, F07, F11 (`eval`) e, se existir, F14.

## 17. Vários provedores de LLM — F17 (planejada, sem spec)

Objetivo: gerar as respostas do `ask` com outros modelos além do Claude: **OpenAI (ChatGPT), Gemini, DeepSeek e Ollama (modelo local)**. Esta seção registra o que a spec da F17 precisará decidir e cobrir; **nada disto está implementado**.

**Fatos do projeto que condicionam a F17**
- O acoplamento ao Claude está **em um arquivo**: `src/generation.py` (`Generator`, que usa o SDK `anthropic`, `ANTHROPIC_API_KEY` e `LLM_MODEL`, e traduz os erros do SDK em `GenerationError`). O prompt (`SYSTEM_PROMPT`, `build_context_prompt`) usa marcação em texto puro (`<contexto>`, `<trecho>`, `<pergunta>`) e é neutro quanto ao provedor.
- Os nomes `ANTHROPIC_API_KEY` e `LLM_MODEL` estão **fixos** em quatro pontos: `src/answer_service.py` (antes da busca), `src/db.py` (`check`), `src/evaluation_service.py` (`--answers`) e `scripts/check_setup.py`. As mensagens da CLI e do menu dizem "Claude".
- `answer_service.py` detecta a resposta negativa pela frase `NOT_FOUND_ANSWER` **no início** da resposta e extrai as fontes pelas citações `[n]`; essas duas regras dependem de o modelo obedecer ao prompt.
- A F11 já mede respostas reais (`eval --answers`): é o método para validar cada provedor.
- Os vetores vêm do modelo local de embeddings (`bge-m3`): **trocar o LLM não exige reindexar nem migrar o banco**.

**Decisões do usuário** (2026-10-11)
1. **Escolha fixa no `.env`, com override opcional:** `LLM_PROVIDER` e `LLM_MODEL` definem o padrão; o `ask` aceita `--llm` para uma execução.
2. **Provedores da 1ª versão:** Claude (atual), OpenAI, Gemini, DeepSeek e Ollama.
3. **Privacidade:** lista de provedores aprovados (R11 revisada, NEGOCIO §5): qualquer outro é recusado; o provedor usado aparece na resposta e no `check`.
4. **Lista inicial de aprovados:** Claude, OpenAI, Gemini, **DeepSeek** e Ollama. O DeepSeek foi **aprovado pelo usuário**, ciente de que os servidores da API ficam na China.
5. **Detalhes das APIs:** URLs, nomes de parâmetros, modelos disponíveis e a compatibilidade do Gemini serão **obtidos durante a especificação**, na documentação oficial de cada provedor, e não agora.

**Desenho proposto (a confirmar na spec)**
| Tema | Proposta |
|---|---|
| Interface | Um contrato único de provedor (ex.: `LLMProvider.answer(question, hits, max_tokens) -> GeneratedAnswer`), com o `Generator` escolhendo o adaptador por `LLM_PROVIDER`. `GeneratedAnswer` ganha `provider` e `model`. |
| Adaptadores | **Anthropic:** o código atual, sem mudança de comportamento. **Compatível com OpenAI:** um adaptador só, com o SDK `openai`, que atende OpenAI, DeepSeek, Gemini (pelo endpoint de compatibilidade do Google, **a confirmar**) e Ollama, mudando `LLM_BASE_URL`, chave e modelo. Alternativa descartada por ora: biblioteca intermediária (LiteLLM), por trazer uma dependência grande. |
| Variáveis | `LLM_PROVIDER` (`anthropic`, `openai`, `gemini`, `deepseek`, `ollama`), `LLM_MODEL`, `LLM_API_KEY` (ou uma chave por provedor), `LLM_BASE_URL` (com padrão por provedor). `ANTHROPIC_API_KEY` continua valendo para o Claude, por compatibilidade. Ollama não exige chave. |
| Lista de aprovados | Constante ou variável (`LLM_APPROVED_PROVIDERS`) conferida antes de qualquer chamada; provedor fora da lista dá erro em português e nenhuma chamada sai. |
| Conferências | As quatro conferências fixas passam a perguntar ao provedor quais variáveis são obrigatórias. O `check` confere só a **presença** das variáveis (sem chamar a API, como hoje) e mostra o provedor e o modelo; `scripts/check_setup.py` faz a chamada real ao provedor configurado. |
| Erros | Cada adaptador traduz os erros do seu SDK nas mesmas mensagens em português de hoje (chave recusada, modelo indisponível, limite atingido, sem conexão, erro do serviço), citando o nome do provedor em vez de "Claude". |
| `max_tokens` | `ANSWER_MAX_TOKENS` (600) é traduzido para o nome do parâmetro de cada API (alguns usam outro nome). Modelos de raciocínio gastam parte do limite pensando; a resposta cortada continua sinalizada por `truncated`. A spec decide se o limite sobe ou se há um valor por provedor. |
| Saída | CLI, menu e API mostram o provedor e o modelo usados (R15 proposta). |
| `--llm` | `--llm <provedor>[:<modelo>]` no `ask` e no `eval --answers`; o `eval` pode receber vários para comparar. |
| Docker (F15) | O contêiner acessa o Ollama do computador por `host.docker.internal` (no Linux exige `extra_hosts`/`host-gateway`); chaves por `env_file`, nunca na imagem. |
| API (F14) | Campo opcional `provider` e `model` no corpo do `/ask`, validados contra a lista de aprovados, e os dois campos na resposta. |

**Arquivos previstos:** `src/generation.py` (refatorado) e, se ficar grande, `src/llm/` (um adaptador por arquivo); `src/config.py`; `src/answer_service.py`; `src/db.py`; `src/evaluation_service.py`; `src/cli.py`; `src/menu.py`; `scripts/check_setup.py`; `requirements.txt` (`openai`, versão fixada); `.env.example`; `README.md`. **Sem migração de banco.**

**Estimativa de impacto:** de 150 a 300 linhas novas ou alteradas, em 7 a 9 arquivos; a maior parte é o `generation.py` e a validação, não a escrita do código. Estimativa sem medição.

**Riscos que a spec precisa tratar**
- **Obediência ao prompt:** modelos diferentes seguem de forma diferente as regras de citar `[n]`, da frase exata de "não encontrei", de ignorar instruções dentro dos documentos e de responder em português. Cada provedor só é suportado depois de passar no `eval --answers` (R16 proposta); pode haver ajuste do `SYSTEM_PROMPT` por provedor.
- **Privacidade:** cada provedor é um novo destino dos trechos; o DeepSeek tem os servidores da API na China (risco **aceito pelo usuário**, que o aprovou); o Ollama mantém tudo na máquina. A lista de aprovados é decisão de negócio (NEGOCIO §5 e §10) e pode ser revista.
- **Custo e chaves:** cada provedor tem preço, limites e uma chave própria; o `eval --answers` consome a cota de cada um.
- **Qualidade do Ollama:** depende do modelo local e da máquina; um modelo pequeno pode falhar nas regras do prompt. A spec registra qual modelo foi testado e pode marcar um provedor como "funciona, qualidade inferior".
- **Detalhes de cada API** (URLs, nomes de parâmetros, compatibilidade do Gemini): serão **obtidos durante a especificação**, na documentação oficial; as compatibilidades citadas aqui vêm de conhecimento geral e não foram testadas. O desenho desta seção pode mudar conforme o que a especificação encontrar.

**Fora do escopo da F17:** streaming da resposta, uso de ferramentas (function calling), fallback automático entre provedores, mais de um provedor na mesma pergunta, embeddings por API e RAG com histórico de conversa.

**Pontos em aberto da F17:** ~~se o DeepSeek entra na lista inicial de aprovados~~ (resolvido: aprovado); a obtenção dos detalhes das APIs na especificação; qual modelo local usar no Ollama e em que máquina; orçamento de validação por provedor; valor de `max_tokens` por provedor; ajuste do prompt por provedor; um provedor de LLM por chave única (`LLM_API_KEY`) ou uma variável por provedor; formato exato de `--llm`.

**Roteiro manual previsto (a detalhar na spec):** regressão completa do `ask` com o Claude (F07, mesmas respostas e fontes de antes); `ask` em cada provedor (resposta com fonte `[n]` e página; pergunta fora do assunto com a frase padrão; injeção de instrução no contexto ignorada; pergunta em inglês respondida em português); chave inválida, modelo inexistente, limite excedido e sem rede, com mensagem em português; provedor fora da lista recusado sem chamada; `check` mostrando o provedor e as variáveis; `--llm` e a variável do `.env`; `eval --answers` por provedor, comparando acertos e custo; resposta cortada por `max_tokens`; Ollama dentro do Docker (F15), se existir.

**Regressão prevista:** F07 (`ask`), F11 (`eval --answers`), F10 (menu e modo conversa), F01 (`check`) e, se existirem, F14 (`/ask`) e F15.
