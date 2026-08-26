# Tasks: Limite de mensagens por tenant (mensal)

**Input**: Design documents from `specs/010-tenant-message-limit/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: incluídos (Princípio VI da constituição é NON-NEGOTIABLE para módulo novo).

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [ ] T001 Adicionar `redis` ao `requirements.txt`

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: bloqueia todas as user stories.

- [ ] T002 Migration `migrations/versions/0008_tenant_message_limit.py`: `ALTER TABLE tenants ADD COLUMN monthly_message_limit INTEGER`, `ADD COLUMN notification_emails TEXT[]`; `CREATE TABLE global_notification_recipients`; `CREATE TABLE tenant_usage_notifications` com `UNIQUE (tenant_id, year_month, milestone)` (ver data-model.md)
- [ ] T003 [P] `modules/tenant_limits/__init__.py`, `domain/__init__.py`, `application/__init__.py`, `infrastructure/__init__.py` (esqueleto do módulo novo)
- [ ] T004 [P] `modules/tenant_limits/domain/usage_policy.py`: `THRESHOLDS = (50, 80, 100)`, `is_over_limit(current_month_calls, monthly_message_limit) -> bool`, `threshold_count(monthly_message_limit, pct) -> int` (ceil), `percentage_used(current_month_calls, monthly_message_limit) -> float | None`
- [ ] T005 `modules/tenant_limits/application/ports.py`: Protocols `TenantLimitConfigPort`, `UsageCounterPort`, `NotificationClaimPort`, `GlobalRecipientsPort`, `EmailSenderPort`
- [ ] T006 [P] `modules/tenant/tenant_repository.py`: incluir `monthly_message_limit`, `notification_emails` em `create_tenant`, `create_tenant_with_prompt`, `get_tenant`, `update_tenant`, `list_tenants` (SELECT/INSERT/UPDATE + dict de retorno)
- [ ] T007 [P] `app/schemas/tenant.py`: `monthly_message_limit: int | None`, `notification_emails: list[EmailStr]` em `TenantCreate`/`TenantUpdate`/`TenantResponse`

**Checkpoint**: schema e portas prontos — user stories podem começar.

---

## Phase 3: User Story 1 - Tenant que atinge o limite mensal para de gerar respostas (P1) 🎯 MVP

**Goal**: bloqueio silencioso quando o tenant atinge `monthly_message_limit`, zero chamadas de LLM na mensagem bloqueada.

**Independent Test**: configurar `monthly_message_limit` baixo, gerar chamadas até atingir, confirmar que a próxima mensagem não gera resposta nem linha nova em `chat_token_usage`.

### Tests for User Story 1

- [ ] T008 [P] [US1] `tests/unit/test_tenant_limits_domain.py`: `is_over_limit`/`threshold_count`/`percentage_used` (limite `None`, limite exato, acima/abaixo)
- [ ] T009 [P] [US1] `tests/unit/test_check_tenant_limit_use_case.py`: portas fake — bloqueia quando `count >= limit`; não bloqueia quando `limit is None`; fail-open quando a porta de contagem lança exceção; loga `TENANT_LIMIT_BLOCKED` quando bloqueado
- [ ] T010 [US1] `tests/integration/test_tenant_limit_enforcement.py`: contra Postgres real — cria tenant com limite baixo, insere linhas em `chat_token_usage` diretamente, confirma `CheckTenantLimitUseCase` bloqueia; tenant B (outro `tenant_id`) não é afetado (isolamento multi-tenant)

### Implementation for User Story 1

- [ ] T011 [P] [US1] `modules/tenant_limits/infrastructure/postgres_tenant_limit_config.py`: implementa `TenantLimitConfigPort` usando `TenantService.get_tenant_by_id` (não acessa `tenants` direto — módulo `tenant/` é legado, ver Governance > Legacy Migration Policy)
- [ ] T012 [P] [US1] `modules/tenant_limits/infrastructure/postgres_usage_counter.py`: implementa `UsageCounterPort.count_current_month(tenant_id)` — `COUNT(*) FROM chat_token_usage WHERE tenant_id = %s AND created_at >= date_trunc('month', NOW())`
- [ ] T013 [US1] `modules/tenant_limits/application/check_tenant_limit.py`: `CheckTenantLimitUseCase.execute(tenant_id, thread_id) -> bool` — fail-open em exceção, loga `TENANT_LIMIT_BLOCKED tenant_id=... thread_id=... current_month_calls=... monthly_message_limit=...` quando bloqueado (depende de T011, T012)
- [ ] T014 [US1] `app/api/v1/endpoints/chat.py`: instancia `CheckTenantLimitUseCase` (singleton, mesmo padrão de `graph_app`); em `chat_interaction`, chama `execute()` antes do `_invoke_graph`; se bloqueado, devolve `ChatResponse(tenant_id=tenant_id, status="success", response="")` sem invocar o grafo
- [ ] T015 [US1] `modules/webhook/whatsapp.py`: mesma checagem em `processar_mensagem_e_responder`, ANTES de iniciar `typing_task`; se bloqueado, sai sem enviar nada (mesmo caminho que `resposta_final` vazio já usa)
- [ ] T016 [US1] `tests/integration/test_tenant_message_limit_api.py`: happy path via `POST`/`PUT /tenants` com `monthly_message_limit`/`notification_emails`, `GET` devolve os campos; erro de validação (e-mail malformado → `422`)

**Checkpoint**: US1 completa e testável isoladamente.

---

## Phase 4: User Story 4 - Contagem de uso não se perde em falha transitória (P2)

**Goal**: falha no INSERT de `chat_token_usage` vai para fila de retry (Redis Streams); worker reprocessa e move para dead-letter após N tentativas.

**Independent Test**: simular falha no repositório, confirmar publish na stream; rodar o worker, confirmar gravação + XACK; simular falha permanente, confirmar dead-letter após N tentativas.

*(Priorizada antes de US2/US3 porque US2 depende de contagem confiável — mesma ordem lógica do research.md, não é P1 mas é pré-requisito de qualidade para as métricas usadas pelas próximas stories.)*

### Tests for User Story 4

- [ ] T017 [P] [US4] `tests/unit/test_record_token_usage_use_case.py` (estende o existente do EDI-60): quando `repository.save()` lança exceção E uma `retry_queue` fake foi injetada, `retry_queue.publish(record)` é chamado com o mesmo `TokenUsageRecord`; sem `retry_queue` injetada, comportamento antigo (só loga) é preservado
- [ ] T018 [P] [US4] `tests/integration/test_token_usage_retry_queue.py`: contra Redis real — `RedisStreamRetryQueue.publish()` grava na stream; o worker consome, grava no Postgres (repositório real) e dá XACK; uma entrada que falha repetidamente é movida para `token_usage_retry:dead_letter` após `TOKEN_USAGE_RETRY_MAX_ATTEMPTS`, preservando `tenant_id`/`thread_id`/timestamp original; reiniciar o worker no meio do processamento (PEL) reprocessa a entrada pendente sem duplicar

### Implementation for User Story 4

- [ ] T019 [P] [US4] `modules/token_usage/application/ports.py`: adiciona `Protocol RetryQueuePort` com `publish(record: TokenUsageRecord) -> None`
- [ ] T020 [US4] `modules/token_usage/application/record_token_usage.py`: aceita `retry_queue: RetryQueuePort | None = None`; isola o `self._repository.save(record)` em seu próprio try/except; na falha, chama `retry_queue.publish(record)` (se houver), também protegido por try/except que só loga
- [ ] T021 [P] [US4] `modules/token_usage/infrastructure/redis_retry_queue.py`: `RedisStreamRetryQueue` (conecta via `REDIS_URL`), `publish()` faz `XADD token_usage_retry`, serializando os campos de `TokenUsageRecord` como strings
- [ ] T022 [US4] `modules/token_usage/infrastructure/retry_worker.py`: `TokenUsageRetryWorker` — na inicialização, cria o consumer group se não existir; `run_once()`: primeiro reclama/processa entradas pendentes do PEL (`XREADGROUP` com ID `"0"`), depois lê novas (`XREADGROUP` com ID `">"`); por entrada, tenta `PostgresTokenUsageRepository.save()`; sucesso → `XACK`; falha → se `XPENDING` mostra `delivery_count > TOKEN_USAGE_RETRY_MAX_ATTEMPTS`, publica em `token_usage_retry:dead_letter` (preservando `tenant_id`/horário original/`thread_id`) e dá `XACK` na entrada original; `run_forever()` chama `run_once()` em loop com um pequeno sleep
- [ ] T023 [US4] `workers/token_usage_retry_worker.py`: entrypoint `python -m workers.token_usage_retry_worker` chamando `TokenUsageRetryWorker().run_forever()`
- [ ] T024 [US4] `modules/ia/agent_graph.py`: injeta `RedisStreamRetryQueue()` no `_token_usage_use_case` (mesma linha onde `RecordTokenUsageUseCase(PostgresTokenUsageRepository())` é instanciado hoje)

**Checkpoint**: US4 completa — contagem de uso resiliente a falha transitória do Postgres.

---

## Phase 5: User Story 2 - Tenant e InterasisAI recebem avisos progressivos (P2)

**Goal**: e-mails de 50/80/100% idempotentes por mês; 100% também vai para `global_notification_recipients`.

**Independent Test**: cruzar cada marco e confirmar exatamente 1 e-mail por marco, para os destinatários certos.

### Tests for User Story 2

- [ ] T025 [P] [US2] `tests/unit/test_notify_usage_milestones_use_case.py`: portas fake — sem limite configurado, não faz nada; cruzar 50% chama `claim(50)` e, se `claim` devolve `True`, envia e-mail só a `notification_emails`; cruzar 100% envia a `notification_emails` E `global_recipients`; `claim` devolvendo `False` (já enviado) não reenvia; rajada que cruza 50% e 80% na mesma chamada envia os dois e-mails, em ordem
- [ ] T026 [US2] `tests/integration/test_notification_milestone_idempotency.py`: contra Postgres real — duas chamadas concorrentes/sequenciais no mesmo marco/mês só resultam em 1 linha em `tenant_usage_notifications` (constraint `UNIQUE` fazendo o trabalho)

### Implementation for User Story 2

- [ ] T027 [P] [US2] `modules/tenant_limits/infrastructure/postgres_notification_claim.py`: implementa `NotificationClaimPort.try_claim(tenant_id, year_month, milestone) -> bool` via `INSERT ... ON CONFLICT DO NOTHING RETURNING id`
- [ ] T028 [P] [US2] `modules/tenant_limits/infrastructure/postgres_global_recipients.py`: implementa `GlobalRecipientsPort.list_active_emails() -> list[str]` (fallback `["contato@interasisai.com.br"]` se lista vazia)
- [ ] T029 [P] [US2] `modules/tenant_limits/infrastructure/smtp_email_sender.py`: `SmtpEmailSender` implementa `EmailSenderPort.send(to, subject, body)` via `smtplib` + env vars (`SMTP_HOST` etc., research.md §6); nunca lança — loga e engole falha de envio
- [ ] T030 [US2] `modules/tenant_limits/application/notify_usage_milestones.py`: `NotifyUsageMilestonesUseCase.execute(tenant_id)` — sem limite, retorna; para cada marco em `THRESHOLDS` cujo `current_month_calls >= threshold_count(...)`, tenta o claim; se ganhou o claim, monta o corpo (textos do ticket: "Você já usou X de Y mensagens...", etc.) e envia — 50/80 só para `notification_emails`; 100 para `notification_emails` + `global_recipients` (depende de T027, T028, T029, T004)
- [ ] T031 [US2] `app/api/v1/endpoints/chat.py` e `modules/webhook/whatsapp.py`: depois do `invoke()` bem-sucedido (não bloqueado), chama `NotifyUsageMilestonesUseCase.execute(tenant_id)` (fire-and-forget, já é defensivo internamente)

**Checkpoint**: US1 + US4 + US2 funcionam juntas — bloqueio, resiliência de contagem e avisos.

---

## Phase 6: User Story 3 - Admin configura limite, e-mails e acompanha consumo (P3)

**Goal**: endpoints REST que a UI (`interasisai-web`, fora deste repo) vai consumir — CRUD de limite/e-mails já cobertos na Fase 2/3; faltam consumo e CRUD de destinatários globais.

**Independent Test**: `GET /tenants/{id}/usage` reflete o uso real; CRUD de `global-notification-recipients` funciona; `GET /tenants/message-limit-config` devolve as razões vigentes.

### Tests for User Story 3

- [ ] T032 [P] [US3] `tests/integration/test_tenant_usage_endpoint_api.py`: `GET /tenants/{id}/usage` — sem limite (`percentage_used: null`), com limite parcial, no limite (`blocked: true`), tenant inexistente (`404`)
- [ ] T033 [P] [US3] `tests/integration/test_global_notification_recipients_api.py`: CRUD completo; `POST` duplicado → `409 EMAIL_ALREADY_EXISTS`; `PUT`/`DELETE` inexistente → `404`

### Implementation for User Story 3

- [ ] T034 [P] [US3] `app/schemas/tenant.py`: `TenantUsageResponse`, `TenantMessageLimitConfigResponse`
- [ ] T035 [P] [US3] `app/schemas/global_notification_recipient.py`: `GlobalRecipientCreate`, `GlobalRecipientUpdate`, `GlobalRecipientResponse`
- [ ] T036 [US3] `app/api/v1/endpoints/tenant.py`: `GET /{tenant_id}/usage` (usa `UsageCounterPort` + `TenantLimitConfigPort` já existentes) e `GET /message-limit-config` (lê as env vars de razão)
- [ ] T037 [US3] `modules/tenant_limits/infrastructure/postgres_global_recipients.py`: métodos `create`, `update`, `delete`, `list_all` (estende T028)
- [ ] T038 [US3] `app/api/v1/endpoints/global_notification_recipients.py`: router `GET`/`POST`/`PUT`/`DELETE` (contracts/tenant-message-limit.md)
- [ ] T039 [US3] `app/api/v1/router.py`: registra o novo router de `global_notification_recipients`

**Checkpoint**: todos os endpoints que a UI admin (repo separado) vai consumir estão prontos.

---

## Phase 7: Polish & Cross-Cutting

- [ ] T040 [P] Atualizar `docker-compose-local.yml`/`docker-compose.yml` com um comentário/exemplo de serviço para o worker (`command: python -m workers.token_usage_retry_worker`) — documentação, não obrigatório para dev local rodar o worker manualmente
- [ ] T041 Rodar `specs/010-tenant-message-limit/quickstart.md` de ponta a ponta (migration, testes unit+integration, worker local, bloqueio manual via curl)
- [ ] T042 [P] Revisar logs `TENANT_LIMIT_BLOCKED` e do worker de dead-letter — confirmar que são grep-áveis (mesmo padrão `CALENDAR_*` do EDI-61)

---

## Dependencies & Execution Order

- **Setup (Fase 1)** → **Foundational (Fase 2)**: bloqueia tudo.
- **US1 (Fase 3)**: depende só de Foundational. MVP.
- **US4 (Fase 4)**: depende só de Foundational (independente de US1) — priorizada antes de US2 porque US2 consome a MESMA contagem que US4 protege, mas nenhuma dependência de código direta entre elas.
- **US2 (Fase 5)**: depende de Foundational; usa a mesma infra de contagem de US1 (T012), mas é uma story separada — pode ser implementada em paralelo a US1 por outra pessoa, só integra em T031.
- **US3 (Fase 6)**: depende de Foundational + reaproveita T011/T012 (US1) e T028 (US2); é majoritariamente exposição de endpoints sobre o que já existe.
- **Polish (Fase 7)**: depende de todas as stories desejadas estarem prontas.

## Implementation Strategy

MVP = Fase 1 + 2 + 3 (US1): bloqueio funcionando, sem avisos nem resiliência de contagem ainda. Incremento seguinte: US4 (contagem confiável) antes de US2 (avisos), para os avisos já nascerem sobre uma contagem resiliente. US3 fecha os endpoints que a UI separada vai consumir.
