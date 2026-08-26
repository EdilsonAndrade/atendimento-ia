# Implementation Plan: Limite de mensagens por tenant (mensal)

**Branch**: `edilsonaandrade/edi-63-limite-de-mensagens-por-tenant-mensal-flag-byok-com-chave-de` | **Date**: 2026-08-25 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/010-tenant-message-limit/spec.md`

## Summary

Adiciona um teto mensal de chamadas de LLM por tenant (`monthly_message_limit`), com bloqueio silencioso do agente ao atingir o teto, notificações por e-mail em 50/80/100% (idempotentes por mês), uma fila de retry em Redis Streams + worker para garantir que a contagem em `chat_token_usage` nunca se perca silenciosamente (com dead-letter após N tentativas), e os endpoints REST que uma UI admin (repositório separado `interasisai-web`, fora do escopo desta implementação — Princípio II da constituição) vai consumir para configurar limite/e-mails, ver consumo e dimensionar planos comerciais. Módulo novo `modules/tenant_limits/` (Clean Architecture completa) para a lógica de limite/notificação; `modules/token_usage/` (EDI-60) ganha a resiliência de retry.

## Technical Context

**Language/Version**: Python 3.13
**Primary Dependencies**: FastAPI, psycopg3, `redis` (NOVA dependência — Redis Streams), `smtplib` (stdlib — envio de e-mail)
**Storage**: PostgreSQL (`tenants` ganha colunas; novas tabelas `global_notification_recipients`, `tenant_usage_notifications`) + Redis (fila de retry `token_usage_retry` e dead-letter `token_usage_retry:dead_letter`, Streams com consumer group)
**Testing**: pytest — `tests/unit/` (Domain + Application com portas fake) e `tests/integration/` (Postgres real via `TestClient`/`httpx`, e Redis real para a fila de retry)
**Target Platform**: Linux server, container Docker (mesmo processo da API existente); o worker de retry roda como processo separado (`python -m workers.token_usage_retry_worker`)
**Project Type**: web-service (backend único, Princípio II — sem UI neste repositório; a UI admin do EDI-63 fica para o repositório `interasisai-web`, fora de escopo aqui)
**Performance Goals**: checagem de limite (1 COUNT indexado) e cálculo de milestone (1-3 INSERT ON CONFLICT idempotentes) não podem adicionar latência perceptível à resposta ao cliente; a checagem de bloqueio roda ANTES de qualquer chamada ao LLM, então uma mensagem bloqueada custa zero chamadas de LLM
**Constraints**: módulo `tenant_limits/` é NOVO → Princípios III e VI NON-NEGOTIABLE desde o primeiro commit; `token_usage/` já é um módulo Clean Architecture (EDI-60), a resiliência se encaixa nas camadas existentes; `tenant/` é módulo legado (grandfathered) — a extensão de schema usa os métodos públicos existentes de `TenantRepository`/`TenantService`, sem burlar a fronteira
**Scale/Scope**: 1 migration nova, 1 módulo novo completo (`tenant_limits/`) + extensão de `token_usage/` (retry queue + worker) + extensão pontual de `tenant/` (schema) + 2 pontos de integração no request-path (`app/api/v1/endpoints/chat.py`, `modules/webhook/whatsapp.py`) + ~6 endpoints REST novos/estendidos

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Avaliação |
| -- | -- |
| I. Multi-Tenant Isolation | **PASS** — toda checagem/contagem/claim de notificação é sempre filtrada por `tenant_id` explícito (o mesmo `configurable.tenant_id` já usado pelo resto do grafo); `global_notification_recipients` é intencionalmente global (não por tenant, por design do ticket), nunca misturado com dado de conversa. |
| II. API-First, Backend-Only | **PASS** — nenhuma tela é criada neste repositório (decisão confirmada com o usuário); tudo que a UI (`interasisai-web`) vai precisar é exposto como endpoint versionado com schema Pydantic (limite/e-mails do tenant, CRUD de destinatários globais, consumo do mês, config da calculadora). |
| III. Modular Clean Architecture | **PASS (módulo novo `tenant_limits/`, sem grace period)** — Domain (regra pura de limite/threshold), Application (`CheckTenantLimitUseCase`, `NotifyUsageMilestonesUseCase` dependendo só de `Protocol`s), Infrastructure (repositórios Postgres, `SmtpEmailSender`, worker Redis). `app/api/v1/endpoints/chat.py` e `modules/webhook/whatsapp.py` (Interface/legado) só chamam os 2 use cases públicos, nunca a Infrastructure diretamente. A extensão de `modules/token_usage/` (fila de retry) segue as camadas já estabelecidas pelo EDI-60. |
| IV. Security & Guardrails by Default | **N/A/PASS** — nenhuma mudança de autenticação; os novos endpoints de tenant seguem o mesmo padrão (sem auth adicional) já usado por `/tenants` hoje; nenhum dado sensível novo é exposto (e-mails de notificação já são dado administrativo, não de cliente final). |
| V. Asynchronous Processing | **PASS** — a checagem de bloqueio e o claim/e-mail de milestone são leves (1 SELECT + até 3 INSERT ON CONFLICT), mesmo padrão de "overhead desprezível" já aceito para `record_llm_usage` (EDI-60); o envio de e-mail em si é raro (no máximo 3x por tenant por mês) e protegido por try/except que nunca bloqueia a resposta — não se qualifica como "AI-model-bound work" que exigiria background task. O reprocessamento da fila de retry roda inteiramente FORA do request/response cycle, em um worker dedicado (exatamente o padrão que o Princípio V pede para trabalho pesado/assíncrono). |
| VI. Test-First Discipline | **PASS (planejado)** — Phase 2 gera testes unitários (Domain puro + Application com portas fake) e de integração (repositórios Postgres reais via `httpx`/`TestClient`, cobrindo happy path + isolamento multi-tenant + erro; fila de retry contra Redis real) antes/junto da implementação. |

Nenhuma violação exige entrada na tabela de Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/010-tenant-message-limit/
├── plan.md              # Este arquivo
├── research.md          # Fase 0 — decisões técnicas
├── data-model.md        # Fase 1 — schema + entidades
├── quickstart.md         # Fase 1 — comandos de dev/teste
├── contracts/            # Fase 1 — contratos dos endpoints REST novos/estendidos
└── tasks.md              # Fase 2 (gerado a seguir)
```

### Source Code (repository root)

```text
migrations/versions/
└── 0008_tenant_message_limit.py      # NOVO — tenants.monthly_message_limit/notification_emails,
                                       #   global_notification_recipients, tenant_usage_notifications

modules/tenant_limits/                # NOVO módulo (Clean Architecture completa)
├── __init__.py
├── domain/
│   ├── __init__.py
│   └── usage_policy.py               # THRESHOLDS, is_over_limit(), threshold_count()
├── application/
│   ├── __init__.py
│   ├── ports.py                      # Protocols: TenantLimitConfigPort, UsageCounterPort,
│   │                                  #   NotificationClaimPort, GlobalRecipientsPort, EmailSenderPort
│   ├── check_tenant_limit.py         # CheckTenantLimitUseCase (fail-open em erro)
│   └── notify_usage_milestones.py    # NotifyUsageMilestonesUseCase (idempotente por mês/marco)
└── infrastructure/
    ├── __init__.py
    ├── postgres_tenant_limit_config.py    # lê monthly_message_limit/notification_emails via TenantService
    ├── postgres_usage_counter.py          # COUNT(*) em chat_token_usage por tenant/mês
    ├── postgres_notification_claim.py     # INSERT ON CONFLICT DO NOTHING em tenant_usage_notifications
    ├── postgres_global_recipients.py      # CRUD de global_notification_recipients
    └── smtp_email_sender.py               # SmtpEmailSender (stdlib smtplib)

modules/token_usage/                  # ESTENDIDO (resiliência, EDI-63 sobre EDI-60)
├── application/
│   ├── ports.py                      # + Protocol RetryQueuePort
│   └── record_token_usage.py         # MODIFICADO — publica na retry queue quando o INSERT falha
└── infrastructure/
    ├── redis_retry_queue.py          # NOVO — RedisStreamRetryQueue (XADD)
    └── retry_worker.py               # NOVO — TokenUsageRetryWorker (XREADGROUP/XACK/XPENDING, dead-letter)

workers/
└── token_usage_retry_worker.py       # NOVO — entrypoint `python -m workers.token_usage_retry_worker`

app/schemas/tenant.py                 # MODIFICADO — monthly_message_limit, notification_emails,
                                       #   TenantUsageResponse, TenantMessageLimitConfigResponse
app/schemas/global_notification_recipient.py  # NOVO

app/api/v1/endpoints/tenant.py        # MODIFICADO — GET /{id}/usage, GET /message-limit-config
app/api/v1/endpoints/global_notification_recipients.py  # NOVO — CRUD

app/api/v1/endpoints/chat.py          # MODIFICADO — checagem de bloqueio antes do invoke,
                                       #   notificação de milestone depois
modules/webhook/whatsapp.py           # MODIFICADO — idem chat.py

modules/tenant/tenant_repository.py   # MODIFICADO — colunas novas nas queries existentes (create/update/get/list)
modules/tenant/tenant_service.py      # inalterado (repassa os dicts já com os novos campos)

tests/unit/
├── test_tenant_limits_domain.py
├── test_check_tenant_limit_use_case.py
├── test_notify_usage_milestones_use_case.py
└── test_record_token_usage_use_case.py    # ESTENDIDO — publica na retry queue em falha

tests/integration/
├── test_tenant_message_limit_api.py           # limite + e-mails via PUT/GET /tenants/{id}
├── test_tenant_usage_endpoint_api.py           # GET /tenants/{id}/usage
├── test_global_notification_recipients_api.py  # CRUD
├── test_tenant_limit_enforcement.py             # CheckTenantLimitUseCase contra Postgres real
├── test_notification_milestone_idempotency.py   # claim idempotente contra Postgres real
└── test_token_usage_retry_queue.py              # publish/consume contra Redis real
```

**Structure Decision**: `modules/tenant_limits/` segue o mesmo padrão Clean Architecture completo inaugurado pelo `modules/token_usage/` (EDI-60) — módulo net-new, sem grace period. A extensão do `token_usage/` reaproveita as camadas já existentes (só adiciona uma porta e dois adapters de Infrastructure). `modules/tenant/` permanece legado (grandfathered): a extensão de schema usa `TenantRepository`/`TenantService` já existentes, sem introduzir uma nova camada ali.

## Complexity Tracking

*Nenhuma violação da Constituição exige justificativa nesta tabela.*
