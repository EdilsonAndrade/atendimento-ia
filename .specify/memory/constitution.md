<!--
Sync Impact Report
==================
Version change: 1.0.0 → 1.1.0
Modified principles:
  - III. Layered Architecture: Endpoint → Service → Repository → III. Modular Clean Architecture
    (expanded from a 3-layer convention into explicit Domain/Application/Infrastructure/Interface layers
    with dependency inversion; declared NON-NEGOTIABLE for new code, legacy code grandfathered — see
    Governance > Legacy Migration Policy)
Added sections:
  - Current Architecture Map (Baseline) — full inventory of what exists today, requested explicitly so the
    constitution reflects reality before layering new standards on top of it
  - VI. Test-First Discipline: Unit + Integration Coverage (new principle)
  - Governance > Legacy Migration Policy
Removed sections: none
Templates requiring updates:
  - .specify/templates/plan-template.md ✅ compatible as-is (Constitution Check gate references this file
    generically; new plans will now be checked against Principles III/VI explicitly)
  - .specify/templates/spec-template.md ✅ compatible as-is
  - .specify/templates/tasks-template.md ✅ compatible as-is (unit + integration test tasks already fit its
    existing task categorization)
  - CLAUDE.md ✅ no change needed
Follow-up TODOs:
  - TODO(LEGACY_RETROFIT_PLAN): the "regressão" pass that brings existing modules (tenant, prompt_manager,
    vetorizacao, agendamento, ia, webhook, google_calendar, token) up to Principles III/VI is intentionally
    deferred to a future Spec Kit feature, per explicit user instruction; not scheduled by this amendment.
-->

# SincroAgente API Constitution

## Core Principles

### I. Multi-Tenant Isolation (NON-NEGOTIABLE)

Every request, data record, and background job MUST be scoped to a single tenant, identified via the
`X-Tenant-ID` header (integrations, WhatsApp) or an explicit `tenant_id` in the request body (web chat).
No code path may read or write another tenant's conversation history, vector store collection, prompts,
guardrails, or calendar data. Vector/knowledge data MUST remain physically or logically partitioned per
tenant (e.g., isolated collections/paths keyed by `tenant_id`). Conversation sessions MUST expire and be
isolated per tenant so stale or cross-tenant context can never leak into a response. Any endpoint that
cannot establish a tenant identity MUST reject the request rather than fall back to a shared default.

**Rationale**: This is a multi-tenant SaaS platform serving multiple independent client businesses through
a shared codebase and shared infrastructure; a tenant-isolation failure is a data breach, not a bug.

### II. API-First, Backend-Only Boundary

This repository owns the versioned REST API (`/api/v1`) and its backend logic only. It does not contain,
and MUST NOT grow, UI code (HTML templates, SPA frontends, admin dashboards). The Painel Administrador and
any other UI are separate consumer applications (deployed as their own services, e.g. the admin web
container) that integrate exclusively through this API's documented contracts. Every new capability needed
by a UI or external integration MUST be exposed as an explicit, versioned endpoint with a Pydantic
schema — never as a bespoke script, direct DB access, or undocumented side channel.

**Rationale**: The deployment topology already separates this API from the admin web app and the WhatsApp
gateway as independent containers on a shared proxy network; mixing UI concerns back into this repo breaks
that separation and couples unrelated release cycles.

### III. Modular Clean Architecture (NON-NEGOTIABLE for new code)

New features, new modules, and any full rewrite of an existing module MUST be organized in explicit,
dependency-inverted layers:

- **Domain**: framework-free entities and business rules. MUST NOT import FastAPI, psycopg/SQLAlchemy,
  LangChain, or any other framework/infra library.
- **Application**: use cases/services that orchestrate Domain logic, depending only on abstractions
  (Python `Protocol`/ABC "ports") for anything external — persistence, vector store, calendar, LLM/agent
  runtime.
- **Infrastructure**: adapters that implement those ports — concrete repositories (SQL), vector store
  clients, Google Calendar client, LangChain/LLM wiring. Infrastructure MAY depend on Application/Domain;
  Application/Domain MUST NEVER import Infrastructure or `app.api.*` directly.
- **Interface**: FastAPI endpoints (`app/api/v1/endpoints`) and Pydantic schemas (`app/schemas`) — thin
  translators between HTTP and Application use cases, with no business rules or SQL of their own.

Dependencies point inward only: Interface → Application → Domain, with Infrastructure plugged into
Application through ports (dependency inversion), never the reverse. A module is compliant when its
Application layer can be unit-tested with every port replaced by a test double, with no real database,
network, or LLM call involved.

**Rationale**: The current baseline (see Current Architecture Map) already separates endpoint / service /
repository, but services instantiate concrete repository classes directly and repositories embed raw SQL,
so nothing is swappable or unit-testable in isolation. Formalizing ports/adapters is what actually buys
testability and lets infrastructure change (e.g., swapping the vector store or calendar provider) without
touching business logic — a concrete near-term need given the duplicated Google Calendar tool
implementations already present under `modules/agendamento/`.

### IV. Security & Guardrails by Default

Every non-webhook endpoint MUST require a resolvable tenant identity, and endpoints handling administrative
or authenticated user actions MUST require valid credentials (JWT session token or admin session,
consistent with existing `token_verify` / `security` modules). Public-facing endpoints (chat, webhooks)
MUST be protected by rate limiting. Webhook endpoints MUST validate their origin/event type and MUST NOT
trust unauthenticated payloads beyond what they were designed to accept. Changes to AI agent prompts or
guardrails MUST be reviewed for prompt-injection and safety impact before being applied to any tenant,
since guardrails are the primary defense against the agent taking unintended actions (e.g., false calendar
confirmations).

**Rationale**: Recent incident history in this repo (webhook event restriction, allowed-domains validation,
guardrails hardening around calendar availability) shows these are real, previously-exploited gaps, not
hypothetical risks.

### V. Asynchronous Processing for Heavy or AI Workloads

Vetorização (embeddings/RAG ingestion), large document processing, and any other long-running or
AI-model-bound work MUST run outside the request/response cycle (e.g., FastAPI `BackgroundTasks` or an
equivalent async job), returning an immediate acknowledgement with a status the caller can poll or be
notified about. Endpoints MUST NOT block on embedding generation, LLM calls used for batch processing, or
file parsing of arbitrary size within the synchronous request path.

**Rationale**: Blocking the API on embedding/LLM work degrades every tenant sharing the process, and the
codebase already establishes the background-task pattern for ingestion — new heavy work must follow it.

### VI. Test-First Discipline: Unit + Integration Coverage (NON-NEGOTIABLE for new code)

Every new use case/service MUST ship with two kinds of tests:

1. **Unit tests** exercising Domain/Application logic in isolation, with every Infrastructure port replaced
   by a fake or mock — no real database, HTTP, or LLM call.
2. **Integration tests** exercising the real HTTP contract (e.g., FastAPI `TestClient`/`httpx` against
   `/api/v1/...`), covering at minimum: the happy path, the multi-tenant isolation boundary (a second
   tenant cannot see or affect the first tenant's data), and the primary error path (validation/not-found).

Unit tests live colocated with the module they cover (`test_*.py` beside the code, consistent with current
convention). Integration tests that exercise the API contract live under `tests/integration/`. A change
that adds a new endpoint or service MUST NOT be merged without both test types.

**Rationale**: The codebase already has good instincts here — `monkeypatch`-based isolation in
`tests/test_chat_api.py` and module-level `test_*.py` files across `modules/agendamento`, `modules/ia`,
`modules/vetorizacao`, `protocols`, and `util` — but there is no enforced split between unit and
API-integration coverage. Making both mandatory for new work closes that gap without demanding an immediate
rewrite of existing tests.

## Current Architecture Map (Baseline)

This section is descriptive: it records the architecture as it exists today so future work has an accurate
starting point. It is not itself a set of MUST rules — Principles III and VI above define the target for
new work; see *Governance > Legacy Migration Policy* for how the gap between this baseline and that target
is closed over time.

- **Interface layer** (`app/`):
  - `app/main.py` — FastAPI app assembly, CORS (+ a custom `WidgetCORSMiddleware`), rate-limiter wiring,
    credential-protected `/docs`/`/redoc`.
  - `app/api/v1/router.py` + `app/api/v1/endpoints/*` — `chat`, `ingest`, `prompt_manager`, `tenant`,
    `evolution_whatsapp_instances`.
  - `app/api/v1/webhooks/whatsapp.py` — Evolution API (WhatsApp) webhook receiver.
  - `app/schemas/*` — Pydantic request/response contracts.
  - `app/core/*` — `config` (pydantic-settings), `security` (Swagger basic auth), `limiter` (slowapi),
    `widget_cors`.
- **Business modules** (`modules/`), each currently mixing what Principle III now splits into
  Application/Infrastructure:
  - `tenant/` — `tenant_service.py` + `tenant_repository.py` (raw psycopg SQL).
  - `prompt_manager/` — prompt/guardrail CRUD, tenant↔prompt N:N linking.
  - `vetorizacao/` — `gerenciador_vetores.py` (pgvector persistence), `setup_databases.py` (PDF/Excel/TXT →
    chunks → vector store), tenant-isolated under `db/<tenant_id>/knowledge_db`.
  - `agendamento/` — scheduling LangChain tools (`agenda_tool.py`, `booking_tools.py`,
    `consulta_agenda_tool.py`, `delete_agenda_tool.py`), plus a parallel, partially duplicated
    `tools/google_calendario/` subpackage.
  - `google_calendar/google_calendar_service.py` — Google Calendar API integration.
  - `ia/` — `agent_graph.py` (LangGraph state graph), `assistante_rag.py`, `thread_session.py` (per-tenant
    session/conversation handling).
  - `webhook/whatsapp.py` — WhatsApp message-handling logic invoked by the webhook endpoint.
  - `token/token_verify.py` — JWT verification.
- **Cross-cutting**:
  - `infrastructure/connection.py` — a single shared `get_db_connection()` psycopg factory, not yet exposed
    behind a port/interface.
  - `protocols/file_data_reader.py` — a standalone `FileDataReader` abstraction (txt/pdf/xlsx/csv), the
    closest existing example of a port-like component, though not yet wired via dependency inversion.
  - `util/` — `ai_helpers.py`, `time_helpers.py`.
  - `prompts/` — `guardrails.md`, `operactional_prompt.md`, `load_prompt.py` (static prompt/guardrail
    content and loader).
  - `db/<tenant_id>/knowledge_db/` — per-tenant on-disk knowledge artifacts backing the vector store.
- **Testing today**: inconsistently located — `tests/test_chat_api.py` plus module-colocated
  `test_*.py` files (`modules/agendamento`, `modules/ia`, `modules/vetorizacao`, `modules/webhook`,
  `protocols`, `util`). No `tests/unit/` vs `tests/integration/` split exists yet.

## Technology & Deployment Constraints

- **Backend**: Python with FastAPI, Pydantic v2 (schemas), SQLAlchemy/psycopg for PostgreSQL access.
- **AI/RAG stack**: LangChain, LangGraph, LangGraph Postgres checkpointing, PostgreSQL + pgvector for vector
  storage, isolated per tenant.
- **Auth & rate limiting**: PyJWT for token-based auth, `slowapi` for rate limiting on public endpoints.
- **Integrations**: WhatsApp via Evolution API (webhook-driven), Google Calendar API for scheduling.
- **Deployment**: containerized (Docker), built and published to GHCR, run alongside sibling containers
  (`evolution-api`, `interasisai-web` admin panel, Redis) on a shared reverse-proxy network. This API
  container does not deploy or bundle the admin web app.
- **Environment/config**: managed via `.env` files and `pydantic-settings`; secrets (API keys, admin
  credentials, JWT secrets) MUST NOT be hardcoded and MUST NOT be committed to the repository.

## Development Workflow & Quality Gates

- Commits follow a Conventional Commits style (`feat:`, `fix:`, `chore:`) with a concise, imperative
  Portuguese or English summary, matching existing repository history.
- New endpoints or services MUST include both unit and integration tests per Principle VI; tenant-isolation
  and error paths MUST be covered, not only the happy path.
- Feature work is tracked through Spec Kit artifacts under `specs/<feature>/` (spec → plan → tasks); the
  Constitution Check gate in the plan template MUST be re-verified whenever a plan's technical approach
  changes materially after Phase 1 design.
- Database schema or vector-store layout changes MUST document tenant-isolation impact explicitly (how the
  change preserves per-tenant partitioning) before being merged.

## Governance

This constitution supersedes ad hoc conventions and prior undocumented practice for this repository.
Amendments require: (1) a documented rationale for the change, (2) an update to this file following the
same validation this document was created under, and (3) propagation of any resulting changes to dependent
Spec Kit templates (`plan-template.md`, `spec-template.md`, `tasks-template.md`) in the same change set.

Versioning follows semantic versioning for governance documents:
- **MAJOR**: Backward-incompatible principle removal or redefinition (e.g., dropping multi-tenant isolation
  as non-negotiable).
- **MINOR**: A new principle or materially expanded section is added.
- **PATCH**: Wording clarifications, typo fixes, or non-semantic refinements.

All new specs, plans, and code reviews for this repository MUST verify compliance with the principles
above; any deviation MUST be justified explicitly (e.g., in a plan's Complexity Tracking table) rather than
silently introduced.

### Legacy Migration Policy

Existing modules (`tenant`, `prompt_manager`, `vetorizacao`, `agendamento`, `ia`, `webhook`,
`google_calendar`, `token`) predate Principles III and VI in their current form and are **not** required to
be rewritten immediately to comply. They are grandfathered as legacy until an explicit retrofit pass
("regressão") brings each one into compliance — tracked as its own future Spec Kit feature, not scheduled
by this amendment. Until a module is retrofitted:

1. It MUST NOT be extended with new business logic embedded directly in an endpoint, nor with new raw SQL
   added outside its existing repository — new code within a legacy module still respects the
   endpoint → service → repository boundary it already has.
2. New logic added to a legacy module SHOULD depend on that module's existing repository/service public
   methods rather than reaching into `infrastructure.connection` or another module's internals directly.
3. Bug fixes in legacy modules do not require migrating the whole module to Clean Architecture first.

Net-new modules and features — anything created under a new `modules/<name>/` directory going forward —
MUST comply with Principles III and VI from their first commit; there is no grace period for new code.

**Version**: 1.1.0 | **Ratified**: 2026-08-19 | **Last Amended**: 2026-08-19
