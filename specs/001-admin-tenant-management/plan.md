# Implementation Plan: Busca de Tenant com Prompts, Guardrails e Base de Conhecimento

**Branch**: `001-admin-tenant-management` | **Date**: 2026-08-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-admin-tenant-management/spec.md`

**Note**: This plan covers **backend/API work only**. The Painel Administrador UI is a separate, already-deployed
service (`interasisai-web`) that consumes this API; it is not built or modified here (Constitution Principle II).

## Summary

Deliver the REST API surface the admin panel needs to: (1) search for a tenant and see its linked
prompts/guardrails, falling back to the default prompt + global guardrails when no custom link exists;
(2) view, create/edit, and delete a tenant's knowledge base (single text document per tenant), with automatic
background re-vectorization. Everything required already exists in the domain except: tenant search, a
non-404 fallback for tenants without a custom prompt link, and the full knowledge-base CRUD (today only a
fire-and-forget "add text" ingestion endpoint exists — there is no read, edit, or delete).

**Auth decision (2026-08-19, explicit user instruction)**: these new/changed endpoints ship with **no
authentication**, matching the current unauthenticated state of every other tenant/prompt-manager endpoint.
The admin panel today gates access purely on the frontend (an env var read client-side, no token sent to
this API); there is no admin login, credential table, or JWT issuance yet. A proper admin-auth feature
(admin table, hashed password, login endpoint, JWT — mirroring the existing `/chat/init` pattern) is
explicitly deferred to a future feature. This is a **documented deviation from Constitution Principle IV**,
not a silent gap — see Constitution Check and Complexity Tracking below.

## Technical Context

**Language/Version**: Python 3.11 (existing FastAPI backend, `X | None` type syntax already in use)
**Primary Dependencies**: FastAPI, Pydantic v2, psycopg3 (raw SQL, no ORM layer in use), langchain-postgres
(`PGVector`) + langchain-huggingface (embeddings) for the vector store, PyJWT for token auth
**Storage**: PostgreSQL — existing tables `tenants`, `prompts`, `guardrails`, `prompt_guardrails`,
`tenant_prompts`; PGVector-managed tables `langchain_pg_collection`/`langchain_pg_embedding` (collection
`interasis_knowledge`, tenant-scoped via `cmetadata->>'tenant_id'`); **new** table `tenant_knowledge_base`
(raw-text source of truth for the KB document, decoupled from the async vector reprocessing)
**Testing**: pytest; unit tests for Application use cases with in-memory fake ports (no DB/HTTP); integration
tests via FastAPI `TestClient` with `app.dependency_overrides` substituting fake ports, covering the real
HTTP contract, tenant isolation, and error paths — no live Postgres required, consistent with this repo's
existing `monkeypatch`-based test style
**Target Platform**: Linux container (existing Docker/GHCR deployment, `uvicorn`), no new infra service
**Project Type**: Single backend service (REST API only — see Constitution Principle II; no frontend here)
**Performance Goals**: Search/detail responses well under 1s (backs SC-001's 10s end-to-end UX budget);
background re-vectorization completes within ~5 minutes for typical KB text sizes (backs SC-005)
**Constraints**: Every new/changed endpoint MUST stay tenant-scoped and MUST NOT block on embedding
generation (Principles I, V); new business logic MUST NOT be added directly to legacy repositories' SQL
inline in endpoints
**Scale/Scope**: Small-to-medium tenant count (SaaS onboarding, not high-volume multi-tenancy); at most one
knowledge-base document per tenant

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Multi-Tenant Isolation | Every new/changed endpoint takes `tenant_id` from the path, verifies the tenant exists, and scopes all reads/writes (text row + vector filter) to that `tenant_id`. Vector deletion uses an explicit `cmetadata->>'tenant_id'` filter, never a blanket delete. | PASS |
| II. API-First, Backend-Only Boundary | Only REST endpoints + schemas are added; no UI/template code in this repo. | PASS |
| III. Modular Clean Architecture | New `modules/knowledge_base/` (net-new module) is built as Domain/Application/Infrastructure/Interface with ports (`KnowledgeBaseRepositoryPort`, `VectorStorePort`) — full compliance from commit one, per the constitution. Tenant search and the prompt-fallback change are small additions to the existing legacy `tenant` and `prompt_manager` modules; per the Legacy Migration Policy they reuse those modules' existing repository/service methods rather than reaching into `infrastructure.connection` directly, and are not required to be re-layered. | PASS (legacy carve-out applied deliberately, not by omission) |
| IV. Security & Guardrails by Default | **FAIL, explicitly waived — see Complexity Tracking.** None of this feature's endpoints (new or modified) carry any authentication. Per explicit user instruction, admin auth (credentials table, hashing, login, JWT) is a separate future feature; today's admin panel gate is frontend-only. This matches the pre-existing, already-unauthenticated state of `/tenants/*` and `/prompt-manager/*`. |  |
| V. Asynchronous Processing | Knowledge-base upsert/delete persist the text row synchronously (fast, no embedding call) and dispatch re-vectorization via `BackgroundTasks`, mirroring the existing `initialize_tenant_data` pattern. | PASS |
| VI. Test-First Discipline | Unit tests planned for every new Application use case (search, prompt fallback, KB get/upsert/delete) with ports/services faked. Integration tests planned per new/changed endpoint, covering happy path, tenant-isolation, and error paths. | PASS (see tasks to be generated) |

**Known gap, tracked, not silently expanded**: every endpoint in this feature — new and pre-existing alike —
is reachable without any credential. This is strictly worse than the original plan (which added an admin JWT
dependency) but matches current production reality for the rest of `/tenants/*` and `/prompt-manager/*`, and
was chosen deliberately over building throwaway auth ahead of the real admin-login feature. Recommended
follow-up: a dedicated feature for admin authentication (credentials table, password hashing, login endpoint
issuing a JWT mirroring `/chat/init` in `app/api/v1/endpoints/chat.py`), after which every endpoint touched
here should get a `Depends(get_current_admin)` retrofit in the same pass.

## Project Structure

### Documentation (this feature)

```text
specs/001-admin-tenant-management/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/             # Phase 1 output
│   ├── tenant-search.md
│   ├── tenant-prompt-overview.md
│   └── tenant-knowledge-base.md
└── tasks.md               # Phase 2 output (/speckit.tasks — not created by this command)
```

### Source Code (repository root)

```text
app/
├── api/v1/endpoints/
│   ├── tenant.py                 # MODIFIED: add GET /tenants search (?q=) — no auth (see Auth decision)
│   ├── prompt_manager.py         # MODIFIED: GET /prompt-manager/tenant/{id} falls back to default
│   │                              #   prompt + global guardrails instead of 404 — no auth
│   └── knowledge_base.py         # NEW: GET/PUT/DELETE /tenants/{id}/knowledge-base — no auth
└── schemas/
    ├── tenant.py                 # MODIFIED: add TenantSearchResult (if shape differs from TenantResponse)
    ├── prompt_manager.py         # MODIFIED: add TenantPromptOverviewResponse (is_default_prompt flag)
    └── knowledge_base.py         # NEW: KnowledgeBaseResponse, KnowledgeBaseUpsertRequest

# NOT built in this pass: app/core/admin_auth.py (get_current_admin). Deferred to the future admin-auth
# feature; every endpoint above should get Depends(get_current_admin) retrofitted at that point.

modules/
├── tenant/
│   ├── tenant_repository.py      # MODIFIED: add search_tenants(term, limit)
│   └── tenant_service.py         # MODIFIED: add search_tenants(term)
├── prompt_manager/
│   ├── prompt_manager_repository.py  # MODIFIED: add get_default_prompt(), get_global_guardrails()
│   └── prompt_manager_service.py     # MODIFIED: get_tenant_prompt_details() falls back to default
├── vetorizacao/
│   └── gerenciador_vetores.py    # MODIFIED: add deletar_por_tenant(tenant_id) — legacy module,
│                                  #   reused as the Infrastructure adapter's vector backend
└── knowledge_base/                # NEW — net-new module, full Clean Architecture layering
    ├── domain/
    │   └── knowledge_base_document.py   # Entity + validation (non-empty content)
    ├── application/
    │   ├── ports.py                     # KnowledgeBaseRepositoryPort, VectorStorePort (Protocols)
    │   └── use_cases.py                 # GetTenantKnowledgeBase, UpsertTenantKnowledgeBase,
    │                                     # DeleteTenantKnowledgeBase, ReindexTenantKnowledgeBase
    └── infrastructure/
        ├── postgres_knowledge_base_repository.py  # implements KnowledgeBaseRepositoryPort
        └── pgvector_knowledge_base_adapter.py      # implements VectorStorePort, wraps GerenciadorVetores

tests/
├── test_chat_api.py               # existing, unchanged
├── unit/
│   ├── test_tenant_search.py
│   ├── test_prompt_manager_fallback.py
│   └── knowledge_base/
│       ├── test_upsert_tenant_knowledge_base.py
│       ├── test_delete_tenant_knowledge_base.py
│       └── test_knowledge_base_document.py
└── integration/
    ├── test_tenant_search_api.py
    ├── test_tenant_prompt_overview_api.py
    └── test_tenant_knowledge_base_api.py
```

**Structure Decision**: Single backend service. Tenant search and the prompt-manager fallback are small,
targeted extensions to the existing legacy `tenant`/`prompt_manager` modules (Legacy Migration Policy
carve-out). The knowledge-base capability is genuinely new domain behavior (a new entity, new invariants,
new persistence) and is built as a net-new `modules/knowledge_base/` package with full
Domain/Application/Infrastructure layering, per Constitution Principle III — with the FastAPI endpoint layer
in `app/api/v1/endpoints/knowledge_base.py` as its thin Interface.

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Principle IV (Security & Guardrails by Default) — no authentication on any endpoint in this feature | There is no admin login, credential store, or JWT issuance in the system yet; the current admin panel only gates access client-side. Building a real login flow now would mean inventing throwaway auth (fake users, a temporary secret) ahead of the actual admin-auth feature the user wants to build properly (credentials table, hashing, JWT). User explicitly chose to ship this feature matching today's unauthenticated posture and do auth as its own follow-up feature. | A minimal shared-secret/API-key check was considered as a lighter middle ground, but was rejected too — it would still need to be thrown away once real login lands, adds a "fake" credential to hand to the frontend team, and the user's own instruction was to leave it exactly as-is for now. |

This is tracked here rather than silently shipped as if compliant; the recommended next feature is admin
authentication (see Constitution Check note above), after which every endpoint touched by this feature
should be retrofitted with `Depends(get_current_admin)` in the same change.
