# Contract: Tenant Search & Lookup

## `GET /api/v1/tenants?q={term}`

**Auth**: none (see `research.md` #1 — admin authentication is deferred to a future feature; this matches
the current unauthenticated state of every other tenant/prompt-manager endpoint)

**Query params**:
- `q` (string, required, min length 1) — matched case-insensitively against `id` and `name` (partial match)
- `limit` (int, optional, default 20, max 100)

**Response `200 OK`** — always a list, even when empty (never 404 for "no match"):

```json
[
  {
    "id": "1234",
    "name": "Barbearia Central",
    "google_calendar_id": "abc@group.calendar.google.com",
    "allowed_domains": ["barbeariacentral.com.br"],
    "created_at": "2026-01-10T12:00:00Z",
    "updated_at": null
  }
]
```

**Errors**:
- `422` — `q` missing or empty (FastAPI/Pydantic validation)

**Maps to**: FR-001, FR-004; spec Edge Case "termo de busca muito curto" (422, not a silent empty result).

---

## `GET /api/v1/tenants/{tenant_id}` *(existing endpoint — unchanged)*

No change in this feature (auth was originally planned to be added here; deferred — see `research.md` #1).
Behavior: `200` with the tenant record, `404` if it does not exist.

**Maps to**: FR-001 (confirm tenant existence before showing prompt/guardrail/KB detail).
