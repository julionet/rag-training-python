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
sql/                     migrações 001 a 003 e setup_admin.sql
scripts/                 scripts de apoio (veja abaixo)
data/
  manual_colaborador.txt   documento de exemplo
  amostras/                arquivos de exemplo e de teste manual
  avaliacao/               documentos e perguntas do comando eval
.spec/                   especificações (negócio, arquitetura, roadmap, features)
```

## Requisitos e instalação

- Python 3.10 ou superior.
- PostgreSQL com a extensão **pgvector** (desenvolvido com PostgreSQL 18.6 e pgvector 0.8.7).
- Chave da API da Anthropic.
- Na primeira execução, o modelo de embeddings é baixado do Hugging Face.

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
- Sem API ou interface web e sem controle de acesso: todos veem todos os documentos.
- Trocar o `EMBEDDING_MODEL` exige reindexar a base inteira; hoje o comando só bloqueia e orienta.
- Os trechos usados na resposta são enviados ao Claude (serviço externo).
