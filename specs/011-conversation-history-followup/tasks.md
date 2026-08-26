# Tasks: Histórico consultável, resumo e outcome por sessão (Fundação de Follow-up)

**Input**: Design documents from `specs/011-conversation-history-followup/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: incluídos (Princípio VI da constituição é NON-NEGOTIABLE para módulo novo).

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 [P] Criar esqueleto `modules/conversation_history/` (`__init__.py`, `domain/__init__.py`, `application/__init__.py`, `infrastructure/__init__.py`)
- [X] T002 [P] Criar esqueleto `modules/follow_up/` (mesmos subpacotes: `__init__.py`, `domain/__init__.py`, `application/__init__.py`, `infrastructure/__init__.py`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: bloqueia todas as user stories.

- [X] T003 Migration `migrations/versions/0009_conversation_followup.py` (`down_revision = "0008_tenant_message_limit"`): `ALTER TABLE tenants ADD COLUMN oferta_vigente_texto TEXT`, `ADD COLUMN oferta_vigente_validade DATE`, `ADD COLUMN retention_days INTEGER`; `CREATE TABLE conversation_messages` (+ índice `ix_conversation_messages_tenant_base_thread`); `CREATE TABLE follow_up_queue` (+ índice `ix_follow_up_queue_tenant_status`, `UNIQUE (active_thread_id)`) — ver data-model.md
- [X] T004 [P] `modules/conversation_history/domain/conversation_message.py`: dataclass `ConversationMessage(tenant_id, base_thread_id, active_thread_id, role, content, created_at=None)`, valida `role` em `__post_init__` (só `"human"`/`"ai"`, senão `ValueError`)
- [X] T005 [P] `modules/conversation_history/application/ports.py`: `Protocol ConversationMessageRepository` com `save_turn(human: ConversationMessage, ai: ConversationMessage) -> None`, `list_by_thread(tenant_id, base_thread_id, limit, before) -> list[ConversationMessage]`, `purge_older_than(tenant_id, retention_days) -> int`
- [X] T006 [P] `modules/follow_up/domain/follow_up_entry.py`: `Outcome` (enum: `FECHADO`, `PENSANDO`, `SEM_RESPOSTA`, `RECUSADO`, `EM_ANDAMENTO`), `Status` (enum: `PENDENTE`, `APROVADO`, `ENVIADO`, `DESCARTADO`, `OPT_OUT`), dataclass `FollowUpEntry(tenant_id, base_thread_id, active_thread_id, outcome, summary, draft_message=None, status=Status.PENDENTE)`
- [X] T007 [P] `modules/follow_up/domain/oferta_vigente.py`: `is_oferta_vigente(texto: str | None, validade: date | None, hoje: date) -> bool` — `True` somente quando `texto` e `validade` preenchidos E `validade >= hoje`
- [X] T008 [P] `modules/follow_up/application/ports.py`: `Protocol FollowUpQueueRepository` com `save(entry: FollowUpEntry) -> bool` (retorna `False` quando `active_thread_id` já existe — claim idempotente), `list_by_tenant(tenant_id, status) -> list[FollowUpEntry]`; `Protocol SessionOutcomeClassifierPort` com `classify(conversation_text, oferta_vigente_texto, oferta_vigente_validade) -> dict` (`{"outcome": ..., "summary": ..., "draft_message": ...}`)

**Checkpoint**: schema e portas prontos — user stories podem começar.

---

## Phase 3: User Story 1 - Histórico de conversa consultável via SQL/API (P1) 🎯 MVP

**Goal**: toda mensagem (cliente + atendente) gravada em `conversation_messages` em paralelo ao checkpoint, consultável via endpoint.

**Independent Test**: enviar mensagens numa conversa de teste e confirmar via `GET /tenants/{id}/conversation-history/{base_thread_id}` que aparecem na ordem certa, isoladas por tenant.

### Tests for User Story 1

- [X] T009 [P] [US1] `tests/unit/test_conversation_message_domain.py`: `role="human"`/`"ai"` aceitos; qualquer outro valor levanta `ValueError`
- [X] T010 [P] [US1] `tests/unit/test_record_conversation_turn_use_case.py`: porta fake — grava par human+ai; quando a porta lança exceção, o use case não propaga (só loga)
- [X] T011 [US1] `tests/integration/test_conversation_history_api.py`: contra Postgres real — enviar 2 mensagens via `/api/v1/chat` e confirmar que `GET /conversation-history/{base_thread_id}` devolve as 4 linhas em ordem cronológica; `base_thread_id` sem mensagens → `200` com `messages: []`; tenant A não vê histórico de tenant B

### Implementation for User Story 1

- [X] T012 [P] [US1] `modules/conversation_history/infrastructure/postgres_conversation_message_repository.py`: implementa `ConversationMessageRepository.save_turn()` (2 `INSERT`) e `list_by_thread()` (`SELECT ... WHERE tenant_id=%s AND base_thread_id=%s ORDER BY created_at ASC`, com `LIMIT`/cursor `before`)
- [X] T013 [US1] `modules/conversation_history/application/record_conversation_turn.py`: `RecordConversationTurnUseCase.execute(tenant_id, base_thread_id, active_thread_id, human_content, ai_content) -> None` — nunca lança (try/except só loga), FR-001/FR-010 (depende de T004, T005, T012)
- [X] T014 [US1] `modules/conversation_history/application/get_conversation_history.py`: `GetConversationHistoryUseCase.execute(tenant_id, base_thread_id, limit, before) -> list[ConversationMessage]`
- [X] T015 [P] [US1] `app/schemas/conversation_history.py`: `ConversationMessageItem` (`role`, `content`, `created_at`), `ConversationHistoryResponse` (`tenant_id`, `base_thread_id`, `messages`)
- [X] T016 [US1] `app/api/v1/endpoints/conversation_history.py`: router `GET /tenants/{tenant_id}/conversation-history/{base_thread_id}` (query `limit`, `before`), `400` se `tenant_id` vazio (depende de T014, T015)
- [X] T017 [US1] `app/main.py`: registra o router de `conversation_history` (mesmo padrão de `global_notification_recipients_router`, prefixo `/api/v1`)
- [X] T018 [US1] `app/api/v1/endpoints/chat.py`: instancia `RecordConversationTurnUseCase` (singleton, mesmo padrão de `check_tenant_limit_use_case`); após o `invoke()` bem-sucedido, chama `execute(tenant_id, thread_id_base, thread_id_grafo, payload.message, resposta_final)`
- [X] T019 [US1] `modules/webhook/whatsapp.py`: mesma chamada, no mesmo ponto (após `invoke()` bem-sucedido)

**Checkpoint**: US1 completa e testável isoladamente (MVP).

---

## Phase 4: User Story 2 - Sessão fechada gera outcome e rascunho de follow-up (P1)

**Goal**: ao expirar, a mesma chamada de LLM de `_summarize_session` também classifica `outcome` e gera `follow_up_draft`, gravando 1 registro idempotente em `follow_up_queue`.

**Independent Test**: encerrar por inatividade uma sessão de teste onde o cliente não respondeu à última pergunta e confirmar que aparece 1 registro `outcome='sem_resposta'` com `draft_message` preenchido.

*Nesta fase o parâmetro de oferta vigente é sempre `None`/vazio (draft nunca cita nenhuma oferta) — a ligação com o dado real do tenant é feita na US3, mantendo o comportamento seguro por padrão desde o primeiro deploy desta story.*

### Tests for User Story 2

- [X] T020 [P] [US2] `tests/unit/test_classify_session_outcome_use_case.py`: porta fake — grava outcome+summary+draft; `draft_message` fica `None` quando `outcome` não é `pensando`/`sem_resposta`; `repository.save()` retornando `False` (claim perdido) não lança; falha do classifier é só logada
- [X] T021 [US2] `tests/integration/test_session_outcome_classification.py`: contra Postgres real (LLM real ou mockado via monkeypatch do adapter) — sessão expirada gera exatamente 1 registro em `follow_up_queue`; reprocessar a mesma `active_thread_id` não duplica (`UNIQUE`); sessão sem mensagens não cria registro; conversa com `ToolMessage` real confirmando agendamento → `outcome='fechado'`, `draft_message` nulo (mesmo cuidado anti-alucinação do EDI-61)

### Implementation for User Story 2

- [X] T022 [P] [US2] `modules/follow_up/infrastructure/postgres_follow_up_queue_repository.py`: implementa `FollowUpQueueRepository.save()` via `INSERT ... ON CONFLICT (active_thread_id) DO NOTHING RETURNING id` (retorna `False` se nenhuma linha afetada)
- [X] T023 [US2] `modules/follow_up/infrastructure/llm_session_outcome_classifier.py`: `LlmSessionOutcomeClassifier` implementa `SessionOutcomeClassifierPort.classify()` — reaproveita o `llm` de `modules/ia/agent_graph.py`; prompt pede `outcome` (um dos 5 valores), `summary`, `draft_message`; instrui explicitamente a regra anti-alucinação de `resultado`/`fechado` (só com `ToolMessage` real, FR-011) e a regra de oferta (nunca citar desconto além do texto fornecido; se `oferta_vigente_texto` vier vazio, instrução explícita "NUNCA mencione desconto/promoção")
- [X] T024 [US2] `modules/follow_up/application/classify_session_outcome.py`: `ClassifySessionOutcomeUseCase.execute(tenant_id, base_thread_id, active_thread_id, conversation_text, oferta_vigente_texto=None, oferta_vigente_validade=None) -> None` — chama o classifier, monta `FollowUpEntry`, grava via repositório; nunca lança (try/except só loga) (depende de T006, T007, T008, T022, T023)
- [X] T025 [US2] `modules/ia/thread_session.py`: `_summarize_session` passa a pedir também `outcome`/`draft_message` no mesmo JSON de resposta (mesmo `llm.invoke`, sem 2ª chamada); `generate_and_store_session_summary` passa a também chamar `ClassifySessionOutcomeUseCase.execute(...)` com o mesmo `conversa_texto` já montado, além do `INSERT` já existente em `chat_thread_summaries` — reaproveita `extract_customer_profile` para personalizar o draft quando possível

**Checkpoint**: US2 completa — outcome/draft gerados com segurança (sem oferta ligada ainda).

---

## Phase 5: User Story 3 - Draft de follow-up nunca inventa desconto (P2)

**Goal**: liga `tenants.oferta_vigente_texto`/`oferta_vigente_validade` reais na classificação da US2, com guardrail testado.

**Independent Test**: gerar draft para tenant sem oferta (nenhuma menção a desconto) e para tenant com oferta válida (cita exatamente o texto cadastrado).

### Tests for User Story 3

- [X] T026 [P] [US3] `tests/unit/test_oferta_vigente_domain.py`: `is_oferta_vigente` — sem texto, sem validade, validade no passado, validade futura, validade igual a hoje
- [X] T027 [P] [US3] `tests/integration/test_tenant_oferta_vigente_retention_api.py`: `PUT`/`GET /tenants/{id}` com `oferta_vigente_texto`, `oferta_vigente_validade`, `retention_days` — persistem e retornam corretamente
- [X] T028 [US3] `tests/integration/test_session_outcome_classification.py` (estende T021): tenant com `oferta_vigente` válida → draft, quando cita oferta, usa exatamente o texto cadastrado; tenant com `oferta_vigente_validade` expirada → nenhuma menção (mesmo resultado de tenant sem oferta)

### Implementation for User Story 3

- [X] T029 [P] [US3] `modules/tenant/tenant_repository.py`: inclui `oferta_vigente_texto`, `oferta_vigente_validade`, `retention_days` em `create_tenant`, `create_tenant_with_prompt`, `get_tenant`, `update_tenant`, `list_tenants`
- [X] T030 [P] [US3] `app/schemas/tenant.py`: os 3 campos novos (`oferta_vigente_texto: str | None`, `oferta_vigente_validade: date | None`, `retention_days: int | None`) em `TenantCreate`/`TenantUpdate`/`TenantResponse`
- [X] T031 [US3] `modules/ia/thread_session.py`: `generate_and_store_session_summary` passa a buscar o tenant (via `TenantService.get_tenant_by_id`, já existente) e repassar `oferta_vigente_texto`/`oferta_vigente_validade` reais para `ClassifySessionOutcomeUseCase.execute(...)` (liga o parâmetro deixado em `None` na Fase 4; depende de T029, T024)

**Checkpoint**: guardrail de oferta completo e testado — US2+US3 juntas entregam o valor central do ticket.

---

## Phase 6: User Story 4 - Fila de follow-up consultável por tenant/status (P2)

**Goal**: endpoint de leitura de `follow_up_queue` para consumidores futuros (worker de disparo, UI de aprovação).

**Independent Test**: com registros de status variados, `GET /tenants/{id}/follow-up-queue?status=pendente` retorna só os pendentes daquele tenant.

### Tests for User Story 4

- [X] T032 [P] [US4] `tests/unit/test_get_follow_up_queue_use_case.py`: porta fake — filtra por `status` quando informado; sem filtro retorna todos os status do tenant
- [X] T033 [US4] `tests/integration/test_follow_up_queue_api.py`: registros de tenants/status diferentes → filtro correto e isolado por tenant; `tenant_id` vazio → `400`; `status` fora do enum → `422`

### Implementation for User Story 4

- [X] T034 [US4] `modules/follow_up/infrastructure/postgres_follow_up_queue_repository.py`: implementa `list_by_tenant(tenant_id, status)` (estende T022)
- [X] T035 [US4] `modules/follow_up/application/get_follow_up_queue.py`: `GetFollowUpQueueUseCase.execute(tenant_id, status) -> list[FollowUpEntry]`
- [X] T036 [P] [US4] `app/schemas/follow_up_queue.py`: `FollowUpEntryItem` (`id`, `base_thread_id`, `outcome`, `summary`, `draft_message`, `status`, `created_at`), `FollowUpQueueResponse`
- [X] T037 [US4] `app/api/v1/endpoints/follow_up_queue.py`: router `GET /tenants/{tenant_id}/follow-up-queue` (query `status` opcional, valida contra o enum)
- [X] T038 [US4] `app/main.py`: registra o router de `follow_up_queue`

**Checkpoint**: fila consultável pronta para os tickets futuros de disparo/UI.

---

## Phase 7: User Story 5 - Expurgo de histórico antigo por tenant (P3)

**Goal**: job standalone que apaga `conversation_messages` mais antigas que `retention_days` do respectivo tenant.

**Independent Test**: tenant com `retention_days` baixo e mensagens antigas de teste → job apaga só as antigas daquele tenant, preservando as recentes e as de outros tenants.

### Tests for User Story 5

- [X] T039 [P] [US5] `tests/unit/test_purge_expired_messages_use_case.py`: porta fake — chama `purge_older_than` só para tenants com `retention_days` não nulo; tenant com `retention_days=None` é ignorado
- [X] T040 [US5] `tests/integration/test_conversation_history_purge.py`: contra Postgres real — mensagens com `created_at` mais antigo que `retention_days` são apagadas; tenant sem `retention_days` não é tocado; tenant B com `retention_days` diferente preservado de acordo com o próprio valor

### Implementation for User Story 5

- [X] T041 [US5] `modules/conversation_history/infrastructure/postgres_conversation_message_repository.py`: implementa `purge_older_than(tenant_id, retention_days)` (`DELETE FROM conversation_messages WHERE tenant_id=%s AND created_at < NOW() - retention_days * INTERVAL '1 day'`) (estende T012)
- [X] T042 [US5] `modules/conversation_history/application/purge_expired_messages.py`: `PurgeExpiredMessagesUseCase.execute() -> None` — lista tenants com `retention_days` não nulo (via `TenantService`), chama `purge_older_than` por tenant, logando total apagado por tenant
- [X] T043 [US5] `workers/conversation_history_purge.py`: entrypoint `python -m workers.conversation_history_purge` — instancia e chama `PurgeExpiredMessagesUseCase().execute()`, script de execução única

**Checkpoint**: todas as 5 user stories entregues e testáveis independentemente.

---

## Phase 8: Polish & Cross-Cutting

- [X] T044 [P] Rodar `specs/011-conversation-history-followup/quickstart.md` de ponta a ponta (migration, testes unit+integration, job de expurgo local, curl dos 2 endpoints novos)
- [X] T045 [P] Revisar logs de falha de `RecordConversationTurnUseCase`/`ClassifySessionOutcomeUseCase`/`PurgeExpiredMessagesUseCase` — confirmar que são grep-áveis (mesmo padrão `CALENDAR_*`/`TENANT_LIMIT_*` já usado no projeto)

---

## Dependencies & Execution Order

- **Setup (Fase 1)** → **Foundational (Fase 2)**: bloqueia tudo.
- **US1 (Fase 3)**: depende só de Foundational. MVP.
- **US2 (Fase 4)**: depende só de Foundational — independente de US1 no código (não lê `conversation_messages`, usa o checkpoint do LangGraph como já faz `_summarize_session`), mas entrega o valor central do ticket junto com US1.
- **US3 (Fase 5)**: depende de US2 (Fase 4, especialmente T024) — liga o parâmetro de oferta que US2 deixa vazio por padrão.
- **US4 (Fase 6)**: depende de US2 (Fase 4, T022) — lê a tabela que US2 escreve.
- **US5 (Fase 7)**: depende só de Foundational (T003) — independente de US1/US2/US3/US4, mas naturalmente só tem valor depois que `conversation_messages` está sendo populada (US1).
- **Polish (Fase 8)**: depende de todas as stories desejadas estarem prontas.

## Implementation Strategy

MVP = Fase 1 + 2 + 3 (US1): histórico consultável funcionando. Incremento seguinte: US2 (outcome/draft seguros por padrão) → US3 (liga oferta real) — as duas juntas entregam o valor central do ticket ("Fundação... resumo e outcome"). US4 expõe a fila para consumidores futuros. US5 fecha o ciclo de retenção e pode ser entregue a qualquer momento após Foundational.
