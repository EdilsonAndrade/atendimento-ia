# Contract: Tenant Prompt & Guardrail Overview

## `GET /api/v1/prompt-manager/tenant/{tenant_id}` *(existing endpoint — modified)*

**Auth**: none (deferred — see `research.md` #1)

**Behavior change**: no longer 404s when the tenant has no active custom prompt link. Order of resolution:

1. Tenant does not exist at all → `404 {"detail": "Tenant não encontrado"}`
2. Tenant exists, has an active `tenant_prompts` link → return that prompt + its associated guardrails
   (prompt-specific ∪ global), `is_default_prompt: false`
3. Tenant exists, no active link → return the prompt where `is_default = TRUE` + all `is_global = TRUE`
   guardrails, `is_default_prompt: true`

**Response `200 OK`** (custom link case):

```json
{
  "tenant_id": "1234",
  "prompt_id": "b3f1...",
  "prompt_titulo": "Atendimento Barbearia",
  "prompt_conteudo": "...",
  "custom_content_override": null,
  "is_default_prompt": false,
  "guardrails_associados": [
    {"id": "g1", "titulo": "Confirmação de agenda", "conteudo": "...", "is_global": false}
  ]
}
```

**Response `200 OK`** (fallback case — no custom link):

```json
{
  "tenant_id": "5678",
  "prompt_id": "d9a2...",
  "prompt_titulo": "Prompt Padrão",
  "prompt_conteudo": "...",
  "custom_content_override": null,
  "is_default_prompt": true,
  "guardrails_associados": [
    {"id": "gG1", "titulo": "Guardrail Global 1", "conteudo": "...", "is_global": true}
  ]
}
```

**Errors**:
- `404` — tenant does not exist
- `500` — no prompt is marked `is_default = TRUE` in the database (misconfiguration; not a normal path, but
  must not silently return an empty prompt)

**Maps to**: FR-002, FR-003; US1 Acceptance Scenarios 1 and 3.
