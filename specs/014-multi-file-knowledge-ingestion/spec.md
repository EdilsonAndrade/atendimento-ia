# Feature Specification: Ingestão de Dados por Múltiplos Arquivos

**Feature Branch**: `edilsonaandrade/edi-39-permitir-ingestao-de-dados-por-multiplos-arquivos`
**Linear**: [EDI-39](https://linear.app/edilsonandrade/issue/EDI-39/permitir-ingestao-de-dados-por-multiplos-arquivos)
**Created**: 2026-09-01
**Status**: Draft
**Input**: Ver descrição completa e análise técnica do EDI-39.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Enviar múltiplos arquivos e textos, adicionando à ingestão existente (Priority: P1)

Um administrador, na tela de Ingestão Tenant, envia N arquivos (PDF, XLS/XLSX ou CSV) e/ou textos diretos, com o toggle de substituição desmarcado. O sistema pergunta se deseja adicionar os novos arquivos/textos à ingestão existente e, confirmado, cria um item novo por arquivo/texto, preservando os itens já existentes.

**Why this priority**: É o caso de uso central do ticket — hoje só é possível enviar um texto corrido por vez, substituindo tudo.

**Independent Test**: Chamar `POST /api/v1/tenants/{tenant_id}/knowledge-base/items` com `mode=append`, 2 arquivos e 1 texto, e conferir que `GET /api/v1/tenants/{tenant_id}/knowledge-base/items` retorna os itens antigos mais os 3 novos.

**Acceptance Scenarios**:

1. **Given** um tenant sem nenhuma ingestão, **When** o admin envia 2 arquivos e 1 texto em modo adicionar, **Then** a grid passa a ter 3 itens.
2. **Given** um tenant com 2 itens já existentes, **When** o admin envia mais 1 arquivo em modo adicionar, **Then** a grid passa a ter 3 itens, sem alterar os 2 anteriores.

---

### User Story 2 - Substituir toda a ingestão existente (Priority: P1)

O administrador marca o toggle de substituição e envia novos arquivos/textos. O sistema exibe um modal confirmando que TODOS os dados de ingestão atuais serão substituídos; confirmado, todos os itens antigos (e seus vetores) são apagados e os novos são criados no lugar.

**Why this priority**: É o outro modo obrigatório do toggle descrito no ticket, sem o qual não há como "recomeçar do zero".

**Independent Test**: Com 2 itens existentes, chamar `POST /api/v1/tenants/{tenant_id}/knowledge-base/items` com `mode=replace` e 1 arquivo novo; conferir que a grid passa a ter só 1 item.

**Acceptance Scenarios**:

1. **Given** um tenant com itens existentes, **When** o admin confirma a substituição total, **Then** os itens antigos deixam de aparecer na grid e só os novos permanecem.
2. **Given** o admin cancela o modal de confirmação, **When** ele cancela, **Then** nenhuma chamada de substituição é feita e nada muda.

---

### User Story 3 - Visualizar a grid de itens com preview e conteúdo completo (Priority: P2)

O administrador vê uma grid com todos os itens de ingestão do tenant (arquivos e textos), cada um mostrando os primeiros 1000 caracteres do conteúdo extraído. Ao clicar em um item, abre um modal com o conteúdo completo em uma área com scroll.

**Why this priority**: Sem essa visão, o admin não consegue conferir o que já foi ingerido antes de decidir substituir, editar ou excluir.

**Independent Test**: Chamar `GET /api/v1/tenants/{tenant_id}/knowledge-base/items` e conferir que cada item tem `content_preview` com no máximo 1000 caracteres; chamar `GET .../items/{item_id}` e conferir que `content` vem completo.

**Acceptance Scenarios**:

1. **Given** um item com conteúdo de 5000 caracteres, **When** a grid é carregada, **Then** `content_preview` tem exatamente os primeiros 1000 caracteres.
2. **Given** o admin clica em um item da grid, **When** o modal abre, **Then** o conteúdo completo (5000 caracteres) é exibido com scroll.

---

### User Story 4 - Editar manualmente o texto extraído de um item (Priority: P2)

O administrador edita livremente o texto de um item já ingerido (extraído de Excel, PDF ou colado), da mesma forma como a edição de texto já funciona hoje.

**Why this priority**: Requisito explícito do ticket — reforça que a edição manual não pode regredir com a migração para múltiplos itens.

**Independent Test**: `PUT /api/v1/tenants/{tenant_id}/knowledge-base/items/{item_id}` com um novo `content` e conferir que o item retorna atualizado.

**Acceptance Scenarios**:

1. **Given** um item existente, **When** o admin edita e salva um novo texto, **Then** o item passa a refletir o novo conteúdo e a reindexação vetorial daquele item é dispara em background.
2. **Given** o admin tenta salvar conteúdo vazio, **When** confirma, **Then** o sistema rejeita com erro de validação (422).

---

### User Story 5 - Substituir o arquivo de um item específico (Priority: P2)

O administrador substitui o conteúdo de um item específico enviando um novo arquivo "por cima" do anterior, sem afetar os demais itens da ingestão.

**Why this priority**: Evita que o admin precise apagar e recriar manualmente um item só porque o arquivo de origem mudou.

**Independent Test**: `PUT /api/v1/tenants/{tenant_id}/knowledge-base/items/{item_id}/file` com um novo arquivo; conferir que `filename` e `content` do item mudaram e que os outros itens do tenant permanecem intactos.

**Acceptance Scenarios**:

1. **Given** um item de arquivo existente, **When** o admin envia um novo arquivo para substituí-lo, **Then** o item passa a refletir o novo arquivo (nome e conteúdo), preservando seu `id`.

---

### User Story 6 - Excluir um item individualmente (Priority: P3)

O administrador exclui um item específico da grid, mantendo todos os outros intactos.

**Why this priority**: Completa o ciclo de manutenção item a item; prioridade menor porque replace-all já cobre o caso de "recomeçar do zero".

**Independent Test**: `DELETE /api/v1/tenants/{tenant_id}/knowledge-base/items/{item_id}`; conferir que o item some da grid e os demais continuam presentes.

**Acceptance Scenarios**:

1. **Given** um tenant com 3 itens, **When** o admin exclui 1 item, **Then** a grid passa a ter 2 itens e a base vetorial mantém somente os chunks dos 2 restantes.

---

### User Story 7 - Detectar nome de arquivo duplicado no modo adicionar (Priority: P2)

Ao enviar, em modo adicionar, um arquivo cujo nome já existe entre os itens do tenant, o sistema não cria silenciosamente um duplicado nem sobrescreve — pergunta ao admin se deseja substituir o item existente ou adicionar mesmo assim (mantendo ambos, mesmo repetido).

**Why this priority**: Decisão de produto explícita, validada com o usuário durante a especificação deste ticket — evita perda de dados por sobrescrita silenciosa e evita duplicação acidental sem aviso.

**Independent Test**: Com um item `filename=precos.xlsx` já existente, chamar `POST .../items` em modo adicionar reenviando `precos.xlsx` sem `duplicate_resolutions`; conferir resposta `409` com a lista de conflitos. Reenviar com `duplicate_resolutions=[{"filename":"precos.xlsx","action":"replace","existing_item_id":"..."}]` e conferir que o item existente foi atualizado (não duplicado).

**Acceptance Scenarios**:

1. **Given** um item `precos.xlsx` já existente, **When** o admin envia outro arquivo com o mesmo nome sem resolver o conflito, **Then** a API responde 409 com a lista de conflitos, sem criar nem sobrescrever nada.
2. **Given** o conflito acima, **When** o admin escolhe "adicionar mesmo assim", **Then** um novo item é criado com o mesmo `filename`, coexistindo com o anterior.
3. **Given** o conflito acima, **When** o admin escolhe "substituir", **Then** o item existente é atualizado com o novo conteúdo, mantendo seu `id`.

---

### Edge Cases

- Envio sem nenhum arquivo e sem nenhum texto → 422 (nada para ingerir).
- Arquivo com extensão não suportada (ex.: `.docx`) → 422, informando as extensões aceitas.
- PDF sem texto extraível (ex.: digitalizado sem OCR, imagem sem camada de texto) → a API rejeita com 422 e uma mensagem específica citando o nome do arquivo (não cria o item; validado em produção — foi o primeiro caso real encontrado ao testar o endpoint).
- Exclusão do último item restante → a base de conhecimento do tenant fica vazia; `GET /tenants/{tenant_id}/knowledge-base` volta a retornar `content: null`, igual ao comportamento de hoje quando nunca houve ingestão.
- `mode=replace` em um tenant que ainda não tem nenhum item → apenas cria os novos itens (não há nada para apagar).
- Tenant inexistente em qualquer endpoint → 404.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: O sistema MUST permitir o envio de N arquivos (`.pdf`, `.xls`, `.xlsx`, `.csv`) e/ou N textos diretos em uma única chamada de ingestão.
- **FR-002**: Cada arquivo ou texto enviado MUST se tornar um item individual e rastreável na base de conhecimento do tenant (não mais um único blob de texto).
- **FR-003**: O sistema MUST suportar dois modos de ingestão explícitos: `append` (adicionar aos itens existentes) e `replace` (apagar todos os itens existentes e criar somente os novos).
- **FR-004**: Em modo `append`, o sistema MUST detectar arquivos cujo nome já existe entre os itens do tenant e MUST recusar a criação (`409`) até que o chamador informe, por arquivo, se deseja substituir o item existente ou adicionar mesmo assim (duplicado).
- **FR-005**: O sistema MUST expor uma listagem dos itens do tenant com um preview limitado aos primeiros 1000 caracteres do conteúdo de cada item.
- **FR-006**: O sistema MUST expor o conteúdo completo de um item individual, para exibição em modal.
- **FR-007**: O sistema MUST permitir editar manualmente o texto de um item existente, preservando a possibilidade de edição livre já existente hoje.
- **FR-008**: O sistema MUST permitir substituir o conteúdo de um único item enviando um novo arquivo, sem afetar os demais itens do tenant.
- **FR-009**: O sistema MUST permitir excluir um único item, mantendo os demais itens e seus vetores intactos.
- **FR-010**: O endpoint `GET /tenants/{tenant_id}/knowledge-base` MUST continuar funcionando sem quebra de contrato, retornando `content` como a concatenação dos itens ativos do tenant.
- **FR-011**: O endpoint `DELETE /tenants/{tenant_id}/knowledge-base` MUST continuar disponível para apagar toda a base de conhecimento do tenant de uma só vez.
- **FR-012**: Toda operação que gera ou altera embeddings (criação, edição, substituição, exclusão de item) MUST rodar a revetorização em background, nunca bloqueando a resposta da requisição (Princípio V da constituição).
- **FR-013**: A reindexação vetorial MUST poder ser escopada a um único item (via metadado `item_id`), para que editar/substituir/excluir um item não afete os vetores dos demais itens do mesmo tenant.
- **FR-014**: O sistema MUST rejeitar (`422`) envios sem nenhum arquivo/texto, com extensão de arquivo não suportada, ou com texto/edição de conteúdo vazio.

### Key Entities *(include if feature involves data)*

- **KnowledgeBaseItem**: um item individual da base de conhecimento de um tenant. Atributos: `id` (uuid), `tenant_id`, `source_type` (`file` | `texto`), `filename` (nulo para texto colado), `content` (texto extraído ou colado completo), `created_at`, `updated_at`. Substitui o modelo atual de um único `content` por tenant (tabela `tenant_knowledge_base`), que passa a ser uma visão derivada (concatenação dos itens).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Um administrador consegue enviar 5 arquivos de tipos diferentes (PDF, XLS, CSV) em uma única operação, sem precisar repetir o processo arquivo a arquivo.
- **SC-002**: 100% das exclusões ou substituições de um item individual preservam os demais itens do tenant (sem regressão de conteúdo já ingerido).
- **SC-003**: Nenhuma sobrescrita ou duplicação de arquivo ocorre sem confirmação explícita do administrador (0 casos de perda silenciosa de dado por nome duplicado).
- **SC-004**: A tela de preview atual (`content` agregado) continua funcionando sem alteração perceptível para quem só consome o `GET /tenants/{tenant_id}/knowledge-base` existente.

## Assumptions

- Este repositório é somente backend; a UI (grid, modais de confirmação, toggle) é construída e mantida no serviço de frontend do Painel Administrador, fora deste repositório — esta spec cobre apenas os endpoints REST.
- O arquivo binário original (PDF/XLS/CSV) não é persistido em disco/storage — apenas o texto extraído é guardado. Substituir "o arquivo" de um item descarta o binário antigo e grava só o novo texto extraído.
- Tamanho máximo sugerido de 10MB por arquivo; sem teto rígido de quantidade de arquivos por envio nesta primeira versão.
- A extração de PDF/XLS/CSV reaproveita a lógica já existente em `protocols/file_data_reader.py` / `modules/vetorizacao/setup_databases.py` (pypdf + pandas), adaptada para ler de `UploadFile` em vez de pasta em disco.
