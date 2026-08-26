# Fase 1 — Data Model: Histórico consultável, resumo e outcome por sessão (EDI-53)

## Tabelas novas

### `conversation_messages`

| Coluna | Tipo | Constraint | Descrição |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `tenant_id` | VARCHAR(50) | NOT NULL | isolamento multi-tenant (Princípio I) |
| `base_thread_id` | VARCHAR(255) | NOT NULL | thread "lógica" do cliente (sobrevive a expiração de sessão) |
| `active_thread_id` | VARCHAR(255) | NOT NULL | thread real da sessão no LangGraph (`base_thread_id#hash`) |
| `role` | VARCHAR(10) | NOT NULL, CHECK IN ('human','ai') | só as duas mensagens visíveis do turno (ver research.md §2) |
| `content` | TEXT | NOT NULL | texto da mensagem |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

Índices: `ix_conversation_messages_tenant_base_thread (tenant_id, base_thread_id, created_at)` — cobre a leitura de histórico (FR-008) e o expurgo por tenant (FR-007). `ix_conversation_messages_retention (tenant_id, created_at)` desnecessário — o índice composto já cobre.

### `follow_up_queue`

| Coluna | Tipo | Constraint | Descrição |
|---|---|---|---|
| `id` | SERIAL | PK | |
| `tenant_id` | VARCHAR(50) | NOT NULL | |
| `base_thread_id` | VARCHAR(255) | NOT NULL | |
| `outcome` | VARCHAR(20) | NOT NULL, CHECK IN ('fechado','pensando','sem_resposta','recusado','em_andamento') | |
| `summary` | TEXT | NOT NULL DEFAULT '' | mesmo `resumo` gerado para `chat_thread_summaries` (duplicado aqui para o consumidor da fila não precisar fazer JOIN) |
| `draft_message` | TEXT | NULL | só preenchido quando `outcome IN ('pensando','sem_resposta')` |
| `status` | VARCHAR(20) | NOT NULL DEFAULT 'pendente', CHECK IN ('pendente','aprovado','enviado','descartado','opt_out') | |
| `attempts` | INTEGER | NOT NULL DEFAULT 0 | reservado para o worker de disparo (ticket futuro) |
| `approved_by` | VARCHAR(255) | NULL | reservado para a UI de aprovação (ticket futuro) |
| `approved_at` | TIMESTAMPTZ | NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |

Constraint de idempotência (FR-004): `UNIQUE (tenant_id, base_thread_id, created_at)` não resolve idempotência de reprocessamento de forma robusta (timestamps diferem). Em vez disso, a idempotência é garantida no nível de aplicação: `sessao_thread_id` (= `active_thread_id` que expirou) é usado como chave de claim, com `UNIQUE (active_thread_id)` — a mesma coluna que `chat_thread_summaries.sessao_thread_id` já usa como referência da sessão expirada. Adiciona-se `active_thread_id VARCHAR(255) NOT NULL` a `follow_up_queue` com esse `UNIQUE`, e o `INSERT` usa `ON CONFLICT (active_thread_id) DO NOTHING` — reprocessar a mesma sessão expirada é inofensivo.

Índices: `ix_follow_up_queue_tenant_status (tenant_id, status, created_at DESC)` — cobre a leitura filtrada por tenant/status (FR-009).

## Colunas novas em `tenants`

| Coluna | Tipo | Constraint | Descrição |
|---|---|---|---|
| `oferta_vigente_texto` | TEXT | NULL | texto livre da oferta/condição comercial vigente |
| `oferta_vigente_validade` | DATE | NULL | data até quando a oferta vale; `NULL` = sem oferta vigente mesmo que `_texto` esteja preenchido (defensivo) |
| `retention_days` | INTEGER | NULL | dias de retenção de `conversation_messages`; `NULL` = sem expurgo automático |

Regra de validade efetiva (usada no research.md §3 e no FR-005): oferta é "vigente" apenas quando `oferta_vigente_texto IS NOT NULL AND oferta_vigente_validade IS NOT NULL AND oferta_vigente_validade >= CURRENT_DATE`.

## Extensão de `follow_up_queue`/`chat_thread_summaries` (sem migration nova para `chat_thread_summaries`)

`chat_thread_summaries` não é alterada por este ticket (ver spec.md > Clarifications) — continua recebendo só `resumo`/`fatos_estruturados` como hoje.

## Migration

Um único arquivo novo: `migrations/versions/0009_conversation_followup.py`, `down_revision = "0008_tenant_message_limit"`, contendo (nesta ordem, por dependência de leitura durante testes):
1. `ALTER TABLE tenants ADD COLUMN oferta_vigente_texto`, `oferta_vigente_validade`, `retention_days`
2. `CREATE TABLE conversation_messages` + índice
3. `CREATE TABLE follow_up_queue` + índice + `UNIQUE (active_thread_id)`

## Entidades de Domínio (Python, `modules/*/domain/`)

- `modules/conversation_history/domain/conversation_message.py` → dataclass `ConversationMessage(tenant_id, base_thread_id, active_thread_id, role, content)`, com validação de `role` no `__post_init__` (só aceita `"human"`/`"ai"`).
- `modules/follow_up/domain/follow_up_entry.py` → dataclass `FollowUpEntry(tenant_id, base_thread_id, active_thread_id, outcome, summary, draft_message, status="pendente")`, com `Outcome` como `Literal`/enum Python (`FECHADO`, `PENSANDO`, `SEM_RESPOSTA`, `RECUSADO`, `EM_ANDAMENTO`) e `Status` como `Literal`/enum (`PENDENTE`, `APROVADO`, `ENVIADO`, `DESCARTADO`, `OPT_OUT`).
- `modules/follow_up/domain/oferta_vigente.py` → função pura `is_oferta_vigente(texto: str | None, validade: date | None, hoje: date) -> bool`, testável sem banco/LLM — a mesma regra do FR-005, extraída como Domain puro para ser unit-testável isoladamente do prompt.
