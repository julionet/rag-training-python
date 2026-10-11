# NEGÓCIO — Assistente de consulta a documentos

> Este documento descreve **o que** a aplicação faz e **por quê**, sem detalhes técnicos. Os detalhes técnicos estão em [ARQUITETURA.md](ARQUITETURA.md).

## 1. Problema

A equipe tem muitos documentos (manuais, políticas, material técnico), espalhados em pastas, em formato texto e PDF. Encontrar uma informação específica exige abrir arquivos e ler. Nem sempre se sabe em qual documento está a resposta.

## 2. Solução

Uma aplicação em que a pessoa **faz uma pergunta em linguagem natural** e recebe uma **resposta direta, com a indicação de onde a informação foi encontrada** (documento e página). A resposta se baseia **somente** no conteúdo dos documentos cadastrados.

## 3. Usuários

- **Uma equipe pequena**, que consulta a mesma base de documentos.
- Todos os integrantes podem ver todos os documentos. Não há restrição por pessoa ou grupo nesta fase (ver seção 9).
- Alguém da equipe também cuida da base: adiciona pastas e atualiza os documentos.

## 4. Escopo desta fase

### O que a aplicação faz

1. **Cadastrar documentos** em formato **TXT**, **Markdown (MD)** e **PDF**, informando uma ou mais pastas, uma de cada vez.
2. **Atualizar a base** de uma pasta quando os documentos mudam, trazendo só o que é novo ou foi alterado.
3. **Consultar** todos os documentos cadastrados de uma vez, ou limitar a consulta a uma pasta.
4. **Responder com fontes**: cada resposta indica o documento e a página de onde veio.
5. **Admitir quando não sabe**: se os documentos não trazem a informação, a aplicação diz isso e não inventa.
6. **Gerenciar a base**: ver quais pastas e documentos estão cadastrados e remover o que não for mais necessário.

### Tipos de documento e idioma

- Aceitos: **TXT**, **Markdown (.md)** e **PDF com texto selecionável**.
- O conteúdo é **misto**: não há um tipo ou tema único de documento.
- Documentos e perguntas podem estar em **português e em inglês**.
- Tamanho: a base deve comportar **centenas de arquivos**, incluindo PDFs grandes.

## 5. Regras de negócio

- **R1.** A resposta usa **apenas** o que está nos documentos. Conhecimento externo não entra.
- **R2.** Toda resposta com informação indica a **fonte** (documento e página).
- **R3.** Se não houver informação suficiente, a resposta diz exatamente que não encontrou, sem tentar adivinhar.
- **R4.** O **mesmo conteúdo não é cadastrado duas vezes**. Se um arquivo igual existir em outro lugar, ele é ignorado e o resumo informa de qual arquivo ele é cópia.
- **R5.** Atualizar uma pasta **não refaz tudo**: arquivo novo é incluído, arquivo alterado substitui a versão anterior, arquivo igual é mantido.
- **R6.** Um arquivo que foi apagado da pasta **só sai da base se a pessoa pedir** explicitamente.
- **R7.** Um arquivo com problema (corrompido, sem texto, formato não aceito) **não interrompe** o cadastro dos demais. No final, a pessoa recebe um resumo do que deu certo e do que falhou, com o motivo.
- **R8.** PDF sem texto selecionável (por exemplo, escaneado) **não é aceito**, e a pessoa é avisada.
- **R9.** Um documento só aparece nas consultas depois de **cadastrado por completo**. Um cadastro interrompido não deixa resultados pela metade.
- **R10.** Antes de **remover** documentos ou pastas, a aplicação pede confirmação.
- **R11.** Os trechos usados para responder são enviados a um serviço externo de inteligência artificial (Claude). Isso é aceito para os documentos desta base, que não têm restrição de confidencialidade para esse fim.

## 6. Como medir o sucesso

| Critério | Como se verifica |
|---|---|
| Respostas corretas, com fonte | Perguntas de teste sobre documentos conhecidos devolvem a informação certa e apontam o documento e a página certos. |
| Admite quando não sabe | Perguntas sobre assuntos que **não** estão nos documentos recebem a resposta de "não encontrei", e não uma invenção. |
| Base sempre atualizada | Depois de alterar, incluir ou apagar arquivos, atualizar a pasta reflete a mudança sem refazer a base inteira. |

O tempo de cadastro de arquivos grandes **não foi definido como critério de sucesso** nesta fase. Ele será acompanhado, mas sem meta fixa.

## 7. Fluxos principais

**Cadastrar e atualizar**
1. A pessoa informa uma pasta.
2. A aplicação lê os arquivos TXT, MD e PDF, ignora duplicados e informa o que fez com cada um.
3. Quando os documentos mudam, a pessoa atualiza a pasta e só o necessário é refeito.
4. Pode repetir o processo com outras pastas, e todas passam a compor a mesma base.

**Perguntar**
1. A pessoa escreve a pergunta, em português ou inglês.
2. A aplicação procura os trechos mais relevantes em todos os documentos (ou só na pasta escolhida).
3. Devolve a resposta com as fontes, ou diz que não encontrou.

## 8. Fora de escopo nesta fase

- Outros formatos além de TXT, MD e PDF (Word, planilhas, páginas web, imagens).
- PDFs escaneados (que exigem reconhecimento de texto em imagem).
- Edição ou criação de documentos pela aplicação.
- Controle de acesso por pessoa, grupo ou documento.
- Interface web e acesso por API (a API REST foi implementada na F14, sem autenticação; a interface web segue fora).
- Histórico de conversas entre sessões.

## 9. Evoluções futuras (roadmap de negócio)

Registradas para planejamento posterior, **não** fazem parte desta fase:

1. **Acesso pela equipe via API e/ou interface web**, para que as pessoas consultem sem usar linha de comando. A **API REST** (F14, sem autenticação) foi implementada; a interface web continua futura.
2. **Controle de acesso**: documentos visíveis apenas para pessoas ou grupos autorizados. Hoje todos veem tudo. A **autenticação da API** entra junto com este item.
3. Reconhecimento de texto em PDFs escaneados.
4. Outros formatos além de TXT, MD e PDF (Word, planilhas).
5. **Implantação em contêiner (F15, **implementada e verificada em 2026-10-11**):** subir a aplicação e o banco com Docker Compose, para que outra pessoa ou outra máquina rode tudo sem instalar PostgreSQL, pgvector e Python. **Requisito de plataforma:** deve rodar do mesmo jeito em **macOS, Windows e Linux** (processadores Intel/AMD e Apple Silicon/ARM), com o mesmo resultado nas consultas. Os dados (banco e modelo de embeddings) devem sobreviver a reinicializações, e a API, que ainda não tem autenticação, não pode ficar exposta à rede por padrão. Detalhes em ARQUITETURA §15.
6. **Troca do modelo de embeddings (F16, planejada, sem spec):** hoje o modelo é fixo (`BAAI/bge-m3`) e trocá-lo é bloqueado. A troca passa a ser uma operação explícita, que revetoriza a base inteira. Detalhes em ARQUITETURA §16.
7. **Vários provedores de LLM (F17, planejada, sem spec):** hoje só o Claude responde às perguntas. A aplicação passa a poder usar **OpenAI (ChatGPT), Gemini, DeepSeek e modelos locais (Ollama)**, além do Claude, escolhidos na configuração. Como cada provedor é um novo destino dos trechos dos documentos, só entram os da **lista de provedores aprovados** (R11 revisada). Detalhes em ARQUITETURA §17.

8. **Servidor MCP (F18, spec aprovada em 2026-10-11, implementação pendente):** a base passa a poder ser consultada por qualquer cliente com suporte a MCP (por exemplo Claude Desktop e Claude Code). O cliente envia a pergunta, o servidor devolve **só os trechos recuperados** com as regras de resposta, e o **LLM do próprio cliente** responde à pessoa: neste canal a aplicação **não chama o Claude**. Só leitura e só local nesta fase. Detalhes em ARQUITETURA §18.

**Regras de negócio propostas para a troca de modelo** (rascunho; só valem depois de formalizadas na spec da F16):
- **R12 (proposta).** O modelo de embeddings só é trocado por um pedido explícito, nunca por mudança do `.env`, e **com confirmação** (R10) que mostra o que será refeito (documentos, trechos e tempo estimado).
- **R13 (proposta).** Durante e depois da troca, **uma consulta nunca mistura vetores de modelos diferentes**: ou usa a base antiga completa, ou a nova completa. Uma troca interrompida não deixa a base pela metade (R9).
- **R14 (proposta).** Depois da troca, a qualidade é **medida de novo** (F11) e o limiar de relevância é revisto antes de a troca ser considerada concluída, porque outro modelo muda a escala das pontuações.
- Os arquivos originais **não** precisam ser relidos: os trechos de texto já estão na base e só os vetores são refeitos.

**Regras de negócio propostas para vários provedores de LLM** (rascunho; só valem depois de formalizadas na spec da F17):
- **R11 (revisão proposta).** Os trechos usados para responder são enviados **apenas a provedores da lista de aprovados**. A lista inicial, **aprovada em 2026-10-11**, é: Claude, OpenAI, Gemini, **DeepSeek** (aprovado pelo usuário, ciente de que os servidores da API ficam na China) e Ollama (local). Cada um só passa a ser **suportado** depois de validado (R16); até lá, ou se for removido da lista, é recusado. Um provedor fora da lista é recusado. Um modelo **local** (Ollama) não envia os documentos para fora da máquina.
- **R15 (proposta).** Toda resposta indica **qual provedor e modelo** a gerou, na CLI, na API e no `check`.
- **R16 (proposta).** As regras R1 a R3 valem para **qualquer** provedor (só os documentos, fonte citada, "não encontrei" sem adivinhar). Um provedor só é considerado suportado depois de passar no `eval --answers` (F11), cumprindo a frase padrão, as citações `[n]` e a resposta em português.
- **R17 (proposta).** Trocar de provedor **não reindexa nada** nem altera a base: os vetores continuam sendo gerados pelo modelo local de embeddings.

**Regras de negócio propostas para o servidor MCP** (rascunho; só valem depois de formalizadas na implementação da F18, cuja spec foi aprovada em 2026-10-11):
- **R11 (revisão para o canal MCP).** No servidor MCP, os trechos devolvidos vão ao LLM do **cliente MCP escolhido por quem usa**, **qualquer um** (decisão do usuário, 2026-10-11). Isso vale **só para este canal**; no `ask` continua valendo a R11 acima (e a revisão proposta da F17).
- **R18 (proposta).** O servidor MCP é **somente leitura**: nenhuma ferramenta cadastra, altera, remove ou avalia documentos.
- **R19 (proposta).** Os trechos são entregues como **dado não confiável**: instruções dentro deles não devem ser seguidas. O servidor marca isso no retorno e no prompt; o efeito depende do cliente.
- **R20 (proposta).** O servidor MCP em HTTP **não é exposto à rede**: só `127.0.0.1`, até existir autenticação.
- **R1 a R3 no MCP:** são **orientadas, não garantidas**, porque quem responde é o LLM do cliente. A frase de "não encontrei" quando nada passa do limiar de relevância é garantida pelo servidor.

## 10. Pontos em aberto

- Quantas pessoas consultam ao mesmo tempo, e se precisam de histórico de perguntas. (Com a API, a concorrência passa a importar: ver F14.)
- Meta de tempo para cadastrar arquivos grandes, se vier a ser necessária.
- Limites de tamanho de arquivo aceitos.
- ~~**F15 (contêiner)**~~ **Resolvido (2026-10-11):** uso **só local** nesta fase (servidor da equipe depende de autenticação); sistemas suportados: macOS Apple Silicon, Windows 11 (Docker Desktop com WSL 2) e Ubuntu LTS 22.04/24.04 (amd64), com uma pessoa da equipe testando cada um. **Backup do banco:** fica com quem roda o Compose (o README documenta `pg_dump` e restauração; nada automático).
- ~~**F16 (troca de modelo)**~~ **Resolvido (2026-10-11):** durante a troca as consultas continuam e as alterações (`ingest`, `reindex`, `delete`) são recusadas; o espaço em disco é irrelevante (≈ 20 MB). Em aberto: qual modelo será adotado de fato (será medido com o `eval`).
- **F17 (vários provedores de LLM):** ~~o **DeepSeek** entra na lista de aprovados?~~ **Resolvido (2026-10-11):** aprovado, com a ressalva registrada de que os servidores da API ficam na China. Em aberto: qual modelo local será usado no Ollama e em que máquina? Qual o orçamento para validar cada provedor com o `eval --answers` (consome a cota de cada serviço)? Os detalhes técnicos das APIs ficam para a especificação.
- ~~**F18 (servidor MCP):** escopo, transportes, política de privacidade, idioma e formato do retorno.~~ **Resolvido (2026-10-11):** só leitura (`search_documents` e `list_sources`); stdio e HTTP local; qualquer cliente MCP (R11 do canal MCP); resposta em português por padrão; retorno em texto. Em aberto: o suporte real de cada cliente (Claude Code e Claude Desktop em stdio e HTTP; ChatGPT e Gemini de consumo ficam fora desta fase), a confirmar no roteiro da spec.
- ~~Se o idioma da resposta deve acompanhar o da pergunta ou ser sempre português.~~ **Resolvido na F07:** a resposta é sempre em português.
