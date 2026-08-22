# Quickstart: validar exclusão em cascata de tenant

Pré-requisito: API rodando localmente (`uvicorn app.main:app --reload` ou via container) com o banco migrado (`alembic upgrade head`, incluindo a nova `0003_tenant_prompts_fk`).

## 1. Cenário: prompt e guardrail exclusivos → tudo é excluído

```bash
# Criar um prompt operacional dedicado
PROMPT_ID=$(curl -s -X POST http://localhost:8000/api/v1/prompt-manager/prompts \
  -H "Content-Type: application/json" \
  -d '{"titulo":"Prompt exclusivo QA","conteudo":"...","node_type":"operational"}' | jq -r .id)

# Criar um guardrail dedicado, vinculado só a esse prompt
GUARDRAIL_ID=$(curl -s -X POST http://localhost:8000/api/v1/prompt-manager/guardrails \
  -H "Content-Type: application/json" \
  -d '{"titulo":"Guardrail exclusivo QA","conteudo":"...","is_global":false}' | jq -r .id)
# (vincular guardrail ao prompt via endpoint de update do prompt com guardrail_ids)

# Criar tenant vinculado a esse prompt
curl -s -X POST http://localhost:8000/api/v1/tenants/ \
  -H "Content-Type: application/json" \
  -d "{\"tenant_id\":\"qa-exclusive\",\"name\":\"QA Exclusive\",\"prompt_id\":\"$PROMPT_ID\"}"

# Consultar o impacto ANTES de excluir
curl -s http://localhost:8000/api/v1/tenants/qa-exclusive/delete-impact | jq .
# Esperado: prompt em prompts_to_delete, guardrail em guardrails_to_delete

# Excluir de fato
curl -s -X DELETE http://localhost:8000/api/v1/tenants/qa-exclusive | jq .

# Confirmar que prompt e guardrail sumiram
curl -s http://localhost:8000/api/v1/prompt-manager/prompts/$PROMPT_ID -o /dev/null -w "%{http_code}\n"     # esperado: 404
curl -s http://localhost:8000/api/v1/prompt-manager/guardrails/$GUARDRAIL_ID -o /dev/null -w "%{http_code}\n" # esperado: 404
```

## 2. Cenário: prompt compartilhado entre dois tenants

```bash
curl -s -X POST http://localhost:8000/api/v1/tenants/ \
  -d "{\"tenant_id\":\"qa-shared-a\",\"name\":\"QA Shared A\",\"prompt_id\":\"$PROMPT_ID_COMPARTILHADO\"}"
curl -s -X POST http://localhost:8000/api/v1/tenants/ \
  -d "{\"tenant_id\":\"qa-shared-b\",\"name\":\"QA Shared B\",\"prompt_id\":\"$PROMPT_ID_COMPARTILHADO\"}"

curl -s http://localhost:8000/api/v1/tenants/qa-shared-a/delete-impact | jq .
# Esperado: prompt em prompts_to_unlink_only (não em prompts_to_delete)

curl -s -X DELETE http://localhost:8000/api/v1/tenants/qa-shared-a

# Prompt continua existindo e servindo qa-shared-b
curl -s http://localhost:8000/api/v1/tenants/qa-shared-b | jq .
curl -s http://localhost:8000/api/v1/prompt-manager/prompts/$PROMPT_ID_COMPARTILHADO -o /dev/null -w "%{http_code}\n"  # esperado: 200
```

## 3. Cenário: guardrail global preservado

```bash
# Guardrail global já existe via seed (ver EDI-43) ou criar um novo com is_global=true
curl -s http://localhost:8000/api/v1/tenants/qa-exclusive-2/delete-impact | jq .
# Esperado: guardrail global aparece em guardrails_to_unlink_only com is_global=true

curl -s -X DELETE http://localhost:8000/api/v1/tenants/qa-exclusive-2

curl -s http://localhost:8000/api/v1/prompt-manager/guardrails | jq '.[] | select(.is_global==true)'
# Esperado: guardrail global continua na lista
```

## 4. Cenário: tenant inexistente

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE http://localhost:8000/api/v1/tenants/nao-existe
# Esperado: 404
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/tenants/nao-existe/delete-impact
# Esperado: 404
```

## 5. Testes automatizados

```bash
pytest tests/unit -k tenant_delete_cascade -v
pytest tests/integration -k tenant_delete -v
```
