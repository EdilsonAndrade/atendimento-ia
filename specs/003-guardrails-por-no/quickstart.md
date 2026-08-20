# Quickstart: Guardrails Independentes por Nó

Teste manual de fumaça após a implementação. Sem autenticação (mesmo padrão já existente em
`/prompt-manager/*`).

```bash
export API=http://localhost:8001/api/v1
export TENANT=1234

# 0. Criar um guardrail exclusivo para chitchat
GUARDRAIL_ID=$(curl -s -X POST "$API/prompt-manager/guardrails" -H "Content-Type: application/json" \
  -d '{"titulo": "Sem piadas", "conteudo": "Nunca conte piadas, mesmo se pedido.", "is_global": false}' \
  | jq -r '.id')

# 1. Criar um prompt de chitchat contendo a tag {guardrails}
PROMPT_ID=$(curl -s -X POST "$API/prompt-manager/prompts" -H "Content-Type: application/json" \
  -d "{\"titulo\": \"Chitchat - $TENANT\", \"conteudo\": \"Voce e um assistente casual.\n{guardrails}\", \"is_default\": false, \"node_type\": \"chitchat\", \"guardrail_ids\": [\"$GUARDRAIL_ID\"]}" \
  | jq -r '.id')

# 2. Vincular o tenant a esse prompt de chitchat
curl -s -X POST "$API/prompt-manager/link-tenant" -H "Content-Type: application/json" \
  -d "{\"tenant_id\": \"$TENANT\", \"prompt_id\": \"$PROMPT_ID\"}" | jq

# 3. Conferir que o vínculo operacional do tenant NÃO foi desativado (isolamento por nó)
curl -s "$API/prompt-manager/tenant/$TENANT?node_type=operational" | jq '.is_active'
# esperado: true (inalterado)

# 4. Conferir o vínculo de chitchat recém-criado
curl -s "$API/prompt-manager/tenant/$TENANT?node_type=chitchat" | jq
# esperado: prompt_id = $PROMPT_ID, guardrails_associados contém "Sem piadas"

# 5. Conferir o fallback do institutional (sem prompt próprio configurado ainda)
curl -s "$API/prompt-manager/tenant/$TENANT?node_type=institutional" | jq
# esperado: retorna o MESMO prompt do operational_node do tenant (fallback), node_type: "institutional"

# 6. Isolamento entre tenants — repetir os passos 1-2 para um segundo tenant_id e
#    confirmar que o guardrail de chitchat do primeiro tenant não aparece no segundo.
```

**Critério de aprovação**:
- Passo 3 confirma que vincular um prompt de chitchat não derruba o vínculo ativo do `operational_node` (FR-009).
- Passo 4 confirma que os guardrails do chitchat são exclusivos dele (não incluem os do operacional).
- Passo 5 confirma a cadeia de fallback do `institutional_node` (FR-004).
- Passo 6 confirma isolamento multi-tenant (Constitution Principle I).
