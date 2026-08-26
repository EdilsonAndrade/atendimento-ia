# Contratos: histórico consultável, resumo e outcome por sessão

**Requisitos**: FR-001 a FR-009 · EDI-53

## `GET /api/v1/tenants/{tenant_id}/conversation-history/{base_thread_id}` (endpoint novo)

Histórico consultável de uma conversa (US1, FR-008). `app/api/v1/endpoints/conversation_history.py`.

**Query params**: `limit: int = 200` (máx. 500), `before: datetime | None` (paginação por cursor, mensagens mais antigas que este timestamp).

**Response `200`** (`ConversationHistoryResponse`):

```json
{
  "tenant_id": "acme",
  "base_thread_id": "acme:5511999998888",
  "messages": [
    {"role": "human", "content": "Oi, quero agendar um horário", "created_at": "2026-08-26T14:00:01Z"},
    {"role": "ai", "content": "Claro! Qual serviço você procura?", "created_at": "2026-08-26T14:00:03Z"}
  ]
}
```

- Mensagens em ordem cronológica ascendente.
- `messages: []` quando o thread não tem nenhuma mensagem (não é erro — `200` com lista vazia).

**Erros**: `400` se `tenant_id` vazio (mesmo padrão de `/chat`).

## `GET /api/v1/tenants/{tenant_id}/follow-up-queue` (endpoint novo)

Fila de follow-up consultável (US4, FR-009). `app/api/v1/endpoints/follow_up_queue.py`.

**Query params**: `status: str | None` (`pendente`/`aprovado`/`enviado`/`descartado`/`opt_out`; omitido = todos os status).

**Response `200`** (`FollowUpQueueResponse`):

```json
{
  "tenant_id": "acme",
  "entries": [
    {
      "id": 42,
      "base_thread_id": "acme:5511999998888",
      "outcome": "sem_resposta",
      "summary": "Cliente pediu horário para corte, mas não respondeu à proposta de terça 14h.",
      "draft_message": "Oi Maria! Vi que você chegou a perguntar sobre horário para corte...",
      "status": "pendente",
      "created_at": "2026-08-26T20:15:00Z"
    }
  ]
}
```

- `draft_message: null` quando `outcome` for `fechado`/`recusado`/`em_andamento` (FR-003).
- `entries: []` quando não há nenhuma sessão fechada ainda para o tenant/status filtrado.

**Erros**: `400` se `tenant_id` vazio; `422` se `status` não for um dos 5 valores válidos.

## `tenants` — campos novos em `TenantCreate`/`TenantUpdate`/`TenantResponse`

`app/schemas/tenant.py` ganha:

```json
{
  "oferta_vigente_texto": "10% de desconto na primeira sessão",
  "oferta_vigente_validade": "2026-09-30",
  "retention_days": 180
}
```

- `oferta_vigente_texto: str | None`, `oferta_vigente_validade: date | None` — ambos default `None`. Uma oferta só é considerada vigente quando os dois estão preenchidos E `oferta_vigente_validade >= hoje` (ver data-model.md).
- `retention_days: int | None`, default `None` (sem expurgo automático).

`POST /api/v1/tenants/` e `PUT /api/v1/tenants/{tenant_id}` passam a aceitar/persistir os três campos; `GET /api/v1/tenants/{tenant_id}` e `GET /api/v1/tenants/list` passam a devolvê-los.

## Persistência de `conversation_messages` no request-path (sem endpoint novo)

`POST /api/v1/chat` e o processamento de mensagens do WhatsApp passam a gravar, após o `invoke()` do grafo ter sucesso, duas linhas em `conversation_messages` (`role='human'` com o texto recebido, `role='ai'` com `resposta_final`) — nunca bloqueia nem altera a resposta ao cliente em caso de falha (FR-001, FR-010).

## Classificação de outcome no fechamento de sessão (sem endpoint novo)

`generate_and_store_session_summary` (`modules/ia/thread_session.py`), disparada pela expiração de sessão, passa a também chamar `ClassifySessionOutcomeUseCase.execute(...)` (`modules/follow_up/`) com o mesmo texto de conversa já montado para o resumo — gravando exatamente um registro em `follow_up_queue` por sessão fechada (FR-002 a FR-005, FR-010, FR-011).

## Job de expurgo (sem endpoint — script)

`python -m workers.conversation_history_purge` — para cada tenant com `retention_days` não nulo, apaga de `conversation_messages` as linhas com `created_at < NOW() - retention_days`. Tenants com `retention_days` nulo não são tocados (FR-007).

## Verificação

- [ ] Enviar 2 mensagens numa conversa de teste → `GET /conversation-history/{base_thread_id}` devolve as 4 linhas (2 human + 2 ai) na ordem certa
- [ ] `base_thread_id` sem nenhuma mensagem → `200` com `messages: []`
- [ ] Sessão de teste expira com cliente sem responder à última pergunta → `follow_up_queue` ganha 1 registro `outcome='sem_resposta'`/`'pensando'` com `draft_message` preenchido
- [ ] Mesma sessão expirada reprocessada manualmente → `follow_up_queue` continua com exatamente 1 registro (idempotência via `UNIQUE(active_thread_id)`)
- [ ] Sessão com agendamento confirmado por `ToolMessage` real → `outcome='fechado'`, `draft_message` nulo
- [ ] Tenant sem `oferta_vigente` → `draft_message` gerado não menciona desconto/promoção em nenhum caso de teste
- [ ] Tenant com `oferta_vigente_validade` no passado → tratado como sem oferta (mesmo resultado do caso acima)
- [ ] `GET /follow-up-queue?status=pendente` só retorna registros `pendente` do tenant informado, nunca de outro tenant
- [ ] Job de expurgo com `retention_days=1` e mensagens de 2 dias atrás → mensagens antigas somem, mensagens de outro tenant com `retention_days` maior permanecem
