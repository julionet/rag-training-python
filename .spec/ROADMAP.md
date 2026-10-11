# ROADMAP — Ordem de implementação

Documentos relacionados: [NEGOCIO.md](NEGOCIO.md) (o quê e por quê) e [ARQUITETURA.md](ARQUITETURA.md) (como).
Cada feature terá sua especificação em `.spec/features/FNN-nome-curto.md` (ex.: `F05-cadastro-de-documento.md`), sempre criada a partir do template [features/_TEMPLATE.md](features/_TEMPLATE.md).

**Status:** roadmap **aprovado**; **F01–F15 verificadas** (M1 a M5 concluídos; M6 parcial); **F14 (API REST)** verificada (M5); **F15 (Docker)** verificada em 2026-10-11 (M6); **F16 (troca de embedding)** só planejada, sem spec (M6); **F17 (vários provedores de LLM)** só planejada, sem spec (M7); **F18 (servidor MCP)** com spec aprovada em 2026-10-11 e implementação pendente (M8). Veja a tabela "Status das features" no fim deste documento.

## Como trabalharemos (SDD)

Para cada feature, nesta ordem:
1. Copiar `.spec/features/_TEMPLATE.md` para `.spec/features/FNN-nome-curto.md` e preenchê-lo por inteiro (objetivo, escopo, regras de negócio, comportamento, interface, dados, configuração, roteiro de teste manual, impacto, riscos). Seção sem mudanças recebe "Sem mudanças", nunca fica em branco. Dúvidas vão em "Pontos em aberto", sem inventar.
2. **Você aprova a spec.**
3. Implementar apenas o que a spec descreve.
4. Executar o **roteiro de teste manual** da spec (seção 9), repetir os roteiros de regressão (seção 10) e registrar o resultado na seção 14 da spec.
5. Atualizar o status na spec e na tabela de status deste roadmap, e confirmar com você antes da próxima.

Se a implementação revelar algo novo, a spec é atualizada **antes** do código.

**F16 e F17** estão só registradas na documentação (NEGOCIO e ARQUITETURA §16 e §17): a spec de cada uma só é escrita quando o usuário pedir. A **F15** foi implementada e verificada em 2026-10-11 ([features/F15-conteineres.md](features/F15-conteineres.md)). A **F18** tem spec aprovada em 2026-10-11 ([features/F18-servidor-mcp.md](features/F18-servidor-mcp.md)) e implementação pendente.

## Testes: somente manuais

Não haverá testes unitários nem automatizados. Cada spec terá um **roteiro de teste manual** na seção 9 do template (passos, comando e resultado esperado). Ao fechar uma feature, repetimos os roteiros das features anteriores que ela possa ter afetado. Detalhes na seção 14 da ARQUITETURA.

## Estratégia: fatia vertical primeiro

Em vez de construir cada camada inteira, o primeiro marco entrega o caminho completo mais simples (**cadastrar um arquivo e perguntar sobre ele**). Isso valida cedo as decisões de maior risco: PDF, Postgres, busca e resposta. Depois vêm pastas, reindexação, gestão e qualidade.

## Features

| ID | Feature | Objetivo | Regras de negócio | Depende de |
|---|---|---|---|---|
| F01 | **Ambiente e banco de dados** | Banco e usuário criados, extensão vetorial ativa, esquema aplicado, configuração por `.env`, verificação do ambiente. | — | — |
| F02 | **Leitura de documentos (TXT e PDF)** | Ler TXT e PDF página a página (`.md` entra na F13), rejeitar formatos não aceitos e PDF sem texto. | R7, R8 | — |
| F03 | **Divisão em trechos** | Dividir o texto em trechos que preservam seção e página; corrigir as falhas atuais do chunking. | R2 (base para citar página) | F02 |
| F04 | **Vetorização dos trechos** | Gerar os vetores de cada trecho e registrar o modelo usado; bloquear e orientar a reindexar se o modelo mudar. | — | F01, F03 |
| F05 | **Cadastro de documento** | Gravar um documento e seus trechos no banco numa única transação, ignorar duplicados, tratar arquivos grandes com progresso. | R4, R9 | F01–F04 |
| F06 | **Busca de trechos** | Busca que combina significado e palavras exatas, com filtro opcional por pasta. | — | F05 |
| F07 | **Resposta com fontes** | Gerar a resposta só com os trechos recuperados, citar documento e página, e admitir quando não sabe. | R1, R2, R3, R11 | F06 |
| F08 | **Pastas e atualização incremental** | Cadastrar pastas, atualizar só o que mudou, tratar falhas isoladas, remover ausentes só sob pedido. | R5, R6, R7 | F05 |
| F09 | **Gestão da base** | Listar pastas e documentos, remover com confirmação. | R10 | F05, F08 |
| F10 | **CLI e menu interativo** | Comandos diretos e menu numerado que reúnem todas as operações. | — | F06–F09 |
| F11 | **Avaliação de qualidade** | Conjunto de perguntas de teste e métricas para comparar estratégias de divisão e definir parâmetros padrão (tamanho dos trechos, limiar de relevância). | Critérios da seção 6 do NEGOCIO | F06, F07 |
| F13 | **Suporte a Markdown (.md)** | Aceitar `.md` (tipo `md`, migração 002 do `file_type`, `init-db` com várias migrações). Ampliação de F01, F02 e F05. | R4, R7 | F01, F02, F05 |
| F12 | **Limpeza e documentação final** | Remover os módulos, scripts e dados do fluxo antigo (incluindo `data/index/`), manter só o que a aplicação usa e atualizar o `README.md`. | — | Todas |
| F14 | **API REST para execução dos fluxos do RAG** | Um endpoint para cada comando da CLI (`init-db`, `check`, `ingest`, `reindex`, `search`, `ask`, `folders`, `list`, `delete`, `eval`), com request e response em JSON, tarefas assíncronas para as operações longas e **sem autenticação** nesta fase. | R1–R11 (sem regra nova) | F05–F11 |
| F15 | **Contêineres (Dockerfile e Docker Compose)** | Subir banco (PostgreSQL com pgvector) e aplicação (API e CLI) com `docker compose up`, sem instalar PostgreSQL, pgvector nem Python na máquina, **em macOS, Windows e Linux** (amd64 e arm64). **Verificada** (2026-10-11) em macOS Apple Silicon, Windows 11 (WSL 2) e Ubuntu LTS. Requisitos em ARQUITETURA §15. | — | F01, F05–F09; F14 para o serviço `api` |
| F16 | **Troca do modelo de embeddings** | Trocar `EMBEDDING_MODEL` reindexando a base inteira a partir dos trechos já gravados, com confirmação, base consistente e novo limiar medido. **Só planejada: sem spec.** Requisitos em ARQUITETURA §16. | R10 (confirmação) | F04, F08, F11; F14 opcional |
| F17 | **Vários provedores de LLM** | Responder com outros modelos além do Claude: **OpenAI (ChatGPT), Gemini, DeepSeek e Ollama (local)**, além do Claude atual. O provedor padrão vem de `LLM_PROVIDER` e `LLM_MODEL` no `.env`, com `--llm` opcional no `ask`. Só provedores da lista de aprovados (R11 revisada). **Só planejada: sem spec.** Requisitos em ARQUITETURA §17. | R1–R3, R11 (revisada); R15–R17 (propostas) | F07, F11; F14 e F15 integram (opcional) |
| F18 | **Servidor MCP (consulta somente leitura)** | A base passa a ser consultada por clientes MCP (Claude Desktop, Claude Code e outros): ferramentas `search_documents` e `list_sources`, em stdio e em HTTP local (serviço `mcp` no Compose), devolvendo só os trechos com as regras de resposta; o LLM do cliente responde e o RAG não chama o Claude. Só leitura, só local, sem autenticação. **Spec aprovada** (2026-10-11), implementação pendente. Requisitos em ARQUITETURA §18. | R1–R3 (orientadas), R11 (revisada para o MCP), R18–R20 (propostas) | F06, F09, F11, F15 |

### Observações sobre as features
- **Comandos da CLI nascem junto de cada feature** (por exemplo, `ingest` em F05 e `ask` em F07). F10 reúne tudo no menu e na interface final, sem reescrever a lógica.
- **F03 começa com a estratégia estruturada proposta** na ARQUITETURA, mas o tamanho e o padrão definitivos só se decidem em F11, com medição.
- **F08 e F09** separam o "trazer documentos" do "gerenciar a base", para a spec de cada uma ficar curta e verificável.

## Marcos

| Marco | Features | Resultado verificável |
|---|---|---|
| **M1 — Fatia vertical** | F01, F02, F03, F04, F05, F06, F07 | Cadastrar **um** TXT ou PDF e fazer perguntas com resposta, fonte e "não encontrei". |
| **M2 — Base completa** | F08, F09 | Várias pastas cadastradas, atualização incremental, listagem e remoção. |
| **M3 — Uso pela equipe** | F10, F11 | Menu completo e qualidade medida, com parâmetros padrão definidos. |
| **M4 — Encerramento** | F12 | Código legado removido e documentação atualizada. |
| **M5 — API** | F14 | Todas as operações da CLI executáveis por HTTP, com paridade de resultados. |
| **M6 — Operação e evolução** (F15 concluída; falta a F16) | F15, F16 | Subir tudo por Docker Compose com dados e modelo persistentes; trocar o modelo de embeddings com a base consistente e a qualidade medida. |
| **M7 — Múltiplos provedores de LLM** | F17 | Responder com Claude, OpenAI, Gemini, DeepSeek e Ollama, cada um validado com `eval --answers`, sem reindexar a base. |
| **M8 — Acesso por MCP** | F18 | Claude Code e Claude Desktop consultando a base por MCP (stdio e HTTP local), com fonte e página e a frase de "não encontrei" fora do assunto; a base continua só leitura. |

## Decisões pendentes que bloqueiam features

| Decisão | Bloqueia | Observação |
|---|---|---|
| ~~**Busca por palavras em português e inglês.**~~ **Resolvida na F06:** duas colunas (`tsv` português e `tsv_en` inglês), título da seção com peso menor e palavras vazias dos dois idiomas descartadas da pergunta. | F06 | Verificar com documentos nos dois idiomas (roteiro da F06). |
| ~~**Acesso simultâneo da equipe** (duas pessoas atualizando a mesma pasta ao mesmo tempo).~~ **Resolvida na F08:** trava por pasta (lock consultivo do PostgreSQL) que recusa a segunda atualização. | F05, F08 | — |
| ~~**Troca de `EMBEDDING_MODEL`**~~ **Planejada na F16** (sem spec), com as decisões de desenho tomadas em 2026-10-11: estratégia de coluna sombra, comando `reembed --model <novo>`, prefixos por variáveis registradas no banco, consultas liberadas e alterações recusadas durante a troca. Ver ARQUITETURA §16. | F16 | Falta só conferir detalhes na spec (dimensões e prefixos dos modelos de teste, tempo real em CPU). |
| ~~**Docker/Compose.**~~ **Resolvida na F15 (verificada em 2026-10-11)**, com as decisões: uso só local, uma imagem para API e CLI, documentos por `DOCS_DIR`, imagem `pgvector/pgvector:0.8.7-pg18` (tag fixada), versões diretas fixadas, macOS Apple Silicon + Windows 11 (WSL 2) + Ubuntu LTS, modelo em volume de cache. Ver ARQUITETURA §15. | F15 | Conferidos em 2026-10-11: tag `0.8.7-pg18` (amd64 e arm64) e `PGDATA` do PG 18. Backup fica com quem roda o Compose. |
| **Vários provedores de LLM.** Decisões de 2026-10-11: escolha fixa no `.env` com `--llm` opcional; provedores da 1ª versão: Claude, OpenAI, Gemini, DeepSeek e Ollama; privacidade por lista de provedores aprovados; **DeepSeek aprovado** na lista inicial. Os detalhes de cada API (URLs, parâmetros, compatibilidade) serão obtidos **durante a especificação**. Em aberto: qual modelo local usar no Ollama e o orçamento do `eval --answers` por provedor. Ver ARQUITETURA §17. | F17 | **Planejada na F17** (sem spec). |
| **Servidor MCP (F18).** Decisões de 2026-10-11: só leitura, stdio e HTTP local, qualquer cliente MCP, retorno em texto, português por padrão, `mcp==2.3.0`. Em aberto: o suporte real de cada cliente (Claude Code e Claude Desktop em stdio e HTTP; ChatGPT e Gemini de consumo ficam fora desta fase). Ver ARQUITETURA §18. | F18 | Confirmar nos passos 18 a 27 do roteiro da spec. |
| ~~**Limiar de relevância e tamanho dos trechos.**~~ **Resolvida na F11:** limiar 0,50 (cosseno) e trechos de 900/110 caracteres. | F11 | Medidos com o corpus de `data/avaliacao/`. |
| **Limites de tamanho de arquivo e de páginas.** | F05 | Podem ser definidos após medir o tempo real de cadastro em F05. |
| ~~**Idioma da resposta**~~ **Resolvida na F07:** sempre português. | F07 | — |
| ~~**Caminhos aceitos, tarefas e framework da API.**~~ **Resolvida na F14 (spec aprovada):** sem restrição de caminhos (só `127.0.0.1`), tarefas em memória com fila de um trabalhador, FastAPI + Uvicorn, `DELETE` pelo caminho, `/api/v1` e CORS desligado. | F14 | Spec aprovada em 2026-10-10; implementada e verificada em 2026-10-11. |
| **Layout real dos PDFs** (colunas, tabelas, cabeçalhos repetidos). | F02, F03 | Exige amostras de PDFs reais. |

## Fora desta fase (evoluções futuras)

Ordem sugerida, a planejar depois de M4:
1. Interface web para acesso da equipe. (A **API REST** passou a ser planejada na [F14](features/F14-api-rest.md), sem autenticação.)
2. Controle de acesso por pessoa, grupo ou documento, **junto da autenticação da API** (F14, seção 11). Ao especificar F05 e F06, evitaremos decisões de esquema que dificultem isso depois.
3. Reconhecimento de texto em PDFs escaneados.
4. Outros formatos (Word, planilhas).

## Status das features

| ID | Spec | Implementação |
|---|---|---|
| F01 | Aprovada | Verificada (2026-10-02) |
| F02 | Aprovada | Verificada (2026-10-02) |
| F03 | Aprovada | Verificada (2026-10-03) |
| F04 | Aprovada | Verificada (2026-10-03) |
| F05 | Aprovada | Verificada (2026-10-09) |
| F13 | Aprovada | Verificada (2026-10-09) |
| F06 | Aprovada | Verificada (2026-10-09) |
| F07 | Aprovada | Verificada (2026-10-09) |
| F08 | Aprovada | Verificada (2026-10-09) |
| F09 | Aprovada | Verificada (2026-10-10) |
| F10 | Aprovada | Verificada (2026-10-10) |
| F11 | Aprovada | Verificada (2026-10-10) |
| F12 | Aprovada | Verificada (2026-10-10) |
| F14 | Aprovada | Verificada (2026-10-11) |
| F15 | Aprovada (2026-10-11) | Verificada (2026-10-11) |
| F16 | Sem spec (planejada) | Pendente |
| F17 | Sem spec (planejada) | Pendente |
| F18 | Aprovada (2026-10-11) | Pendente |
