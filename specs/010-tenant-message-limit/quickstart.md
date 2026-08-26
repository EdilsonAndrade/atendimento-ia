# Quickstart — Limite de mensagens por tenant (mensal)

## Aplicar a migration

```bash
alembic upgrade head
```

## Variáveis de ambiente novas

```bash
# Redis (fila de retry de chat_token_usage)
REDIS_URL=redis://localhost:6379/2

# E-mail (SMTP)
SMTP_HOST=smtp.exemplo.com
SMTP_PORT=587
SMTP_USERNAME=alertas@interasisai.com.br
SMTP_PASSWORD=troque_isto
SMTP_FROM=alertas@interasisai.com.br
SMTP_USE_TLS=true

# Opcional — defaults já cobrem o caso comum
TOKEN_USAGE_RETRY_MAX_ATTEMPTS=5
TENANT_LIMIT_WORST_CASE_CALLS_PER_MESSAGE=3
TENANT_LIMIT_AVERAGE_CALLS_PER_MESSAGE=3
```

## Rodar os testes

```bash
# Unit (sem banco/rede)
pytest tests/unit/test_tenant_limits_domain.py tests/unit/test_check_tenant_limit_use_case.py \
  tests/unit/test_notify_usage_milestones_use_case.py tests/unit/test_record_token_usage_use_case.py -v

# Integration (exige Postgres real com a migration aplicada)
pytest tests/integration/test_tenant_message_limit_api.py tests/integration/test_tenant_usage_endpoint_api.py \
  tests/integration/test_global_notification_recipients_api.py tests/integration/test_tenant_limit_enforcement.py \
  tests/integration/test_notification_milestone_idempotency.py -v

# Integration (exige também Redis real acessível via REDIS_URL)
pytest tests/integration/test_token_usage_retry_queue.py -v
```

## Rodar o worker de retry localmente

```bash
python -m workers.token_usage_retry_worker
```

Ao subir, o worker primeiro drena qualquer backlog pendente (incluindo entradas que ficaram no PEL de uma execução anterior que caiu no meio do processamento) antes de esperar por novas entradas — não precisa de nenhum passo manual de "recuperação".

## Simular um bloqueio manualmente

```bash
curl -X PUT http://localhost:8001/api/v1/tenants/SEU_TENANT_ID \
  -H "Content-Type: application/json" \
  -d '{"name": "...", "google_calendar_id": "...", "allowed_domains": [], "monthly_message_limit": 1, "notification_emails": ["voce@exemplo.com"]}'

curl http://localhost:8001/api/v1/tenants/SEU_TENANT_ID/usage
```

Depois de 1 chamada de LLM registrada nesse tenant, a próxima mensagem em `/api/v1/chat` deve devolver `response: ""`.
