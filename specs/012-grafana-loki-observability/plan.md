# Implementation Plan: Grafana + Loki Observability

**Branch**: `012-grafana-loki-observability` | **Date**: 2026-08-26 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/012-grafana-loki-observability/spec.md`

**Note**: This plan follows the workflow in `.specify/templates/plan-template.md`.

## Summary

Instrumentar o sistema de agentes com logging estruturado enviado em tempo real para Grafana Loki, permitindo auditoria completa de operações (início, fim, erros, decisões) com contexto de tenant, thread, método e linha de código. Dados sensíveis (senhas, tokens) serão omitidos. Implementação usa `requests` library para enviar logs via HTTP Bearer token ao Loki, com labels estruturados: `tenant="ID|NAME" operation="..." method="..." line="..." agent="..."`.

## Technical Context

**Language/Version**: Python 3.11+ (current project baseline)  
**Primary Dependencies**: 
- `requests` (HTTP client for Loki push API)
- `logging` (Python standard library - no external logging framework required initially)
- `pydantic` v2 (for structured event schemas)

**Storage**: Grafana Loki (SaaS, free tier: 50GB logs/month)  
**Testing**: pytest (existing project baseline) + integration tests against real Loki or mock HTTP responses  
**Target Platform**: Linux containers (existing deployment topology)  
**Project Type**: Web service (FastAPI backend)  
**Performance Goals**: Logs delivered to Loki within 2 seconds of generation; dashboard queries return in < 1 second  
**Constraints**: 
- Must not block request/response cycle on log transmission (queue locally, async send)
- Must handle Loki unavailability gracefully (retry with exponential backoff)
- Must remain within Loki free tier (50GB/month)

**Scale/Scope**: 
- 10,000+ log entries per minute (worst case)
- Multi-tenant isolation: each tenant's logs visible only to that tenant's admin
- Support for 20+ agents across agendamento, ia, webhook, google_calendar modules

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principle I: Multi-Tenant Isolation ✅ PASS
- **Requirement**: Every log MUST be scoped to a tenant via `tenant_id` and searchable by tenant in Grafana dashboard
- **Implementation**: Label `tenant="TENANT_ID|TENANT_NAME"` on every log entry; Loki queries filtered by tenant in dashboard
- **Validation**: Integration test covers: tenant A's logs are not visible when filtering as tenant B

### Principle II: API-First, Backend-Only ✅ PASS
- **Requirement**: No UI code in this repo; new observability exposed via API (if needed by admin UI)
- **Implementation**: Core feature is logging service (backend only). Grafana dashboard is external SaaS; no UI templates added to this repo
- **Validation**: No HTML, SPA, or template files created

### Principle III: Clean Architecture (NEW CODE) ✅ PASS
- **Requirement**: New modules must use Domain/Application/Infrastructure/Interface layers with dependency inversion
- **Implementation Plan**:
  - **Domain**: `modules/observability/domain/log_event.py` — LogEntry entity (tenant, thread, method, line, agent, level, message)
  - **Application**: `modules/observability/application/log_service.py` — orchestrates Domain + port (LokiLogSender port)
  - **Infrastructure**: `modules/observability/infrastructure/loki_client.py` — adapter implementing LokiLogSender port using `requests` library
  - **Interface**: Lightweight logger factory injected into agent modules (no endpoint/schema needed; internal tool)
- **Ports**: `modules/observability/domain/ports/log_sender.py` — abstract interface for transmitting logs (Loki or test double)
- **Validation**: Unit tests mock the log_sender port; integration tests use real Loki or httpx mock

### Principle IV: Security & Guardrails ✅ PASS
- **Requirement**: Loki endpoint URL and API token in environment variables, not hardcoded; sanitize logs to prevent sensitive data leaks
- **Implementation**: 
  - Read from env: `GRAFANA_LOKI_URL` (default: `None` = disabled), `GRAFANA_LOKI_API_TOKEN`
  - Field-level redaction: pre-filter any field matching patterns like `password`, `token`, `secret`, `key` before transmission
  - Log level filtering: errors only trigger alerts (not all info/debug)
- **Validation**: Unit test confirms passwords/tokens are stripped; integration test sends intentional PII and verifies absence in Loki

### Principle V: Async Processing ✅ PASS
- **Requirement**: Heavy or blocking work (log transmission to Loki) must not block request/response
- **Implementation**: Logger queues events in-process (local Queue), background thread/task consumes and batches sends to Loki
- **Validation**: Request completes < 1ms after logging; verify Loki receives logs async

### Principle VI: Test-First (NEW CODE) ✅ PASS
- **Requirement**: Unit tests + integration tests mandatory
- **Test Structure**:
  - `modules/observability/test_log_service.py` — Unit tests mocking LokiLogSender port (happy path, error path, PII redaction)
  - `tests/integration/test_observability_api.py` — Integration tests: real/mock Loki, multi-tenant isolation, alert firing
- **Validation**: All tests pass; coverage > 80%

## Project Structure

### Documentation (this feature)

```text
specs/012-grafana-loki-observability/
├── plan.md              # This file
├── research.md          # Phase 0 (to be generated)
├── data-model.md        # Phase 1 (to be generated)
├── quickstart.md        # Phase 1 (to be generated)
├── contracts/           # Phase 1 (to be generated)
└── checklists/
    └── requirements.md  # Validation checklist
```

### Source Code (repository root)

```text
modules/observability/
├── __init__.py
├── domain/
│   ├── __init__.py
│   ├── log_event.py           # LogEntry entity, validation rules
│   └── ports/
│       ├── __init__.py
│       └── log_sender.py       # Abstract LokiLogSender port
├── application/
│   ├── __init__.py
│   └── log_service.py          # LogService orchestrator (use case)
├── infrastructure/
│   ├── __init__.py
│   ├── loki_client.py          # LokiLogSender adapter (requests-based)
│   └── log_sender_factory.py   # Port binding (env-driven: real or no-op)
├── interface/
│   ├── __init__.py
│   └── logger_factory.py       # Factory injected into agent modules
└── test_log_service.py         # Unit tests (colocated)

tests/integration/
├── test_observability_integration.py  # API contract tests

app/core/
├── observability.py  # Main observability setup (wiring + background task)
```

**Structure Decision**: New Clean Architecture module `modules/observability/` follows Principle III exactly. No modifications to legacy `modules/agendamento`, `modules/ia`, etc. — only dependency injection of logger factory into existing agent code (minimally invasive, grandfathered under legacy policy). If future retrofit of legacy modules is needed, this module becomes the port definition they depend on.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. The feature complies with all principles; new code follows Clean Architecture (Principle III) from day one.
