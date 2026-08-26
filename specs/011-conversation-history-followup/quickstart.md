# Quickstart — Histórico consultável, resumo e outcome por sessão

## Aplicar a migration

```bash
alembic upgrade head
```

## Variáveis de ambiente novas

Nenhuma variável nova é obrigatória — reaproveita `CHAT_SESSION_IDLE_MINUTES` (EDI-59) e a mesma instância `llm` já configurada em `modules/ia/agent_graph.py`.

## Rodar os testes

```bash
# Unit (sem banco/rede)
pytest tests/unit/test_conversation_message_domain.py tests/unit/test_oferta_vigente_domain.py \
  tests/unit/test_classify_session_outcome_use_case.py tests/unit/test_record_conversation_turn_use_case.py \
  tests/unit/test_purge_expired_messages_use_case.py -v

# Integration (exige Postgres real com a migration aplicada)
pytest tests/integration/test_conversation_history_api.py tests/integration/test_follow_up_queue_api.py \
  tests/integration/test_session_outcome_classification.py tests/integration/test_conversation_history_purge.py -v
```

## Rodar o job de expurgo localmente

```bash
python -m workers.conversation_history_purge
```

Processa todos os tenants com `retention_days` configurado; tenants sem esse campo não são tocados. Pensado para rodar via cron externo (infraestrutura, fora deste repositório) — não é um processo de longa duração.

## Configurar `oferta_vigente` e `retention_days` de um tenant manualmente

```bash
curl -X PUT http://localhost:8001/api/v1/tenants/SEU_TENANT_ID \
  -H "Content-Type: application/json" \
  -d '{"name": "...", "google_calendar_id": "...", "allowed_domains": [], "oferta_vigente_texto": "10% na primeira sessão", "oferta_vigente_validade": "2026-12-31", "retention_days": 180}'
```

## Conferir o histórico e a fila de follow-up de uma conversa de teste

```bash
curl "http://localhost:8001/api/v1/tenants/SEU_TENANT_ID/conversation-history/SEU_TENANT_ID:5511999998888"

curl "http://localhost:8001/api/v1/tenants/SEU_TENANT_ID/follow-up-queue?status=pendente"
```

Para ver um registro aparecer em `follow-up-queue`, envie uma mensagem em `/api/v1/chat` e espere `CHAT_SESSION_IDLE_MINUTES` (ou reduza a env var localmente, ex. `CHAT_SESSION_IDLE_MINUTES=0.5`) antes de enviar a próxima mensagem no mesmo `thread_id` — isso dispara a expiração/classificação em background.
