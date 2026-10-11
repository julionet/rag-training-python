# F12 — Limpeza e documentação final

| Campo | Valor |
|---|---|
| **Status da spec** | Aprovada |
| **Status da implementação** | Verificada |
| **Marco** | M4 — Encerramento |
| **Depende de** | Todas (F01–F11 e F13, já verificadas) |
| **Regras de negócio** | Nenhuma (não muda comportamento) |
| **Seções da arquitetura** | §2 Decisão, §9 Configuração e dependências, §10 Estrutura alvo, §11 Fases (fase 6) |

## 1. Objetivo
Deixar no projeto **só o que a aplicação usa para executar**: remover o código, os dados e a dependência do fluxo antigo (TXT, numpy, BM25), e reescrever o `README.md` para descrever o fluxo atual (PostgreSQL/pgvector, CLI, menu, `ask`, `eval`). Não há mudança de comportamento para quem usa a CLI.

## 2. Escopo

**Inclui**
- Remover os módulos antigos de `src/`: `vector_store.py`, `lexical_search.py`, `fusion.py`, `rag.py` e `hybrid_rag.py`.
- Remover de `src/generation.py` o que só o código antigo usava: `build_user_prompt` e `Generator.answer`.
- Remover de `src/chunking.py` a constante `_MAX_SECTION_LEVEL` (definida e nunca usada).
- Remover `rank-bm25` do `requirements.txt`.
- Remover 6 scripts que dependem do código antigo: `scripts/ask.py`, `ask_hybrid.py`, `build_index.py`, `compare_methods.py`, `compare_search.py` e `semantic_search.py`.
- Remover `data/index/` (`texts.json` e `vectors.npy`) e `data/manual_colaborador_novo.txt`.
- Reescrever o `README.md` por inteiro.
- Atualizar `ARQUITETURA.md`, `ROADMAP.md`, `CLAUDE.md` e notas nas specs antigas (seção 12).

**Não inclui** (fica para outra feature ou fora de escopo)
- Qualquer mudança de comportamento da CLI, do menu, do `ask`, do `search`, do `eval` ou do banco.
- Alterar os scripts que ficam (`check_setup.py`, `compare_chunking.py`, `read_document.py`, `chunk_document.py`, `embed_document.py`), inclusive o `check_setup.py`, que permanece **como está**.
- Reescrever os 6 scripts removidos sobre o código novo (a função deles já existe na CLI).
- Remover amostras de `data/amostras/`, `data/avaliacao/`, `data/manual_colaborador.txt`, `sql/` ou a pasta `.spec/`.
- Mexer em `data/amostras/real.pdf` e `grande.pdf` (locais, ignorados pelo Git).
- Evoluções futuras: API/web, controle de acesso, OCR, outros formatos e a troca de `EMBEDDING_MODEL`.

## 3. Regras de negócio aplicáveis

| Regra | O que significa nesta feature |
|---|---|
| R1–R11 | Nenhuma muda. A limpeza **não pode** alterar o comportamento verificado nas features anteriores; a regressão (seção 10) comprova isso. |

**Regras técnicas**
- **T1.** Só se remove o que **nenhum código vivo** usa. Antes de cada remoção, conferir por busca que nada em `src/` (exceto os módulos removidos) nem nos scripts que ficam o importa.
- **T2.** `Generator.answer_hits`, `build_context_prompt`, `SYSTEM_PROMPT`, `NOT_FOUND_ANSWER`, `GeneratedAnswer` e `GenerationError` **ficam** (usados por `ask` e `eval`). O `Generator.__init__` não muda.
- **T3.** As estratégias `fixed_size_chunks`, `sentence_chunks`, `recursive_chunks` e `semantic_chunks` **ficam** (o `eval` e os scripts que ficam as usam). `Embedder.embed` também fica (usado por `embed_chunks`).
- **T4.** As sete dependências do `requirements.txt` que o código usa (`anthropic`, `sentence-transformers`, `numpy`, `python-dotenv`, `psycopg[binary]`, `pymupdf4llm`, `pgvector`) **ficam**; só `rank-bm25` sai.
- **T5.** Removido do disco e do Git (`git rm`); o histórico do Git é o registro do que existia.
- **T6.** Documentos históricos (specs F01–F11, seções 9 e 14) **não são reescritos**; recebem, no máximo, uma nota curta onde citam algo removido (seção 12).
- **T7.** Os 5 scripts que ficam **não mudam**. Se um deles quebrar por causa da remoção, a causa é um erro desta feature e deve ser corrigida na spec antes do código.

## 4. Comportamento esperado

### 4.1 Fluxo principal
1. Conferir por busca (T1) que nada vivo usa o que será removido.
2. Remover os arquivos e os trechos de código da seção 2.
3. Remover `rank-bm25` do `requirements.txt`.
4. Reescrever o `README.md` (seção 5.1).
5. Atualizar a documentação da seção 12.
6. Executar o roteiro da seção 9 e a regressão da seção 10.

### 4.2 Fluxos alternativos e erros

| Situação | Comportamento esperado | Mensagem / saída |
|---|---|---|
| A busca encontra um uso vivo de algo a remover | Não remover. Registrar na seção 11 e perguntar à pessoa. | — |
| Script que fica quebra depois da remoção | Parar, atualizar a spec e perguntar (T7). | — |
| `pip install -r requirements.txt` falha sem `rank-bm25` | Parar e investigar; alguém ainda importa `rank_bm25`. | — |

### 4.3 Saída para a pessoa
Sem saída nova. O resultado visível é o projeto mais enxuto:
```
src/            16 módulos (antes 21)
scripts/        5 arquivos (antes 11)
data/           manual_colaborador.txt, amostras/, avaliacao/   (sem index/ e sem manual_colaborador_novo.txt)
requirements    7 pacotes (antes 8)
```

## 5. Interface

**Comandos / opções da CLI**: sem mudanças. Nenhum comando é criado, alterado ou removido.

**Módulos e funções**

| Arquivo | O que acontece | Funções / classes |
|---|---|---|
| `src/vector_store.py` | Removido | `VectorStore` |
| `src/lexical_search.py` | Removido | `LexicalSearch`, `tokenize`, `STOPWORDS_PT` |
| `src/fusion.py` | Removido | `weighted_fusion`, `reciprocal_rank_fusion` |
| `src/rag.py` | Removido | `RAGPipeline` |
| `src/hybrid_rag.py` | Removido | `HybridRAGPipeline` |
| `src/generation.py` | Remove `build_user_prompt` e `Generator.answer` | O resto permanece (T2) |
| `src/chunking.py` | Remove `_MAX_SECTION_LEVEL` | O resto permanece (T3) |
| `scripts/` | Remove `ask.py`, `ask_hybrid.py`, `build_index.py`, `compare_methods.py`, `compare_search.py`, `semantic_search.py` | Ficam os 5 da seção 2 |

### 5.1 Estrutura do novo `README.md`
Em português, direto e curto:
1. **O que é**: aplicação de estudo de RAG; cadastra TXT, MD e PDF com texto, busca em PostgreSQL/pgvector e responde com fontes pelo Claude.
2. **Arquitetura**: diagrama curto do fluxo (cadastro: leitura → trechos → vetores → banco; consulta: pergunta → busca híbrida em SQL → limiar → Claude → resposta com fontes).
3. **Requisitos e instalação**: Python, PostgreSQL com pgvector, ambiente virtual, `pip install -r requirements.txt`, `.env` a partir do `.env.example`, preparo do banco (`sql/setup_admin.sql`) e `init-db`.
4. **Configuração (`.env`)**: `ANTHROPIC_API_KEY`, `LLM_MODEL`, `EMBEDDING_MODEL`, `HF_TOKEN`, `DATABASE_URL`, `RELEVANCE_THRESHOLD`.
5. **Uso**: tabela de comandos (`init-db`, `check`, `ingest`, `reindex`, `search`, `ask`, `eval`, `folders`, `list`, `delete`) e o menu interativo.
6. **Estrutura do projeto**: `src/`, `scripts/` (os 5), `sql/`, `data/`, `.spec/`.
7. **Scripts de apoio**: uma linha por script que fica.
8. **Dados de exemplo**: `manual_colaborador.txt`, `data/amostras/` e `data/avaliacao/`.
9. **Desenvolvimento**: método SDD (`.spec/`), sem testes automatizados, roteiros manuais.
10. **Limitações e fora de escopo**: sem OCR, sem API/web, sem controle de acesso, troca de `EMBEDDING_MODEL` exige reindexar.

Não repetir a descrição módulo a módulo do README antigo; os detalhes técnicos ficam em `.spec/ARQUITETURA.md`.

## 6. Dados
Sem mudanças de esquema. Remove-se `data/index/` (arquivos locais do índice antigo) e `data/manual_colaborador_novo.txt`. O banco e as migrações **não são tocados**.

## 7. Configuração
Sem variáveis novas. O `.env.example` não muda. O `.gitignore` não muda.

| Parâmetro | Padrão | Onde se define |
|---|---|---|
| (nenhum novo) | — | — |

## 8. Dependências externas
- Sai `rank-bm25` do `requirements.txt`. Nenhum pacote novo.
- Para a regressão: banco com os documentos de `data/` e `data/avaliacao/` cadastrados, `.env` completo, serviço do Claude acessível.

## 9. Critérios de aceite — roteiro de teste manual

**Pré-condições:** ambiente virtual ativo; comandos na raiz; banco com `manual_colaborador.txt`, `data/amostras/` (guia, remote_policy, injecao, com_texto) e `data/avaliacao/` cadastrados; `.env` com `ANTHROPIC_API_KEY`, `LLM_MODEL`, `EMBEDDING_MODEL` e `DATABASE_URL`. Antes de remover, executar o passo 1 para ter a lista de usos.

| # | Passo | Comando / ação | Resultado esperado |
|---|---|---|---|
| 1 | Nenhum uso vivo (antes) | `grep -rnE "vector_store\|lexical_search\|hybrid_rag\|fusion\|rank_bm25\|RAGPipeline\|build_user_prompt\|\.answer\(" src scripts` | Ocorrências **só** nos arquivos a remover e no corpo de `Generator.answer`. Qualquer outra interrompe a feature (4.2). |
| 2 | Arquivos removidos | `ls src scripts data` | `src/` sem os 5 módulos antigos; `scripts/` com só `check_setup.py`, `compare_chunking.py`, `read_document.py`, `chunk_document.py`, `embed_document.py`; `data/` sem `index/` e sem `manual_colaborador_novo.txt`. |
| 3 | Nada sobrou referenciando | O mesmo `grep` do passo 1, mais `grep -rnE "data/index\|manual_colaborador_novo\|rank-bm25" . --exclude-dir=.venv --exclude-dir=.git --exclude-dir=.spec` | Sem nenhuma ocorrência (as specs em `.spec/` podem citar como histórico). |
| 4 | Importação sem efeitos | `python -c "import src.cli, src.answer_service, src.evaluation_service, src.menu"` | Sem saída e sem erro. |
| 5 | Dependências | Em um ambiente virtual novo: `pip install -r requirements.txt`; depois o passo 4 | Instala sem `rank-bm25` e o passo 4 passa. |
| 6 | Geração enxuta | `python -c "from src.generation import Generator, build_context_prompt, NOT_FOUND_ANSWER; print(hasattr(Generator,'answer'), hasattr(Generator,'answer_hits'))"` | Imprime `False True`. |
| 7 | `check` | `python -m src.cli check` | Ambiente OK; código 0. |
| 8 | `search` | `python -m src.cli search "posso trabalhar de casa?" --folder $(pwd)/data` | Trechos com arquivo, página e seção, como na F06. |
| 9 | `ask` | `python -m src.cli ask "o que significa o erro E-5107?" --folder $(pwd)/data` | Resposta com fonte do trecho de Suporte de TI. |
| 10 | `ask` fora do assunto | `ask "qual a capital da França?" --folder $(pwd)/data` | Frase padrão, sem chamar o Claude (limiar da F11). |
| 11 | `eval` | `python -m src.cli eval --strategies structured --max-chars 900` | Tabelas de recuperação e do limiar, como na F11; base real intacta. |
| 12 | Menu | `python -m src.cli` em terminal interativo, opção 7 e opção 5 (uma pergunta) e 0 | O menu abre, o `check` e a pergunta funcionam, e sai sem erro. |
| 13 | Gestão da base | `python -m src.cli folders` e `python -m src.cli list --folder $(pwd)/data/amostras` | Listagens normais. |
| 14 | Scripts que ficam | `python -m scripts.read_document data/amostras/guia.md`, `python -m scripts.chunk_document data/amostras/guia.md`, `python -m scripts.compare_chunking` | Os três executam sem erro de importação. |
| 15 | `embed_document` e `check_setup` | `python -m scripts.embed_document data/amostras/guia.md --no-db` e `python -m scripts.check_setup` | Executam sem erro de importação (o `check_setup` faz uma chamada real ao Claude e carrega o modelo). |
| 16 | README | Ler o `README.md` e seguir só a seção de instalação e uso rápido, com os comandos copiados | Cada comando citado existe (`--help`) e a estrutura descrita bate com `ls`. |
| 17 | Links e menções | Conferir no README e na ARQUITETURA que nenhum arquivo citado foi removido | Sem menção a módulo ou script que não existe mais, salvo notas históricas explícitas. |
| 18 | Somente o previsto | `git status` | Só remoções previstas (seção 2), `requirements.txt`, `README.md`, `src/generation.py`, `src/chunking.py` e os documentos da seção 12. |

**Consultas úteis para conferir o banco** (se aplicável)
```sql
SELECT count(*) FROM documents;
SELECT count(*) FROM chunks;
```
(Os valores antes e depois da feature devem ser iguais: a F12 não toca no banco.)

## 10. Impacto em outras features

| Feature | Roteiros a repetir (#) | Motivo |
|---|---|---|
| F01 | `check` e `init-db` | A importação de `src.config`/`src.db` não pode ter sido afetada. |
| F02, F03, F04 | Roteiro dos scripts de apoio (`read_document`, `chunk_document`, `embed_document`) e do `chunking` | Esses scripts ficam e `chunking.py` perdeu uma constante. |
| F05, F08 | `ingest` de um arquivo e de uma pasta; `reindex` | Confirma que o cadastro não dependia do código removido. |
| F06 | 3, 4, 6 | `search` sobre a base atual. |
| F07 | Os passos de 1 a 8 e 17 a 22 (**exceto o 31**: o legado deixa de existir) | `generation.py` mudou. O passo 31 ("Legado intacto") passa a **não se aplicar**: registrar na seção 14. |
| F09 | `folders`, `list` | Gestão da base. |
| F10 | Menu e modo conversa | O menu usa `run_ask` e `EmbedderCache`. |
| F11 | 1, 2, 13 | `eval` e `ask` com limiar. |
| F13 | `ingest` de um `.md` | Tipo `md`. |

## 11. Riscos e decisões

**Decisões tomadas** (confirmadas pela pessoa em 2026-10-10)
- Remover o código antigo e deixar só o que a aplicação usa (T1).
- **`data/index/` é removido.** Isso **revoga a decisão anterior** de mantê-lo (CLAUDE.md, ROADMAP e ARQUITETURA); os três documentos são atualizados.
- `data/manual_colaborador_novo.txt` é removido (sem referência em nenhum lugar).
- `data/manual_colaborador.txt` e **todas** as amostras de `data/amostras/` ficam (base dos roteiros manuais, já que não há testes automatizados).
- Dos 11 scripts, ficam os **5 que funcionam sem o código antigo**; os 6 que dependem dele saem. O `check_setup.py` fica **como está**.

**Decisões tomadas por mim, a confirmar na aprovação**
- **Remover `fusion.py`.** A ARQUITETURA listava só 4 módulos, mas só o `hybrid_rag.py` usava o `fusion.py` (a F06 já dizia que ele "continua até a F12").
- **Remover `build_user_prompt` e `Generator.answer`** de `generation.py`; só o `rag.py` e o `hybrid_rag.py` as usavam.
- **Remover `_MAX_SECTION_LEVEL`** de `chunking.py`: constante definida e nunca usada (encontrada por busca).
- **README novo em vez de editado**, porque o antigo descreve só o fluxo antigo.
- **Specs históricas não são reescritas**, só ganham notas curtas (T6).
- **Sem alterar `.gitignore`:** `real.pdf` e `grande.pdf` continuam ignorados e locais.

**Riscos aceitos**
- Sem testes automatizados, uma remoção pode quebrar algo que a busca por texto não achou (importação dinâmica). Mitigação: os passos 4, 5 e 7 a 15 e a regressão da seção 10.
- Os 5 scripts mantidos ficam sem outro uso além do apoio aos roteiros e do estudo; podem sair em uma limpeza futura.
- O índice antigo (`data/index/`) deixa de existir no disco; só o histórico do Git o guarda.
- O passo 31 da F07 e roteiros que citam os scripts removidos deixam de ser repetíveis. Isso é registrado, não corrigido.

**Pontos em aberto** (precisam de resposta antes de implementar)
- Nenhum, além das decisões da lista "a confirmar na aprovação".

## 12. Documentação a atualizar
- `README.md`: reescrito (seção 5.1).
- `.spec/ARQUITETURA.md`: §2 (tabela "Hoje / Evolução" passa a passado), §9 (sem `rank-bm25`), §10 (estrutura real, sem `pipeline.py` nem `scripts/experiments/`), §11 (fase 6 concluída, `data/index/` removido), §13 ("Resolvidos": `data/index/` removido, revogando a decisão anterior).
- `.spec/ROADMAP.md`: F12 (spec e implementação), M4, e a frase "manter `data/index/`" na tabela de features.
- `.claude/CLAUDE.md`: acrescentar a F12 ao "implementada e verificada" e trocar "`data/index/` e `data/manual_colaborador.txt` **não são removidos**" por "`data/manual_colaborador.txt` **não é removido** (`data/index/` foi removido na F12)".
- Notas curtas nas specs que citam o removido: F03 (linha dos roteiros do código atual), F06 (`fusion.py`), F07 (passo 31 e a menção a `rag.py`/`hybrid_rag.py`), F02/F03/F04 (scripts "podem sair na F12": agora ficam).
- `.env.example`: sem mudanças.

## 13. Definição de pronto
- [x] Spec aprovada pela pessoa responsável
- [x] Código implementado somente no que a spec descreve
- [x] Todos os passos do roteiro (seção 9) executados e aprovados
- [x] Roteiros de regressão (seção 10) repetidos
- [x] Documentação da seção 12 atualizada
- [x] Status atualizado nesta spec e no ROADMAP

## 14. Registro de verificação

| Data | Quem executou | Resultado | Observações / falhas encontradas |
|---|---|---|---|
| 2026-10-10 | Claude (pré-verificação na implementação) | Passos executados abaixo | Aguarda execução e aprovação da pessoa. **Removido:** 5 módulos de `src/` (`vector_store`, `lexical_search`, `fusion`, `rag`, `hybrid_rag`), 6 scripts, `data/index/`, `data/manual_colaborador_novo.txt`, `build_user_prompt` e `Generator.answer` de `generation.py`, `_MAX_SECTION_LEVEL` de `chunking.py` e `rank-bm25` do `requirements.txt`. **Executados e conformes:** 1 (busca antes de remover: usos só nos arquivos a remover e em `Generator.answer`); 2 (`src/` com 16 módulos, `scripts/` com os 5, `data/` com `manual_colaborador.txt`, `amostras/` e `avaliacao/`); 3 (sem ocorrências fora de `.spec/`, salvo a frase do `CLAUDE.md` que registra a revogação da decisão sobre `data/index/`); 4 (importações); 6 (`Generator` sem `answer` e com `answer_hits`: `False True`); 7 (`check` OK); 8 (`search`); 9 (`ask` do E-5107 com fonte); 10 (`ask` fora do assunto com chave inválida: frase padrão, sem 401); 11 (`eval`: mesmas métricas da F11, `rrf` hit@1 0,94 e `semantic` 1,00); 13 (`folders` e `list`); 14 (`read_document`, `chunk_document` e `compare_chunking`); 15 (`embed_document --no-db` e `check_setup`, com chamada real ao Claude); 16 (todos os comandos do README respondem a `--help` e os 5 scripts existem); 17 (ARQUITETURA e README sem menção a removidos, salvo notas históricas); 18 (`git status` só com o previsto). Base real igual antes e depois: 141 documentos, 4858 trechos e 6 pastas. **Não executados:** 5 (instalação em ambiente virtual novo; fiz só `pip install --dry-run -r requirements.txt` no ambiente atual, que resolve sem `rank-bm25`), 12 (menu: exige terminal interativo), regressão de F05/F08 (`ingest` e `reindex`), F10 (modo conversa) e F13 (`ingest` de `.md`). **Observação (resolvida depois):** o cabeçalho da ARQUITETURA já indica "implementada e verificada (F01–F13)" e a tabela da §2 está rotulada como histórico ("Antes (removido na F12)"); nenhuma alteração pendente. |
| 2026-10-10 | Jose Julio | Aprovado | Implementação e roteiro da seção 9 aprovados, conforme relato da pessoa. |
