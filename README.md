# RAG Training (Python)

Aplicação de estudo de **RAG** (Retrieval-Augmented Generation). Ela cadastra documentos **TXT, MD e PDF com texto**, guarda os trechos e seus vetores no **PostgreSQL com pgvector**, busca os trechos mais relevantes para uma pergunta e pede ao **Claude** uma resposta baseada **só** nesses trechos, com a indicação de documento e página. Se os documentos não trazem a informação, ela diz que não encontrou.

- Interface: **linha de comando** (`python -m src.cli`) e menu interativo.
- Embeddings: **SentenceTransformer** (exemplo: `BAAI/bge-m3`, 1024 dimensões).
- Busca: **híbrida em SQL** (significado + palavras exatas, em português e inglês), com filtro opcional por pasta.
- Geração: **Claude**, pela SDK `anthropic`.

O projeto é conduzido por **Spec Driven Development**: as regras e as decisões estão em [.spec/](.spec/) (`NEGOCIO.md`, `ARQUITETURA.md`, `ROADMAP.md` e uma spec por feature).

---

## Arquitetura

```
              CADASTRO (ingest / reindex)
 arquivo ─► leitura ─► trechos ─► vetores ─► PostgreSQL
 (TXT/MD/PDF)  (páginas)  (por título/       (documents, chunks,
                           parágrafo)          pgvector + tsvector)

              CONSULTA (search / ask)
 pergunta ─► vetor ─► busca híbrida em SQL (RRF) ─► limiar de relevância
                                                         │
                       resposta com fontes [n] ◄─ Claude ◄┘
```

## Estrutura do projeto

```
src/
  cli.py                 comandos e formatação da saída
  menu.py                menu interativo e modo conversa
  config.py              variáveis do .env
  db.py                  conexão, migrações e verificação do ambiente
  repository.py          SQL de documentos, trechos e pastas
  loaders.py             leitura de TXT, MD e PDF (página a página)
  chunking.py            divisão em trechos (estratégia estruturada e outras)
  embeddings.py          Embedder (SentenceTransformer) e embed_chunks
  ingestion.py           cadastro de um arquivo
  folder_ingestion.py    cadastro e atualização incremental de pastas
  retrieval.py           busca em SQL (rrf, semantic, lexical) e limiar
  search_service.py      fluxo do comando search
  generation.py          prompt e chamada ao Claude
  answer_service.py      fluxo do comando ask
  management_service.py  pastas, listagem e remoção
  evaluation.py          perguntas de teste e métricas
  evaluation_service.py  fluxo do comando eval
  api/                   API REST (rotas, tarefas, erros e esquemas)
sql/                     migrações 001 a 003 e setup_admin.sql
scripts/                 scripts de apoio (veja abaixo)
data/
  manual_colaborador.txt   documento de exemplo
  amostras/                arquivos de exemplo e de teste manual
  avaliacao/               documentos e perguntas do comando eval
.spec/                   especificações (negócio, arquitetura, roadmap, features)
Dockerfile               imagem da aplicação (API e CLI)
docker-compose.yml       serviços db, api e cli (perfil tools)
docker/init-db.sh        preparo do banco na primeira subida do volume
```

## Requisitos e instalação

- Python 3.10 ou superior.
- PostgreSQL com a extensão **pgvector** (desenvolvido com PostgreSQL 18.6 e pgvector 0.8.7).
- Chave da API da Anthropic.
- Na primeira execução, o modelo de embeddings é baixado do Hugging Face.

Prefere não instalar nada? Veja a seção [Docker](#docker).

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # depois edite os valores
```

Preparo do banco (uma vez, como superusuário do Postgres; cria o usuário `rag_user`, o banco `rag_training_db` e a extensão `vector`):

```bash
psql -d postgres -v rag_password='<SENHA>' -f sql/setup_admin.sql
python -m src.cli init-db     # aplica as migrações
python -m src.cli check       # confere ambiente, banco e variáveis
```

### Configuração (`.env`)

| Variável | Uso |
|---|---|
| `ANTHROPIC_API_KEY` | Chave da API do Claude (obrigatória no `ask`). |
| `LLM_MODEL` | Modelo do Claude usado na resposta. |
| `EMBEDDING_MODEL` | Modelo SentenceTransformer, por exemplo `BAAI/bge-m3`. |
| `HF_TOKEN` | Token do Hugging Face (opcional). |
| `DATABASE_URL` | Conexão com o Postgres (`postgresql://rag_user:<SENHA>@localhost:5432/rag_training_db`). A senha fica só no `.env`. |
| `API_HOST` / `API_PORT` | Endereço e porta da API REST. Padrão `127.0.0.1` e `8000`. |
| `RELEVANCE_THRESHOLD` | Similaridade mínima (0 a 1) do melhor trecho para o `ask` chamar o Claude. Padrão `0.50`; vazio desliga o limiar. |

## Uso

Execute sempre da raiz do projeto. Sem argumentos, em um terminal interativo, o comando abre o menu.

| Comando | O que faz |
|---|---|
| `python -m src.cli init-db` | Aplica o esquema e as migrações (idempotente). |
| `python -m src.cli check` | Verifica variáveis do `.env`, banco, tabelas e modelo de embeddings. |
| `python -m src.cli ingest <arquivo\|pasta> [--recursive/--no-recursive] [--force] [--prune]` | Cadastra um arquivo ou uma pasta. Atualização incremental: só o que é novo ou mudou. `--prune` remove da base, com confirmação, o que sumiu da pasta. |
| `python -m src.cli reindex <pasta>\|--all [--prune]` | Reprocessa as pastas já registradas. |
| `python -m src.cli search "<pergunta>" [--method rrf\|semantic\|lexical] [--top-k N] [--fetch-k N] [--folder <pasta>] [--full]` | Mostra os trechos recuperados, sem chamar o Claude. |
| `python -m src.cli ask "<pergunta>" [--method ...] [--top-k N] [--fetch-k N] [--folder <pasta>]` | Responde com fontes (documento, página, seção). |
| `python -m src.cli folders` | Lista as pastas registradas. |
| `python -m src.cli list [--folder <pasta>]` | Lista os documentos da base. |
| `python -m src.cli delete <arquivo\|pasta>` | Remove um documento ou uma pasta, com confirmação. |
| `python -m src.cli eval [--questions ...] [--strategies ...] [--max-chars ...] [--methods ...] [--top-k N] [--answers]` | Mede a qualidade da recuperação (hit rate e MRR), compara estratégias e tamanhos de trecho e propõe o limiar. Não grava na base. `--answers` roda o `ask` real e consome a cota do Claude. |

Exemplo:

```bash
python -m src.cli ingest data/manual_colaborador.txt
python -m src.cli ask "Quantos dias de férias eu tenho?"
python -m src.cli ask "O que significa o erro E-5107?" --method rrf
```

O menu oferece: adicionar pasta, reindexar uma ou todas, listar, perguntar (modo conversa), remover e verificar o ambiente.

## API REST

`python -m src.api` sobe a API (Uvicorn) com as mesmas operações da CLI; a documentação interativa fica em `http://127.0.0.1:8000/docs`. Prefixo `/api/v1`, JSON, erros no formato `{"error": {"code", "message", "details"}}`.

| Endpoint | Equivale a |
|---|---|
| `GET /health`, `GET /check`, `POST /db/init` | saúde, `check`, `init-db` |
| `POST /ingest`, `POST /reindex` | `ingest`, `reindex` (tarefas: respondem `202` e o resultado sai em `GET /jobs/{id}`) |
| `POST /search`, `POST /ask` | `search`, `ask` |
| `GET /folders`, `GET /documents?folder=` | `folders`, `list` |
| `DELETE /documents?path=&confirm=true`, `DELETE /folders?path=&confirm=true` | `delete` (sem `confirm=true` nada é removido e a prévia é devolvida) |
| `POST /evaluations` | `eval` (tarefa) |

**Atenção:** a API não tem autenticação e aceita qualquer caminho do servidor em `ingest`. Por isso escuta só em `127.0.0.1` por padrão; abrir para a rede (`API_HOST=0.0.0.0`) é decisão sua. As tarefas ficam em memória, uma por vez, e somem ao reiniciar. Exemplo:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/ask -H 'Content-Type: application/json' \
  -d '{"question": "Como funciona o trabalho remoto?"}'
```

## Docker

Sobe o banco (PostgreSQL com pgvector) e a aplicação (API e CLI) sem instalar PostgreSQL, pgvector nem Python. Uso **só local**: o banco não publica porta e a API só responde em `127.0.0.1`. O mesmo `Dockerfile` e o mesmo `docker-compose.yml` servem para macOS, Windows e Linux (amd64 e arm64). Spec: [.spec/features/F15-conteineres.md](.spec/features/F15-conteineres.md).

**Requisitos**
- **Docker Compose v2** (comando `docker compose`, sem hífen). Desenvolvido com Docker 29.8.2 e Compose 5.5.1.
- macOS: Docker Desktop. Windows 11: Docker Desktop com **WSL 2**. Linux: Docker Engine com o plugin Compose.
- Pelo menos **4 GB de memória** para o Docker e cerca de **8 GB de disco** (imagem 2,2 GB, cache do modelo 4,3 GB e banco). No Docker Desktop o limite se ajusta nas configurações; no WSL 2, em `.wslconfig` (`memory=4GB`).
- **Internet no primeiro uso:** o modelo `BAAI/bge-m3` (cerca de 4,3 GB no volume) é baixado na primeira vetorização e guardado no volume `rag_hfcache`.
- No Docker a vetorização roda **em CPU** (o Docker não expõe o MPS do Mac nem GPU), então PDFs grandes demoram mais.

**1. Configurar o `.env`** (copie de `.env.example` e preencha; o `.env` nunca vai para o Git nem para a imagem):

| Variável | Para quê |
|---|---|
| `ANTHROPIC_API_KEY`, `LLM_MODEL` | Resposta do `ask`. |
| `POSTGRES_PASSWORD` | Senha do `rag_user` no banco do Docker. Obrigatória. Só vale na **primeira** subida do volume (ver "Trocar a senha"). |
| `DOCS_DIR` | Pasta de documentos do computador, montada **somente leitura** em `/data/docs`. Obrigatória. |
| `API_PORT` | Porta da API no computador (padrão `8000`). Mude se já houver algo nela, por exemplo `API_PORT=8001`. |
| `APP_UID`, `APP_GID` | Só no Linux, se o seu usuário não for `1000`: use `id -u` e `id -g` e refaça o `docker compose build`. |

`DATABASE_URL`, `API_HOST` e `HF_HOME` **não** precisam ser mudados: o Compose os define para os contêineres, e o `.env` do uso local continua valendo fora do Docker.

Exemplos de `DOCS_DIR` (use barras `/`, inclusive no Windows):

| Sistema | Exemplo |
|---|---|
| macOS | `DOCS_DIR=/Users/ana/docs` |
| Linux | `DOCS_DIR=/home/ana/docs` |
| Windows | `DOCS_DIR=C:/Users/ana/docs` |

**2. Subir e preparar**

```bash
# macOS / Linux (bash, zsh)
cp .env.example .env            # depois edite o .env
docker compose build
docker compose up -d            # sobe db e api
docker compose run --rm cli init-db
docker compose run --rm cli check
```

```powershell
# Windows (PowerShell)
Copy-Item .env.example .env     # depois edite o .env
docker compose build
docker compose up -d
docker compose run --rm cli init-db
docker compose run --rm cli check
```

**3. Usar.** Os comandos da CLI são os mesmos, com o prefixo `docker compose run --rm cli`. Os **caminhos são os de dentro do contêiner** (`/data/docs/...`), iguais nos três sistemas; o caminho do computador só aparece no `DOCS_DIR`.

```bash
docker compose run --rm cli ingest /data/docs
docker compose run --rm cli search "erro E-5107"
docker compose run --rm cli ask "Como funciona o trabalho remoto?"
docker compose run --rm cli folders
docker compose run --rm cli delete /data/docs/arquivo.pdf     # pede confirmação [s/N]
curl http://127.0.0.1:8000/api/v1/health                       # use a porta do API_PORT
```

Para o `eval`, cadastre os documentos de avaliação que vêm na imagem: `docker compose run --rm cli ingest /app/data/avaliacao` e depois `docker compose run --rm cli eval`.

A base do Docker **começa vazia**: os documentos precisam ser cadastrados de novo, porque a tabela `sources` guarda os caminhos de dentro do contêiner. Migrar uma base do uso local não faz parte desta versão.

**Parar e apagar**

| Comando | Efeito |
|---|---|
| `docker compose down` | Para tudo. **Banco e modelo continuam** nos volumes. |
| `docker compose up -d` | Volta com os mesmos dados, sem baixar o modelo de novo. |
| `docker compose down -v` | Apaga os volumes: **a base e o modelo baixado somem**. |

**Acessar o banco.** O banco não tem porta no computador (e por isso não disputa a 5432 com um PostgreSQL local). Para consultar: `docker compose exec db psql -U rag_user -d rag_training_db`.

**Backup e restauração.** O volume `rag_pgdata` é a **única cópia** dos vetores; o backup é responsabilidade de quem roda o Compose. Os comandos funcionam igual em bash e PowerShell:

```bash
# backup (cria backup.dump na pasta atual)
docker compose exec -T db pg_dump -U rag_user -Fc rag_training_db -f /tmp/backup.dump
docker compose cp db:/tmp/backup.dump ./backup.dump
docker compose exec -T db rm /tmp/backup.dump

# restauração (num banco já inicializado; roda como postgres para recriar a extensão)
docker compose cp ./backup.dump db:/tmp/backup.dump
docker compose exec -T db pg_restore -U postgres -d rag_training_db --clean --if-exists /tmp/backup.dump
docker compose exec -T db rm /tmp/backup.dump
```

Não use `--no-owner` na restauração: as tabelas passariam a pertencer ao `postgres` e o `rag_user` perderia o acesso.

**Trocar a senha.** O `POSTGRES_PASSWORD` só é lido ao criar o volume. Para mudar depois: altere no `.env` **e** rode `docker compose exec db psql -U postgres -c "ALTER ROLE rag_user PASSWORD 'nova-senha'"`, ou apague os volumes com `down -v` (perde a base).

**Problemas comuns**

| Sintoma | Causa e solução |
|---|---|
| `ports are not available ... 8000: address already in use` | Outra coisa usa a porta (por exemplo a API local). Defina `API_PORT=8001` no `.env` e rode `docker compose up -d`. |
| `required variable POSTGRES_PASSWORD is missing` / `DOCS_DIR` | Faltam no `.env`. |
| Processo encerrado com código 137 ao carregar o modelo | Pouca memória para o Docker. Aumente para 4 GB ou mais. |
| `ingest` diz que o arquivo ou a pasta não existe | Foi usado o caminho do computador. Use `/data/docs/...`. |
| No Linux, `ingest` não consegue ler os arquivos | O usuário do contêiner (`APP_UID`/`APP_GID`) não tem permissão de leitura em `DOCS_DIR`. Ajuste os dois valores e rode `docker compose build`. |
| Primeira vetorização demora e baixa muito | É o download do modelo (uma vez só). Sem internet, falha sem gravar nada no banco. |

## Scripts de apoio

Executados com `python -m scripts.<nome>`, não fazem parte da CLI:

| Script | O que faz |
|---|---|
| `check_setup` | Testa uma chamada real ao Claude e carrega o modelo de embeddings, mostrando dimensão, dispositivo e similaridades de exemplo. |
| `read_document <arquivo> [--page N]` | Mostra como um TXT, MD ou PDF é lido, página a página. |
| `chunk_document <arquivo> [--strategy ...] [--max-chars N] [--overlap N]` | Mostra os trechos que uma estratégia gera para um arquivo. |
| `embed_document <arquivo> [--no-db] ...` | Vetoriza os trechos de um arquivo e mostra estatísticas. |
| `compare_chunking` | Compara as quatro estratégias simples de divisão sobre o documento de exemplo. |

## Dados de exemplo
- `data/manual_colaborador.txt`: manual fictício ("Acme Tech") com férias, trabalho remoto, reembolso, suporte de TI (códigos `E-4021` e `E-5107`) e segurança.
- `data/amostras/`: arquivos pequenos e de borda (PDF com e sem texto, corrompido, protegido, Markdown, Latin-1) usados nos roteiros de teste manual.
- `data/avaliacao/`: documentos em português e inglês e `perguntas.json`, usados pelo comando `eval`.

## Desenvolvimento

- Não há testes automatizados. Cada feature tem um **roteiro de teste manual** na sua spec (`.spec/features/`), repetido na regressão.
- Antes de implementar uma feature, a spec precisa ser aprovada.

## Limitações e fora de escopo
- Sem reconhecimento de texto em PDFs escaneados (OCR); outros formatos (Word, planilhas) não são aceitos.
- Sem interface web e sem controle de acesso: todos veem todos os documentos, e a API não tem autenticação.
- Trocar o `EMBEDDING_MODEL` exige reindexar a base inteira; hoje o comando só bloqueia e orienta.
- Os trechos usados na resposta são enviados ao Claude (serviço externo).
