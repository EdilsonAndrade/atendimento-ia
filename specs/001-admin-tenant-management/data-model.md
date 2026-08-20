# Data Model: Busca de Tenant com Prompts, Guardrails e Base de Conhecimento

## Entities

### Tenant *(existing — `tenants` table, unchanged)*

| Field | Type | Notes |
|---|---|---|
| id | text | Primary key, client-chosen identifier |
| name | text | Display name — search target |
| google_calendar_id | text | |
| allowed_domains | text[] | |
| created_at | timestamptz | |
| updated_at | timestamptz \| null | |

No schema change. Search reads existing columns only (`id`, `name`). The spec's `active`/`deleted_at`
soft-delete fields (present in `TenantRequest` schema) are **not** backed by real columns the repository
uses today — out of scope here; search simply reflects whatever rows exist in `tenants`.

### Prompt *(existing — `prompts` table, unchanged)*

| Field | Type | Notes |
|---|---|---|
| id | uuid/text | |
| titulo | text | |
| conteudo | text | Template body |
| is_default | boolean | Exactly one row is expected to be the fallback default |
| created_at / updated_at | timestamptz | |

### Guardrail *(existing — `guardrails` table, unchanged)*

| Field | Type | Notes |
|---|---|---|
| id | uuid/text | |
| titulo | text | |
| conteudo | text | |
| is_global | boolean | Applies to every tenant automatically |

### TenantPromptLink *(existing — `tenant_prompts` table, unchanged)*

Join of `tenant_id` ↔ `prompt_id`, with `is_active` and `custom_content_override`. Unique per
`(tenant_id, prompt_id)`; a tenant's *active* link (`is_active = TRUE`) is what the search result surfaces.
Absence of any active row is the "using default prompt" case.

### KnowledgeBaseDocument *(NEW — Domain entity, `modules/knowledge_base/domain/knowledge_base_document.py`)*

| Field | Type | Notes |
|---|---|---|
| tenant_id | str | Identity — one document per tenant |
| content | str | MUST be non-empty (validated in the Domain constructor, not just at the API layer) |
| updated_at | datetime | Set on every upsert |

Persisted via `KnowledgeBaseRepositoryPort` to the new table below. Framework-free: no FastAPI/psycopg
imports in this module.

**New table**: `tenant_knowledge_base`

```sql
CREATE TABLE IF NOT EXISTS tenant_knowledge_base (
    tenant_id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Created idempotently at repository init, matching the existing `chat_thread_sessions` convention in
`modules/ia/thread_session.py`. No foreign key to `tenants` is enforced at the DB level, consistent with how
other tenant-scoped tables in this codebase (e.g. the PGVector `cmetadata->>'tenant_id'`) already work.

### Vector index *(existing — PGVector-managed tables, unchanged schema)*

`langchain_pg_collection` (collection `interasis_knowledge`) / `langchain_pg_embedding`
(`cmetadata->>'tenant_id'` scoping). Treated as a derived index of `tenant_knowledge_base.content`: replaced
wholesale per tenant on every upsert (delete-then-reinsert), removed wholesale on delete. Never read as the
source of truth for "current content" (see research.md #2).

## Relationships

```text
Tenant (1) ── (0..1) TenantPromptLink ── (1) Prompt ── (0..n) Guardrail   [via prompt_guardrails, + is_global]
Tenant (1) ── (0..1) KnowledgeBaseDocument ── (derives) ──> vector rows filtered by tenant_id
```

## State / lifecycle notes

- **KnowledgeBaseDocument**: does not exist → created (PUT with no prior row) → edited (PUT over existing
  row, same primary key, content replaced) → deleted (row removed, vectors removed). There is no separate
  "processing" state persisted — the text row is always immediately consistent; the vector index is
  best-effort eventually consistent (background task), per SC-005's ~5 minute budget.
- **TenantPromptLink**: unaffected by this feature (read-only here); its absence is a valid, expected state
  handled by the fallback in research.md #4, not an error state.
