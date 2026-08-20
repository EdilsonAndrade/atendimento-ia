# Contract: Tenant Knowledge Base (view / edit / delete)

All three endpoints require no authentication (deferred — see `research.md` #1) and share
`404 {"detail": "Tenant não encontrado"}` when `tenant_id` does not exist in `tenants`.

## `GET /api/v1/tenants/{tenant_id}/knowledge-base`

**Response `200 OK`** (content exists):

```json
{"tenant_id": "1234", "content": "Regra: o barbeiro Lucas atende...", "updated_at": "2026-08-19T10:00:00Z"}
```

**Response `200 OK`** (no content yet — not an error, empty state):

```json
{"tenant_id": "1234", "content": null, "updated_at": null}
```

**Maps to**: FR-005.

---

## `PUT /api/v1/tenants/{tenant_id}/knowledge-base`

Single upsert endpoint: creates the document if none exists (US4), replaces it if one does (US2). The
distinction is invisible to the caller — same request/response shape either way.

**Request body**:

```json
{"content": "Regra: o barbeiro Lucas atende apenas de terça a sábado, das 09h às 18h."}
```

- `content`: string, required, `min_length=1` (rejects empty/whitespace-only — FR-009)

**Response `200 OK`**:

```json
{"tenant_id": "1234", "content": "Regra: o barbeiro Lucas atende...", "updated_at": "2026-08-19T10:05:00Z"}
```

Persists the text row synchronously (so a follow-up GET immediately reflects it), then schedules background
re-vectorization (delete old vectors for this tenant, embed and store the new content) — FR-010. The response
does not wait for re-vectorization to finish.

**Errors**:
- `404` — tenant does not exist
- `422` — `content` missing or empty

**Maps to**: FR-006, FR-008, FR-009, FR-010; US2 Acceptance Scenarios 1–2, US4 Acceptance Scenario 1.

---

## `DELETE /api/v1/tenants/{tenant_id}/knowledge-base`

**Response `200 OK`**:

```json
{"tenant_id": "1234", "message": "Base de conhecimento removida com sucesso."}
```

Removes the `tenant_knowledge_base` row synchronously and schedules background deletion of the tenant's
vector rows.

**Errors**:
- `404` — tenant does not exist, **or** tenant exists but has no knowledge base to delete
  (`{"detail": "Nenhuma base de conhecimento encontrada para este tenant"}`) — the explicit-confirmation
  requirement (FR-007, SC-004) is a frontend UX concern (confirm dialog before calling this endpoint); the
  API's job is just to make the delete an unambiguous, deliberate, single-purpose call.

**Maps to**: FR-007; US3 Acceptance Scenarios 1–2.
