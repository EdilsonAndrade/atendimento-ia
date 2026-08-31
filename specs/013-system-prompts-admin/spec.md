# Feature Specification: Painel Admin — Prompts do Sistema (hardcoded no agent_graph)

**Feature Branch**: `013-system-prompts-admin`
**Linear**: [EDI-71](https://linear.app/edilsonandrade/issue/EDI-71/painel-admin-gerenciar-prompts-do-sistema-hardcoded-no-agent-graph-com)
**Created**: 2026-08-31
**Status**: Draft
**Input**: Ver descrição completa do EDI-71.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Listar os prompts de sistema hardcoded (Priority: P1)

Um administrador acessa o submenu "Prompts do Sistema" (dentro do menu "Painel", ao lado de "Ingestão Tenant") e vê a lista dos prompts hoje hardcoded em `modules/ia/agent_graph.py`: `routing_agent`, `GROUNDEDNESS_RULE`, `CHITCHAT_NO_KNOWLEDGE_RULE` e `BOOKING_INTEGRITY_RULE`, cada um com título fixo indicando sua origem.

**Independent Test**: Chamar `GET /system-prompts` e verificar que os 4 registros vêm populados com o conteúdo atualmente hardcoded (seed da migration).

**Acceptance Scenarios**:
1. **Given** o admin abre "Prompts do Sistema", **When** a tela carrega, **Then** os 4 prompts hardcoded aparecem, cada um com título indicando a constante/função de origem em `agent_graph.py`.

---

### User Story 2 - Editar um prompt de sistema com versionamento (Priority: P1)

O admin edita o conteúdo de um prompt de sistema e salva. O sistema grava a nova versão como `current_version`, movendo o conteúdo anterior para `last_version` — nunca perdendo a versão anterior.

**Independent Test**: `PUT /system-prompts/{prompt_key}` com um novo conteúdo; conferir que `current_version` passou a ser o novo texto e `last_version` passou a ser o texto anterior.

**Acceptance Scenarios**:
1. **Given** um prompt com `current_version` = A, **When** o admin salva o conteúdo B, **Then** `current_version` = B e `last_version` = A.
2. **Given** o admin tenta salvar conteúdo vazio, **When** confirma, **Then** o sistema rejeita com erro de validação (400).

---

### User Story 3 - Rollback para a versão anterior (Priority: P1)

O admin decide reverter um prompt de sistema para a versão anterior.

**Independent Test**: `POST /system-prompts/{prompt_key}/rollback`; conferir que `current_version` passou a ser o `last_version` anterior.

**Acceptance Scenarios**:
1. **Given** um prompt com `current_version` = B e `last_version` = A, **When** o admin faz rollback, **Then** `current_version` = A e `last_version` = B (a operação é reversível — rollback duas vezes seguidas volta ao estado original).

---

### User Story 4 - Runtime do agente usa o conteúdo do banco, com fallback local (Priority: P1)

O `agent_graph.py` passa a carregar `routing_agent`, `GROUNDEDNESS_RULE`, `CHITCHAT_NO_KNOWLEDGE_RULE` e `BOOKING_INTEGRITY_RULE` do banco (`current_version`) a cada turno. Se o banco estiver indisponível ou o registro não existir, usa o texto hardcoded local como fallback — o comportamento do agente nunca fica indisponível por causa desta feature.

**Independent Test**: Editar `GROUNDEDNESS_RULE` via API, disparar uma conversa institucional/operacional e confirmar (via log) que o novo texto foi usado. Derrubar a conexão com o banco e confirmar que o texto hardcoded local ainda é usado sem erro para o cliente final.

**Acceptance Scenarios**:
1. **Given** um prompt de sistema editado no painel, **When** o agente processa uma nova mensagem, **Then** o conteúdo vindo do banco é usado (sem precisar de deploy).
2. **Given** o banco está indisponível, **When** o agente processa uma mensagem, **Then** o conteúdo hardcoded local é usado como fallback, sem interromper o atendimento.

## Fora de escopo

- Alterar o comportamento da página "Ingestão Tenant".
- Remover os fallbacks locais hardcoded (permanecem como plano de contingência).
- Construir a UI do Painel Admin (este repositório é somente backend — a UI consome os endpoints REST descritos aqui).
- Adicionar/remover novos `prompt_key`s pelo painel (o conjunto é fixo, populado pela migration).

## Requisitos Funcionais

- **FR-001**: O sistema deve expor os 4 prompts hardcoded (`routing_agent`, `groundedness_rule`, `chitchat_no_knowledge_rule`, `booking_integrity_rule`) em uma tabela própria (`system_prompts`), com colunas `current_version` e `last_version`.
- **FR-002**: A migration inicial deve popular `current_version` e `last_version` com o conteúdo hardcoded atual (idêntico ao de `agent_graph.py` no momento da migration), para nunca existir rollback para versão nula.
- **FR-003**: `PUT /system-prompts/{prompt_key}` atualiza `current_version`, movendo o valor anterior para `last_version`.
- **FR-004**: `POST /system-prompts/{prompt_key}/rollback` troca `current_version` ↔ `last_version`.
- **FR-005**: O runtime do agente (`agent_graph.py`) lê `current_version` do banco a cada turno; em caso de falha de infraestrutura ou registro ausente, usa o texto hardcoded local (mesmo padrão de fallback já usado por `prompts/load_prompt.py`).
- **FR-006**: O template de `routing_agent` mantém o placeholder dinâmico de "intenção anterior" (`{previous_turn_intent}`), substituído em runtime — igual ao comportamento atual.

## Entidades-Chave

- **SystemPrompt**: `id` (uuid), `prompt_key` (slug único: `routing_agent`, `groundedness_rule`, `chitchat_no_knowledge_rule`, `booking_integrity_rule`), `titulo` (nome de exibição, ex. "GROUNDEDNESS_RULE"), `current_version` (text), `last_version` (text), `created_at`, `updated_at`.
