# Quickstart: Busca de Tenant com Prompts, Guardrails e Base de Conhecimento

Manual smoke test once the endpoints are implemented. No authentication required — admin auth is deferred to
a future feature (see `research.md` #1).

```bash
export API=http://localhost:8001/api/v1

# 1. Search for a tenant
curl -s "$API/tenants?q=barbearia" | jq

# 2. Confirm one exists and inspect it
curl -s "$API/tenants/1234" | jq

# 3. View its prompts/guardrails (falls back to default if no custom link)
curl -s "$API/prompt-manager/tenant/1234" | jq

# 4. View current knowledge base (expect content: null the first time)
curl -s "$API/tenants/1234/knowledge-base" | jq

# 5. Create/edit the knowledge base
curl -s -X PUT "$API/tenants/1234/knowledge-base" -H "Content-Type: application/json" \
  -d '{"content": "Regra: o barbeiro Lucas atende apenas de terça a sábado, das 09h às 18h."}' | jq

# 6. Re-read to confirm the text is immediately visible (before re-vectorization finishes)
curl -s "$API/tenants/1234/knowledge-base" | jq

# 7. Delete it
curl -s -X DELETE "$API/tenants/1234/knowledge-base" | jq

# 8. Confirm it's gone
curl -s "$API/tenants/1234/knowledge-base" | jq   # content: null again

# 9. Isolation check — repeat steps 5–6 for a second tenant_id and confirm tenant 1234's
#    knowledge-base GET is unaffected by the other tenant's content.
```

**Pass criteria**: every call above returns the shapes documented in `contracts/`, step 9 shows no
cross-tenant leakage, and no request in steps 5/7 blocks noticeably waiting on embedding generation.
