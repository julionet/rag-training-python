# F11 — Avaliação de qualidade

| Campo | Valor |
|---|---|
| **Status da spec** | Aprovada |
| **Status da implementação** | Verificada |
| **Marco** | M3 — Uso pela equipe |
| **Depende de** | F03 (`chunk_pages`, estratégias), F04 (`Embedder`, `embed_chunks`), F06 (`search`, `SearchHit`), F07 (`run_ask`) |
| **Regras de negócio** | R3 (admitir quando não sabe), R2 (fonte certa); critérios da seção 6 do NEGOCIO |
| **Seções da arquitetura** | §5 Chunking (avaliação), §6 (busca híbrida), §7 Geração (limiar), §13 Pontos a confirmar, §14 Testes |

## 1. Objetivo
A pessoa responsável pela base consegue **medir** a qualidade da recuperação com um conjunto fixo de perguntas de teste, comparar estratégias e tamanhos de trecho, e **definir com números** os padrões que hoje estão em aberto: tamanho dos trechos e limiar mínimo de relevância. O limiar passa a valer no `ask`.

## 2. Escopo

**Inclui**
- Conjunto versionado de perguntas de teste (`data/avaliacao/perguntas.json`), com perguntas **com** e **sem** resposta, em português e inglês.
- Documentos de avaliação novos em `data/avaliacao/`, mais longos que as amostras atuais, para que estratégias e tamanhos de trecho se diferenciem (ver seção 11).
- Comando `python -m src.cli eval` que:
  - compara estratégias (`structured`, `recursive`, `sentence`, `fixed`, `semantic`) e tamanhos de trecho, por **hit rate@k** e **MRR**, **sem tocar na base real** (tabelas temporárias);
  - compara os métodos de busca (`rrf`, `semantic`, `lexical`);
  - mede a similaridade do melhor trecho em perguntas com e sem resposta e **propõe o limiar**;
  - com `--answers`, roda o `ask` real nas perguntas e confere fonte e "não encontrei" (consome a cota do Claude).
- **Aplicar o limiar no `ask`** (ajuste na F07): abaixo dele, responde "não encontrei" sem chamar o Claude.
- Fixar os padrões medidos (`MAX_CHARS`, `OVERLAP_CHARS`, limiar) e registrar os números na seção 14.

**Não inclui** (fica para outra feature ou fora de escopo)
- Testes automatizados (continuam só manuais; o `eval` é uma **ferramenta de medição**, não uma suíte de testes).
- Avaliação com documentos reais da pessoa (o conjunto é o versionado em `data/`; ver seção 11).
- Reranking, reformulação de pergunta e outros ganhos de qualidade.
- Troca de `EMBEDDING_MODEL` e comparação entre modelos de embeddings.
- Menu interativo para o `eval` (ferramenta de manutenção, só CLI).
- Remover módulos legados (F12), inclusive `scripts/compare_chunking.py` e afins.

## 3. Regras de negócio aplicáveis

| Regra | O que significa nesta feature |
|---|---|
| R3 | O limiar é o que faz perguntas fora dos documentos receberem "não encontrei" **sem** gastar uma chamada ao Claude. O `eval --answers` confere que o Claude também admite quando não sabe. |
| R2 | O `eval --answers` confere que a fonte citada é o documento certo. |
| NEGOCIO §6 | "Respostas corretas, com fonte" e "Admite quando não sabe" passam a ter números reproduzíveis. |

**Regras técnicas**
- **T1.** O `eval` **nunca escreve** nas tabelas reais (`documents`, `chunks`, `sources`, `app_meta`). Os trechos de teste vivem em tabelas temporárias `chunks` e `documents` da própria conexão (que escondem as reais), descartadas ao fim por `ROLLBACK`.
- **T2.** A recuperação medida é a **mesma** de produção: `src.retrieval.search`, sem cópia da consulta SQL.
- **T3.** Um trecho **acerta** uma pergunta se o `filename` é o esperado **e** o conteúdo contém o texto-chave esperado (comparação sem diferenciar maiúsculas, acentos nem espaços repetidos). A página é conferida só quando a pergunta a informa.
- **T4.** Métricas, para as perguntas **com** resposta, sobre os `top_k` trechos (padrão 5):
  - `hit@1`, `hit@3`, `hit@top_k`: fração de perguntas com ao menos um acerto até aquela posição;
  - `MRR`: média de `1 / posição do primeiro acerto` (0 se não houver).
- **T5.** Perguntas **sem** resposta não entram no hit rate. Para elas, registra-se a similaridade de cosseno do melhor trecho (`semantic_score` máximo).
- **T6.** **Limiar proposto:** tabela de candidatos de 0,30 a 0,80 (passo 0,05) com (a) % das perguntas **com** resposta cujo melhor trecho **passa** e (b) % das perguntas **sem** resposta **barradas**. Proposta: o **maior** candidato que mantém pelo menos **95%** das perguntas com resposta. A pessoa confirma o valor.
- **T7.** O limiar atua só nos métodos `semantic` e `rrf`, sobre `semantic_score`: um trecho é relevante se tem `semantic_score ≥ limiar`. Em `lexical` não há similaridade e o limiar **não se aplica**. *(Ajuste de 2026-10-10: a regra "1º da busca textual conta" foi retirada; na primeira medição ela deixava 3 das 6 perguntas sem resposta passarem em qualquer limiar.)*
- **T8.** A avaliação compara configurações sobre o **mesmo** conjunto de documentos e perguntas. Cada configuração é (estratégia, `max_chars`); `overlap_chars` acompanha `max_chars` na proporção do padrão atual (110/900, ≈ 12%).
- **T9.** O modelo de embeddings é carregado **uma vez** (`Embedder`/`EmbedderCache`) e só se houver método vetorial. O `eval` respeita a conferência do modelo registrado em `app_meta` (F04): se divergir, erro igual ao da busca.
- **T10.** Importar `src.evaluation` não conecta ao banco nem carrega o modelo.

## 4. Comportamento esperado

### 4.1 Fluxo principal
1. A pessoa executa `python -m src.cli eval`.
2. A aplicação lê `data/avaliacao/perguntas.json` e confere que os documentos listados existem.
3. Divide cada documento com cada configuração, vetoriza (uma vez por configuração) e grava nas tabelas temporárias (T1).
4. Para cada configuração, executa `search` em cada pergunta e calcula as métricas (T4), por método.
5. Imprime a tabela comparativa e, em separado, a análise do limiar (T6).
6. Com `--answers`, roda `run_ask` em cada pergunta sobre a **base real** e imprime o resultado.
7. Descarta as tabelas temporárias. Nada é gravado.

### 4.2 Fluxos alternativos e erros

| Situação | Comportamento esperado | Mensagem / saída |
|---|---|---|
| Arquivo de perguntas inexistente ou JSON inválido | Erro. Código 1. | `Arquivo de perguntas inválido: <motivo>.` |
| Pergunta sem `id`, `pergunta` ou com `esperado` mal formado | Erro apontando o `id`/posição. Código 1. | `Pergunta <id>: <campo> ausente ou inválido.` |
| Documento listado que não existe | Erro antes de qualquer trabalho caro. Código 1. | `Documento não encontrado: <caminho>.` |
| Documento recusado pelo `loaders` (formato, sem texto) | Erro. Código 1. | Mensagem da F02 |
| `--strategies` com valor desconhecido | Erro do `argparse`. Código 2. | Mensagem do `argparse` |
| `--max-chars`/`--top-k` ≤ 0 | Erro do `argparse`. Código 2. | Mensagem do `argparse` |
| Modelo de embeddings divergente do registrado | Erro da F04. Código 1. | Mensagem da F04 |
| Banco indisponível ou sem `init-db` | Erro da F01. Código 1. | Mensagens existentes |
| `--answers` sem `ANTHROPIC_API_KEY`/`LLM_MODEL` | Erro antes de qualquer trabalho. Código 1. | Mensagens da F07 |
| `--answers` com a base real sem os documentos de avaliação | Aviso e pergunta marcada `sem base`; nenhuma chamada ao Claude para ela. | `Documento não cadastrado na base: <arquivo>. Cadastre com: python -m src.cli ingest data/avaliacao` |
| Estratégia `semantic` | Usa o mesmo modelo do `Embedder` (mais lenta, só com o corpus pequeno). | — |
| `Ctrl+C` | Interrompe sem traceback e descarta as tabelas temporárias. Código 1. | `Avaliação interrompida.` |

### 4.3 Saída para a pessoa
```
$ python -m src.cli eval
Perguntas: 24 (18 com resposta, 6 sem) | Documentos: 9 | top-k 5

Recuperação (método rrf)
estratégia   max_chars  trechos   hit@1  hit@3  hit@5   MRR
structured          500       61   0,67   0,89   0,94  0,78
structured          900       38   0,72   0,89   0,94  0,81
...

Por método (estratégia structured, max_chars 900)
método      hit@1  hit@3  hit@5   MRR
rrf          0,72   0,89   0,94  0,81
semantic     0,67   0,83   0,89  0,76
lexical      0,50   0,67   0,72  0,58

Limiar de relevância (cosseno do melhor trecho, structured 900)
limiar   com resposta que passam   sem resposta barradas
0,45                      100%                    33%
0,50                       94%                    67%
...
Proposta: 0,50 (maior valor que mantém ≥ 95% das perguntas com resposta).
Tempo: 41 s
```
Com `--answers`:
```
Respostas (ask real, método rrf, limiar 0,50)
id   resultado
q01  ok (fonte: manual_colaborador.txt, p. 1)
q19  ok (não encontrei, sem chamar o Claude)
q21  FALHA (respondeu com informação; esperado "não encontrei")
Resumo: 23/24 corretas | chamadas ao Claude: 17
```
- Valores acima são ilustrativos; os reais são registrados na seção 14.
- Erros em `stderr`, sem traceback. Tabelas em `stdout`.

## 5. Interface

**Comandos / opções da CLI**

| Comando | Argumentos e opções | Descrição |
|---|---|---|
| `python -m src.cli eval` | `[--questions <arquivo>]` `[--strategies a,b,…]` `[--max-chars N,N,…]` `[--methods rrf,semantic,lexical]` `[--top-k N]` `[--answers]` | Avalia recuperação e limiar (4.3). Padrões: `--questions data/avaliacao/perguntas.json`; estratégias `structured,recursive,sentence,fixed` (`semantic` só se pedida); `--max-chars 500,900,1400`; os três métodos; `--top-k 5`. |
| `python -m src.cli ask` | (sem mudança de opções) | Passa a aplicar o limiar (T7, seção 6.1). |
| `python -m src.cli check` | (sem mudança) | Sem alteração. |

Sem item de menu.

**Módulos e funções**

| Arquivo | Responsabilidade | Funções / classes |
|---|---|---|
| `src/evaluation.py` | Carrega perguntas, monta as tabelas temporárias, calcula métricas e a análise do limiar. | `load_questions(path) -> EvalSet`; `Question(id, text, language, expected)`; `evaluate_retrieval(conn, embedder, eval_set, strategy, max_chars, methods, top_k) -> RetrievalReport`; `threshold_table(with_answer, without_answer, method) -> list[ThresholdRow]` (recebe os trechos de cada pergunta e usa `passes_relevance`); `suggest_threshold(rows) -> float`; `is_hit(hit, expected) -> bool`; `EvaluationError` |
| `src/evaluation_service.py` | Orquestra o comando: valida, conecta, roda as configurações, e o `--answers`. | `run_eval(...) -> EvalOutcome` |
| `src/cli.py` | Subcomando `eval` e formatação das tabelas. | `cmd_eval(args)` |
| `src/retrieval.py` | Regra de relevância (só similaridade) compartilhada pelo `eval` e pelo `ask` (T7). | `passes_relevance(hits, method, threshold) -> bool` |
| `src/answer_service.py` | Aplica o limiar antes de chamar o Claude. | ajuste em `run_ask` (6.1) |
| `src/config.py` | Lê `RELEVANCE_THRESHOLD`. | `RELEVANCE_THRESHOLD` |
| `src/chunking.py` | Padrões `MAX_CHARS`/`OVERLAP_CHARS` ajustados **só se** a medição indicar. | constantes |

### 5.1 Formato de `data/avaliacao/perguntas.json`
```json
{
  "documentos": ["data/manual_colaborador.txt", "data/avaliacao/politica_viagens.md"],
  "perguntas": [
    {
      "id": "q01",
      "pergunta": "posso trabalhar de casa?",
      "idioma": "pt",
      "esperado": [
        {"arquivo": "manual_colaborador.txt", "texto": "modelo híbrido", "pagina": 1}
      ]
    },
    {"id": "q19", "pergunta": "qual a capital da França?", "idioma": "pt", "esperado": []}
  ]
}
```
- `esperado` vazio = **pergunta sem resposta** nos documentos.
- `texto` é um trecho **curto e literal** (até ~60 caracteres) que identifica a informação; `pagina` é opcional.
- `documentos` define o corpus da avaliação (caminhos relativos à raiz do projeto).

## 6. Dados
Sem mudanças (nenhuma tabela, coluna ou migração permanente). As tabelas temporárias `chunks` e `documents` são criadas com `CREATE TEMP TABLE … (LIKE … INCLUDING DEFAULTS INCLUDING GENERATED)`, **sem** índices (busca vetorial exata) e **sem** chaves estrangeiras, e somem no `ROLLBACK`.

### 6.1 Limiar no `ask`
Em `run_ask`, depois da busca e antes de chamar o Claude:
- métodos `semantic` e `rrf`: se **nenhum** trecho tem `semantic_score ≥ RELEVANCE_THRESHOLD`, responde `NOT_FOUND_ANSWER`, **sem chamar o Claude** e sem o aviso de envio (R11), código 0 (igual ao T3 da F07);
- método `lexical`: sem alteração;
- `RELEVANCE_THRESHOLD` ausente ou `0`: sem limiar (comportamento atual da F07).
- Os trechos enviados ao Claude **não** são filtrados: o limiar só decide se há chamada ou não.

## 7. Configuração

| Parâmetro | Padrão | Onde se define |
|---|---|---|
| `RELEVANCE_THRESHOLD` | **0,50** (definido na verificação, aprovado pela pessoa); vazio = sem limiar | `.env` / `.env.example`; padrão em `src/config.py` |
| `MAX_CHARS` / `OVERLAP_CHARS` | 900 / 110 (**mantidos** após a medição) | `src/chunking.py` |
| `--top-k` do `eval` | 5 | Opção do comando |
| Candidatos de limiar | 0,30 a 0,80, passo 0,05 | Constante em `src/evaluation.py` |
| Critério da proposta | ≥ 95% das perguntas com resposta mantidas | Constante em `src/evaluation.py` |

## 8. Dependências externas
- Nenhum pacote novo (JSON da biblioteca padrão).
- Documentos de avaliação **novos** em `data/avaliacao/` (a criar na implementação, revisados pela pessoa): de 4 a 6 arquivos `.md`/`.txt`, com PT e EN, seções longas, tabelas e códigos, totalizando algumas dezenas de KB.
- Amostras existentes reaproveitadas: `data/manual_colaborador.txt`, `data/amostras/guia.md`, `data/amostras/remote_policy.md`, `data/amostras/injecao.txt`, `data/amostras/com_texto.pdf`.
- Para `--answers`: serviço do Claude acessível, chave e modelo válidos, e os documentos de avaliação cadastrados na base real.

## 9. Critérios de aceite — roteiro de teste manual

**Pré-condições:** ambiente virtual ativo; comandos na raiz; `init-db` aplicado; `.env` completo; documentos e `perguntas.json` de `data/avaliacao/` criados e revisados. Para os passos com `--answers`, `ingest data/avaliacao` e as amostras já cadastrados. Anotar antes `SELECT count(*) FROM documents; SELECT count(*) FROM chunks;`.

| # | Passo | Comando / ação | Resultado esperado |
|---|---|---|---|
| 1 | Avaliação padrão | `python -m src.cli eval` | Tabelas de estratégia × tamanho, por método e do limiar (4.3); código 0. |
| 2 | Base real intacta (T1) | Repetir as contagens da pré-condição | Idênticas às de antes; nenhuma linha nova em `documents`, `chunks` ou `sources`. |
| 3 | Tabelas temporárias somem | Em outra sessão `psql`: `\dt pg_temp*.*` | Sem `chunks`/`documents` temporárias. |
| 4 | Hit rate coerente | Escolher 3 perguntas e conferir na saída de `search` (com `--folder`) | O resultado do `eval` para essas perguntas bate com o `search` real nos mesmos documentos (T2). |
| 5 | Acerto confere o texto (T3) | Alterar uma pergunta para um `texto` inexistente e rodar | A pergunta passa a contar como falha e o hit rate cai. Reverter. |
| 6 | Pergunta sem resposta fora do hit rate (T5) | Conferir o total de perguntas "com resposta" na saída | Só as com `esperado` entram nas métricas; as sem resposta aparecem na tabela do limiar. |
| 7 | Estratégias | `eval --strategies structured,fixed --max-chars 900` | Só as duas linhas; `semantic` ausente por padrão. |
| 8 | Estratégia `semantic` | `eval --strategies semantic --max-chars 900` | Executa e entra na tabela; pode ser mais lenta. |
| 9 | Métodos | `eval --methods lexical` | Só `lexical`; **sem** carregar o modelo de embeddings (sem "Loading weights") e sem tabela de limiar (sem similaridade). |
| 10 | `--top-k` | `eval --top-k 3` | `hit@5` não aparece; `hit@3` = `hit@top_k`. |
| 11 | Limiar proposto (T6) | Ler a tabela do limiar | A proposta é o maior candidato com ≥ 95% das perguntas com resposta mantidas; conferir a conta à mão em duas linhas. |
| 12 | Aplicar o limiar | Definir `RELEVANCE_THRESHOLD` no `.env` com o valor aprovado | — |
| 13 | `ask` barra pergunta fora (6.1) | `ask "qual a capital da França?" --folder $(pwd)/data` com `ANTHROPIC_API_KEY=invalida` | Frase padrão, código 0, **sem erro 401** (Claude não chamado) e sem o aviso de envio. |
| 14 | `ask` mantém pergunta dentro | `ask "posso trabalhar de casa?" --folder $(pwd)/data` | Resposta com fonte, como na F07. |
| 15 | `ask` com código exato | `ask "o que significa o erro E-5107?" --folder $(pwd)/data` | Resposta com fonte (não barrada pelo limiar). Confere que o código exato não é barrado só pela similaridade (T7). |
| 16 | Sem limiar | `RELEVANCE_THRESHOLD= python -m src.cli ask "qual a capital da França?" …` | Comportamento da F07 (o Claude é chamado e responde a frase padrão). |
| 17 | `lexical` ignora o limiar | `ask "trabalho remoto" --method lexical --folder $(pwd)/data` | Responde normalmente. |
| 18 | `--answers` | `eval --answers` | Tabela de respostas (4.3); perguntas sem resposta barradas ou com a frase padrão; fontes dos acertos conferem; resumo `N/M corretas`. |
| 19 | `--answers` sem chave | `ANTHROPIC_API_KEY= python -m src.cli eval --answers; echo $?` | Erro da F07; código 1; sem trabalho caro. |
| 20 | Perguntas inválidas | Corromper o JSON e rodar `eval` | `Arquivo de perguntas inválido…`; código 1. Reverter. |
| 21 | Documento inexistente | Listar um caminho inexistente em `documentos` | `Documento não encontrado: …`; código 1. Reverter. |
| 22 | Argumentos inválidos | `eval --strategies foo`; `eval --max-chars 0` | Erro do `argparse`; código 2. |
| 23 | Interrupção | `Ctrl+C` durante o `eval` | `Avaliação interrompida.`; sem traceback; sem tabelas temporárias; código 1. |
| 24 | Padrões de trecho | Se a medição indicar novo `MAX_CHARS`/`OVERLAP_CHARS`: alterar e repetir o passo 1 | Os números do padrão novo são os da linha escolhida. Registrar a decisão e os números na seção 14. |
| 25 | Importação sem efeitos (T10) | `python -c "import src.evaluation"` | Sem saída, sem conectar ao banco nem carregar o modelo. |
| 26 | Somente o previsto | `git status` | Só os arquivos previstos (seção 5), `data/avaliacao/` e os documentos de spec. |

**Consultas úteis para conferir o banco**
```sql
SELECT count(*) FROM documents;
SELECT count(*) FROM chunks;
SELECT * FROM sources;
```

## 10. Impacto em outras features

| Feature | Roteiros a repetir (#) | Motivo |
|---|---|---|
| F07 | 1, 2, 3, 5, 6, 7, 8 | O `ask` passa a aplicar o limiar. |
| F10 | Modo conversa (opção 5 do menu) | O menu usa `run_ask`; conferir que pergunta fora dos documentos não chama o Claude. |
| F03 | Roteiro de `structured_chunks` | Se `MAX_CHARS`/`OVERLAP_CHARS` mudarem. |
| F05 / F08 | `ingest` e `reindex --force` | Se os padrões mudarem, documentos já cadastrados continuam com os trechos antigos até um `reindex --force`; conferir o aviso na documentação. |
| F06 | 3, 4, 6 | `search` não muda, mas o `eval` o reutiliza. |

## 11. Riscos e decisões

**Decisões tomadas** (confirmadas pela pessoa)
- Comparação por **tabelas temporárias** no mesmo banco, sem tocar na base real.
- Limiar **medido e aplicado no `ask`** (ajuste na F07, com a spec dela atualizada).
- Conjunto de perguntas sobre os **documentos de `data/`**, versionado.
- `--answers` **opcional** (consome a cota do Claude); o padrão mede só a recuperação.

**Decisões propostas por mim e aprovadas pela pessoa (2026-10-10)**
- **Comando `eval` na CLI** (e não um script em `scripts/experiments/`, como previa a ARQUITETURA §5): segue o padrão dos outros comandos e reaproveita `search` e `Embedder`. A ARQUITETURA é atualizada.
- **Documentos novos em `data/avaliacao/`.** O corpus atual (cerca de 2,7 KB, seções com menos de 900 caracteres) gera praticamente um trecho por seção em qualquer estratégia; **não permite diferenciar estratégias nem tamanhos**. Sem documentos mais longos, a F11 mediria só o limiar. Os documentos novos serão sintéticos (PT e EN, com seções longas, tabelas e códigos) e revisados pela pessoa.
- **Texto-chave literal** (T3) em vez de um id de trecho: não depende do tamanho dos trechos, então serve para comparar configurações.
- **Candidatos de limiar e critério de 95%** (T6): ponto de partida, ajustável na verificação.
- **Gate tudo ou nada** (6.1): o limiar só decide chamar ou não o Claude; não filtra trechos individuais.
- **`overlap_chars` proporcional** (T8) para não multiplicar configurações.
- **`--answers` usa a base real** (e o `ask` real), não as tabelas temporárias, para validar o fluxo de produção inteiro, incluindo o limiar.

**Riscos aceitos**
- O corpus de teste é pequeno e sintético; os padrões medidos valem como **ponto de partida**, não como garantia para documentos reais. Reavaliar com documentos reais é uma evolução possível (o formato do JSON já permite).
- Um texto-chave cortado entre dois trechos (comum em `fixed`) conta como falha; é uma falha real da estratégia, mas pode penalizá-la mais que o uso prático.
- Tabelas temporárias sem índice fazem busca vetorial exata: não mede o efeito do HNSW (aproximado) em volume grande.
- O RRF não tem escala absoluta; por isso o limiar usa o cosseno, não o `score` do RRF.
- Mudar `MAX_CHARS`/`OVERLAP_CHARS` não altera documentos já cadastrados sem `reindex --force`.

**Pontos em aberto** (precisam de resposta antes de implementar)
- Nenhum. Os três pontos abaixo foram **resolvidos e aprovados em 2026-10-10**:
  - **Trechos achados só pela busca textual** (código exato como `E-5107`): **decisão revista em 2026-10-10, aprovada pela pessoa:** o limiar usa **só a similaridade** (T7). A regra "1º da busca textual conta" foi descartada após a medição. O passo 15 do roteiro confere o código exato.
  - **Perguntas de teste:** cerca de 24 (18 com resposta, 6 sem), metade em inglês nos documentos em inglês, incluindo códigos exatos, números, tabelas e perguntas parafraseadas. Redigidas por mim e revisadas pela pessoa.
  - **Tamanhos testados:** 500, 900 e 1400 caracteres.

## 12. Documentação a atualizar
- `.spec/ROADMAP.md`: status da F11; decisões "limiar" e "tamanho dos trechos" resolvidas.
- `.spec/ARQUITETURA.md`: §5 (avaliação via `eval`), §7 (limiar), §8 (comando `eval`), §13 (limiar e tamanho definidos).
- `.spec/features/F07-resposta-com-fontes.md`: nota apontando o limiar da F11 (seções 2, 7 e 11).
- `.env.example`: `RELEVANCE_THRESHOLD`.
- `.claude/CLAUDE.md`: acrescentar F11 ao "implementada e verificada" ao concluir.
- `README.md`: sem mudanças (revisado na F12).

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
| 2026-10-10 | Claude (pré-verificação na implementação) | Passos executados abaixo | Aguarda execução e aprovação da pessoa. **Medição (corpus de 8 documentos, 24 perguntas, `rrf`, top-k 5):** `structured` fica em hit@1 0,94 e MRR 0,94 nos três tamanhos (500, 900 e 1400); `recursive`, `sentence` e `fixed` pioram com 1400 (MRR 0,85, 0,89 e 0,81). `semantic` como estratégia: MRR 0,86. Por método (`structured` 900): `semantic` hit@1 1,00 e MRR 1,00; `rrf` 0,94; `lexical` 0,89 (MRR 0,90). **Decisão de tamanho:** manter `MAX_CHARS` 900 e `OVERLAP_CHARS` 110 (empate com 500 e 1400 e menos trechos que 500: 46 contra 64); nenhuma mudança de código nem `reindex --force`. **Limiar (cosseno do melhor trecho nas perguntas com resposta):** de 0,552 (q17) a 0,767; sem resposta: 0,301 (França), 0,375 (bolo), 0,511 (aumento), 0,559, 0,571, 0,577 (mesmo assunto); nenhum valor separa tudo. Proposta da regra dos 95%: 0,55 (folga de 0,002); **fixado 0,50** (folga de 0,05, barra as 2 fora do assunto), aprovado pela pessoa. **Ajuste de spec durante a implementação:** a regra \"1º da busca textual conta\" (T7) deixava 3 das 6 perguntas sem resposta passarem em qualquer limiar e foi retirada (só similaridade). **Executados e conformes:** 1, 2 (base real com 136 documentos, 4822 trechos e 5 pastas antes e depois do `eval`; depois cadastrei `data/avaliacao` por exigência do `--answers`), 3 (nenhuma tabela temporária), 5 (texto inexistente derrubou o hit@1 para 0,94 em `semantic`; reverteu ao usar o arquivo original), 7, 8, 9, 10, 11 (proposta 0,55 conferida), 13 (com chave inválida: frase padrão, sem 401), 14, 15 (E-5107 respondido com fonte), 16 (sem limiar, o Claude é chamado e responde a frase padrão), 17, 18 (`--answers`: 23/24 corretas, 22 chamadas ao Claude, perguntas q19 e q21 barradas pelo limiar sem chamar o Claude), 19, 20, 21 (e variantes de pergunta inválida), 22, 25 e 26 (`git status` só com os arquivos previstos). Regressão F07: 5/6/7/8/17/18 e `check` conformes; `RELEVANCE_THRESHOLD=abc` dá `RELEVANCE_THRESHOLD inválida…` (comportamento novo, sem passo na spec). **Falha encontrada no `--answers`:** q17 (\"quantos dias de atestado posso tirar sem comprovante médico?\", documento em inglês) recebeu \"não encontrei\"; é a mesma pergunta que o `rrf` não recupera (hit@5 0,94): pergunta em português sobre tabela em inglês. Registrada como limitação do corpus/recuperação, sem ajuste. **Não executados:** 4 (conferir 3 perguntas contra o `search`), 6 (conferência visual), 12 (feito ao fixar o padrão em `src/config.py`, sem `.env`), 23 (`Ctrl+C`), 24 (sem mudança de padrões), regressão F10 (menu) e F05/F08. |
| 2026-10-10 | Jose Julio | Aprovado | Implementação e roteiro da seção 9 aprovados, conforme relato da pessoa. |
| 2026-10-10 | Jose Julio | Aprovado | Passos que a pré-verificação não executou (4, 6, 23 e 24) e a regressão de F10, F05 e F08 executados pela pessoa responsável, sem falhas, conforme relato. |
