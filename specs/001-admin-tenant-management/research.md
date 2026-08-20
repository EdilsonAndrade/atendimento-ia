# Phase 0 Research: Busca de Tenant com Prompts, Guardrails e Base de Conhecimento

## 1. Admin authentication for cross-tenant endpoints — DEFERRED

**Decision (revised 2026-08-19)**: Ship this feature with **no authentication** on any of its endpoints,
matching the current unauthenticated state of every other `/tenants/*` and `/prompt-manager/*` endpoint.
Do **not** build `get_current_admin` / `app/core/admin_auth.py` in this pass.

**Why this changed**: The original decision below (JWT bearer signed with `ADMIN_SESSION_SECRET`) assumed
the admin panel already had a login flow that could mint such a token. Confirmed with the user this is not
the case: there is no admin credentials table, no password hashing, and no JWT issuance today — the current
admin panel gates access purely on the frontend by reading an environment variable client-side, with no
token ever sent to this API. Building `get_current_admin` now would mean inventing a token format with
nothing real to validate it against, or inventing throwaway admin credentials that would be discarded the
moment real admin auth is built. The user explicitly asked to defer proper admin authentication (a
credentials table, hashing, a login endpoint, JWT — mirroring the existing `/chat/init` pattern in
`app/api/v1/endpoints/chat.py`) to its own future feature, and ship this one matching today's posture.

**Consequence**: this is a tracked deviation from Constitution Principle IV, not a silent gap — see
`plan.md` Constitution Check and Complexity Tracking. Every endpoint this feature adds/modifies should be
retrofitted with `Depends(get_current_admin)` in the same change that builds the future admin-auth feature.

**Original analysis (kept for when that follow-up feature is scoped)**: a JWT bearer dependency validated
via `fastapi.security.HTTPBearer`, signed with `ADMIN_SESSION_SECRET` (already provisioned to the
`interasisai-web` container in `docker-compose.yml` alongside `ADM_USER`/`ADM_PWD`), following the same
shape as `modules/token/token_verify.py`'s `verificar_token` — but with an admin-scoped subject instead of a
`tenant_id` claim, since `verificar_token` has no concept of "can act on any tenant." A login endpoint
(e.g. `POST /api/v1/admin/login`) would validate admin credentials and mint that JWT, mirroring `/chat/init`.

## 2. Representing the knowledge base as a single document per tenant

**Decision**: Add one new table, `tenant_knowledge_base(tenant_id TEXT PRIMARY KEY, content TEXT NOT NULL,
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())`, created idempotently in code
(`CREATE TABLE IF NOT EXISTS ...`) the same way `modules/ia/thread_session.py` initializes
`chat_thread_sessions` — this repo has no migration framework (no Alembic, no `.sql` migration files), and
that inline-idempotent-DDL pattern is the established convention. This table becomes the source of truth for
"what is the tenant's current KB content" (fast, always available for the GET), decoupled from the vector
store, which is treated as a derived/eventually-consistent index rebuilt from this table's content.

**Rationale**: The existing ingestion path (`POST /ingest/text` → `initialize_tenant_data` →
`GerenciadorVetores.criar_banco_com_textos` → `PGVector.add_documents`) only ever *appends* embeddings; it
has no read path and no way to know "what text is currently active for this tenant" without re-reading raw
vector rows. Persisting the raw text separately makes "view current content" (FR-005) trivial and instant,
and makes "edit" well-defined: replace the text row, then re-derive the vector index from it.

**Alternatives considered**:
- *Read current content back from PGVector by re-assembling stored chunks*: rejected — lossy (chunking is
  not guaranteed reversible to the original text), and couples the read path to embedding-store internals.
- *Store content as multiple discrete rows (list of chunks)*: rejected — the user explicitly decided the
  knowledge base is a single document per tenant, not a list of items (see spec Assumptions).

## 3. Replacing (not accumulating) vectors on edit/delete

**Decision**: Add `deletar_por_tenant(tenant_id)` to `modules/vetorizacao/gerenciador_vetores.py`, executing
`DELETE FROM langchain_pg_embedding WHERE collection_id = (SELECT uuid FROM langchain_pg_collection WHERE
name = %s) AND cmetadata->>'tenant_id' = %s` against the same Postgres connection PGVector uses. On upsert,
the background task calls `deletar_por_tenant(tenant_id)` then `criar_banco_com_textos([content], tenant_id)`
(replace, not append). On delete, it calls `deletar_por_tenant(tenant_id)` alone.

**Rationale**: `langchain_postgres.PGVector`'s public API (`add_documents`, `similarity_search`, and
`delete(ids=...)` in the version pinned by `requirements.txt`) has no documented delete-by-metadata-filter
call, but the underlying schema (`langchain_pg_collection` / `langchain_pg_embedding` with a `cmetadata`
JSONB column) is stable and already relied upon implicitly by `search_context`'s
`filter={"tenant_id": tenant_id}` similarity search. Deleting via the same `cmetadata` filter, scoped to the
known collection name, is the smallest change that guarantees isolation and avoids accumulating stale
duplicate chunks on repeated edits.

**Alternatives considered**:
- *Append-only, let old + new chunks coexist*: rejected — directly contradicts FR-006 ("edit" must replace,
  not accumulate) and would degrade RAG answer quality with stale/contradictory chunks over time.
- *Recreate the whole `interasis_knowledge` collection per edit*: rejected — would delete every other
  tenant's vectors too (the collection is shared, isolation is by metadata, not by collection); a clear
  Principle I violation.

## 4. Default-prompt fallback instead of 404

**Decision**: Add `get_default_prompt()` and `get_global_guardrails()` to `PromptManagerRepository`. In the
endpoint (Interface layer), first resolve the tenant via `TenantService.get_tenant(tenant_id)` (404 if
absent). Then call `PromptManagerService.get_tenant_prompt_details(tenant_id)`; if it returns `None` (no
active link), call the new default-prompt + global-guardrails lookup instead and return the same response
shape with `is_default_prompt: true`.

**Rationale**: Directly implements spec FR-002/FR-003 and US1 Acceptance Scenario 3. Composing the
tenant-existence check and the prompt-fallback at the endpoint (Interface) layer — rather than making
`prompt_manager` depend on `tenant` internals — keeps the two legacy modules decoupled, consistent with how
`app/api/v1/endpoints/*` already compose independent services today.

**Alternatives considered**:
- *Keep 404 on no-link, let the frontend call a separate "get default prompt" endpoint*: rejected — spec
  requires a single search action to surface prompt+guardrail info (US1), and this would push
  business-meaning ("this tenant is on the default") into the frontend instead of the API.

## 5. Testing approach without a live test database

**Decision**: Unit tests exercise the new `modules/knowledge_base` Application use cases directly, with
`KnowledgeBaseRepositoryPort`/`VectorStorePort` implemented as simple in-memory fakes (dicts) — no FastAPI,
no DB. Integration tests use FastAPI's `TestClient` against the real routers, with
`app.dependency_overrides[...]` substituting the same fakes so the full HTTP contract (status codes,
validation errors, tenant-isolation behavior across two fake tenants) is exercised without a live
Postgres/pgvector instance. No auth dependency to override for now (see decision #1 — deferred).

**Rationale**: Matches the repo's existing convention of `monkeypatch`-based isolation
(`tests/test_chat_api.py`) rather than introducing a new test-database dependency, while still satisfying
Constitution Principle VI's requirement for both unit and integration coverage.

**Alternatives considered**:
- *Spin up a real Postgres/pgvector container for integration tests*: deferred — valuable for a future CI
  hardening pass, but out of scope for "the only things missing to deliver enough for the frontend," and no
  such test infra exists anywhere in the repo today.
