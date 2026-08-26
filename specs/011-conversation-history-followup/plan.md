# Implementation Plan: Histórico consultável, resumo e outcome por sessão (Fundação de Follow-up)

**Branch**: `edilsonaandrade/edi-53-follow-up-fundacao-historico-consultavel-resumo-e-outcome` | **Date**: 2026-08-26 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/011-conversation-history-followup/spec.md`

## Summary

Cria uma camada de histórico de conversa estruturado e consultável (`conversation_messages`), gravada em paralelo ao checkpoint do LangGraph nos dois pontos de entrada de mensagem (`/chat`, webhook WhatsApp). Estende a chamada de LLM que já roda no fechamento de sessão (`generate_and_store_session_summary`, EDI-59/61) para também classificar um `outcome` e gerar um `follow_up_draft` (com guardrail para nunca inventar desconto fora de `tenants.oferta_vigente`), gravando-os em uma nova fila `follow_up_queue`. Adiciona `oferta_vigente_texto`/`oferta_vigente_validade`/`retention_days` a `tenants`, um job de expurgo standalone para `conversation_messages`, e dois endpoints de leitura (histórico por thread, fila de follow-up por status). Dois módulos novos, Clean Architecture completa: `modules/conversation_history/` e `modules/follow_up/`.

## Technical Context

**Language/Version**: Python 3.13
**Primary Dependencies**: FastAPI, psycopg3, LangChain/LangGraph (LLM já configurado em `modules/ia/agent_graph.py`, reaproveitado — nenhuma dependência nova)
**Storage**: PostgreSQL (`tenants` ganha 3 colunas; tabelas novas `conversation_messages`, `follow_up_queue`)
**Testing**: pytest — `tests/unit/` (Domain + Application com portas fake) e `tests/integration/` (Postgres real via `TestClient`/`httpx`)
**Target Platform**: Linux server, container Docker (mesmo processo da API existente); o job de expurgo roda como script standalone (`python -m workers.conversation_history_purge`), agendado por cron externo (infraestrutura, fora do escopo desta implementação)
**Project Type**: web-service (backend único, Princípio II — sem UI neste repositório; endpoints de leitura desta feature são consumidos por tickets futuros de worker/UI, fora de escopo aqui)
**Performance Goals**: gravação de `conversation_messages` (2 INSERTs por turno) não pode adicionar latência perceptível — mesmo perfil de custo já aceito para `record_llm_usage` (EDI-60); a classificação de outcome/draft roda em background (thread daemon, mesmo padrão de `generate_and_store_session_summary`), nunca no caminho de resposta ao cliente
**Constraints**: `conversation_history/` e `follow_up/` são módulos NOVOS → Princípios III e VI NON-NEGOTIABLE desde o primeiro commit; `modules/ia/thread_session.py` é módulo legado (grandfathered) — a chamada ao novo `ClassifySessionOutcomeUseCase` respeita a Política de Migração Legada (chama método público do módulo novo, não acessa `infrastructure.connection` diretamente para a tabela nova); `modules/tenant/` é módulo legado — a extensão de schema usa os métodos públicos existentes de `TenantRepository`/`TenantService`, sem burlar a fronteira
**Scale/Scope**: 1 migration nova, 2 módulos novos completos (`conversation_history/`, `follow_up/`), extensão pontual de `modules/ia/thread_session.py` (1 chamada de use case a mais) e `modules/tenant/` (schema), 2 pontos de integração no request-path (`app/api/v1/endpoints/chat.py`, `modules/webhook/whatsapp.py`), 1 script de expurgo (`workers/conversation_history_purge.py`), 2 endpoints REST novos + extensão de `TenantCreate`/`TenantUpdate`/`TenantResponse`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Princípio | Avaliação |
| -- | -- |
| I. Multi-Tenant Isolation | **PASS** — `conversation_messages` e `follow_up_queue` sempre gravadas/lidas com `tenant_id` explícito (o mesmo `configurable.tenant_id` já usado pelo resto do grafo); os dois endpoints de leitura exigem `tenant_id` no path e filtram por ele; o job de expurgo aplica `retention_days` estritamente por tenant, nunca aplicando o valor de um tenant a outro. |
| II. API-First, Backend-Only | **PASS** — nenhuma UI é criada; os dois endpoints de leitura (histórico, fila de follow-up) são a superfície versionada que tickets futuros (worker de disparo, UI de aprovação) vão consumir, com schema Pydantic. |
| III. Modular Clean Architecture | **PASS (2 módulos novos, sem grace period)** — `conversation_history/`: Domain (`ConversationMessage`), Application (`RecordConversationTurnUseCase`, `GetConversationHistoryUseCase`, `PurgeExpiredMessagesUseCase` dependendo só de `Protocol`s), Infrastructure (`PostgresConversationMessageRepository`). `follow_up/`: Domain (`FollowUpEntry`, `is_oferta_vigente`), Application (`ClassifySessionOutcomeUseCase`, `GetFollowUpQueueUseCase`), Infrastructure (`PostgresFollowUpQueueRepository`, adapter que chama o `llm` já existente). `app/api/v1/endpoints/*` e `modules/ia/thread_session.py` (Interface/legado) só chamam os use cases públicos, nunca a Infrastructure diretamente. |
| IV. Security & Guardrails by Default | **PASS** — os novos endpoints seguem o mesmo padrão (sem auth adicional) já usado por `/tenants/{id}/usage`; o guardrail de `oferta_vigente` no prompt de `follow_up_draft` é revisado como mudança de prompt/guardrail de IA (mesmo cuidado do EDI-61) antes de aplicar a qualquer tenant — ver research.md §3. Nenhum dado sensível novo é exposto (histórico de conversa já existe hoje via checkpoint; esta feature só o torna consultável pelo próprio tenant dono do dado). |
| V. Asynchronous Processing | **PASS** — a gravação de `conversation_messages` é 2 INSERTs rápidos, mesmo perfil já aceito para `record_llm_usage`, síncrono no request-path; a classificação de outcome/draft É trabalho AI-model-bound (chamada ao LLM) e já roda inteiramente fora do request/response cycle (thread daemon disparada por `resolve_active_thread_id`, padrão pré-existente do EDI-59, apenas estendido). O job de expurgo roda como script separado, fora do processo da API. |
| VI. Test-First Discipline | **PASS (planejado)** — Phase 2 gera testes unitários (Domain puro + Application com portas fake) e de integração (Postgres real via `httpx`/`TestClient`, cobrindo happy path + isolamento multi-tenant + idempotência + guardrail de oferta) antes/junto da implementação. |

Nenhuma violação exige entrada na tabela de Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/011-conversation-history-followup/
├── plan.md               # Este arquivo
├── research.md            # Fase 0 — decisões técnicas
├── data-model.md          # Fase 1 — schema + entidades
├── quickstart.md          # Fase 1 — comandos de dev/teste
├── contracts/             # Fase 1 — contratos dos endpoints REST novos
└── tasks.md               # Fase 2 (gerado a seguir)
```

### Source Code (repository root)

```text
migrations/versions/
└── 0009_conversation_followup.py     # NOVO — tenants.oferta_vigente_texto/validade/retention_days,
                                     #   conversation_messages, follow_up_queue

modules/conversation_history/          # NOVO módulo (Clean Architecture completa)
├── __init__.py
├── domain/
│   ├── __init__.py
│   └── conversation_message.py       # ConversationMessage (valida role human/ai)
├── application/
│   ├── __init__.py
│   ├── ports.py                      # Protocol ConversationMessageRepository
│   ├── record_conversation_turn.py   # RecordConversationTurnUseCase (fail-safe: nunca lança)
│   ├── get_conversation_history.py   # GetConversationHistoryUseCase (paginação por cursor)
│   └── purge_expired_messages.py     # PurgeExpiredMessagesUseCase (varre tenants com retention_days)
└── infrastructure/
    ├── __init__.py
    └── postgres_conversation_message_repository.py

modules/follow_up/                     # NOVO módulo (Clean Architecture completa)
├── __init__.py
├── domain/
│   ├── __init__.py
│   ├── follow_up_entry.py            # FollowUpEntry, Outcome, Status (enums Python)
│   └── oferta_vigente.py             # is_oferta_vigente() — regra pura, unit-testável
├── application/
│   ├── __init__.py
│   ├── ports.py                      # Protocols: FollowUpQueueRepository, SessionOutcomeClassifierPort
│   ├── classify_session_outcome.py   # ClassifySessionOutcomeUseCase (idempotente por active_thread_id)
│   └── get_follow_up_queue.py        # GetFollowUpQueueUseCase
└── infrastructure/
    ├── __init__.py
    ├── postgres_follow_up_queue_repository.py
    └── llm_session_outcome_classifier.py  # adapter que chama o `llm` de modules/ia/agent_graph.py

workers/
└── conversation_history_purge.py     # NOVO — entrypoint `python -m workers.conversation_history_purge`

modules/ia/thread_session.py          # MODIFICADO — _summarize_session ganha outcome/follow_up_draft
                                       #   no mesmo prompt/chamada; generate_and_store_session_summary
                                       #   chama ClassifySessionOutcomeUseCase.execute(...) além do INSERT
                                       #   já existente em chat_thread_summaries

app/schemas/tenant.py                 # MODIFICADO — oferta_vigente_texto, oferta_vigente_validade,
                                       #   retention_days em TenantCreate/TenantUpdate/TenantResponse
app/schemas/conversation_history.py   # NOVO — ConversationHistoryResponse
app/schemas/follow_up_queue.py        # NOVO — FollowUpQueueResponse

app/api/v1/endpoints/conversation_history.py  # NOVO — GET /tenants/{id}/conversation-history/{base_thread_id}
app/api/v1/endpoints/follow_up_queue.py       # NOVO — GET /tenants/{id}/follow-up-queue

app/main.py                           # MODIFICADO — registra os 2 routers novos (mesmo padrão de
                                       #   global_notification_recipients_router)

app/api/v1/endpoints/chat.py          # MODIFICADO — grava turno em conversation_messages após invoke()
modules/webhook/whatsapp.py           # MODIFICADO — idem chat.py

modules/tenant/tenant_repository.py   # MODIFICADO — colunas novas nas queries existentes (create/update/get/list)
modules/tenant/tenant_service.py      # inalterado (repassa os dicts já com os novos campos)

tests/unit/
├── test_conversation_message_domain.py
├── test_oferta_vigente_domain.py
├── test_record_conversation_turn_use_case.py
├── test_purge_expired_messages_use_case.py
├── test_classify_session_outcome_use_case.py
└── test_get_follow_up_queue_use_case.py

tests/integration/
├── test_conversation_history_api.py           # GET /conversation-history/{base_thread_id}
├── test_follow_up_queue_api.py                 # GET /follow-up-queue
├── test_session_outcome_classification.py       # fechamento de sessão real → follow_up_queue (+ idempotência)
├── test_conversation_history_purge.py           # job de expurgo contra Postgres real
└── test_tenant_oferta_vigente_retention_api.py  # PUT/GET /tenants/{id} com os 3 campos novos
```

**Structure Decision**: `modules/conversation_history/` e `modules/follow_up/` seguem o mesmo padrão Clean Architecture completo inaugurado por `modules/token_usage/` (EDI-60) — dois módulos net-new, sem grace period, separados por bounded context (ver research.md §7). `modules/ia/` e `modules/tenant/` permanecem legados (grandfathered): a extensão de `thread_session.py` chama o use case público do módulo novo em vez de SQL raw ali mesmo; a extensão de schema de `tenant/` usa `TenantRepository`/`TenantService` já existentes.

## Complexity Tracking

*Nenhuma violação da Constituição exige justificativa nesta tabela.*
