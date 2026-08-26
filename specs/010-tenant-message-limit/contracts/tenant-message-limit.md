# Contratos: limite mensal de mensagens por tenant

**Requisitos**: FR-001, FR-004, FR-005, FR-011 a FR-013b · EDI-63

## `TenantCreate` / `TenantUpdate` / `TenantResponse` — campos novos

`app/schemas/tenant.py` ganha, nos três schemas:

```json
{
  "monthly_message_limit": 3000,
  "notification_emails": ["gerente@buffet.com", "responsavel@buffet.com"]
}
```

- `monthly_message_limit`: `int | None`, default `None` (sem limite). Contagem por chamada de LLM, não por mensagem real do cliente final (ver `spec.md` > Clarifications).
- `notification_emails`: `list[str]`, default `[]`. Validação de formato de e-mail via `pydantic.EmailStr` em cada item.

`POST /api/v1/tenants/` e `PUT /api/v1/tenants/{tenant_id}` passam a aceitar/persistir os dois campos; `GET /api/v1/tenants/{tenant_id}` e `GET /api/v1/tenants/list` passam a devolvê-los.

## `GET /api/v1/tenants/{tenant_id}/usage` (endpoint novo)

Consumo do mês corrente — base do indicador visual da UI admin (FR-012).

**Response `200`** (`TenantUsageResponse`):

```json
{
  "tenant_id": "acme",
  "monthly_message_limit": 3000,
  "current_month_calls": 930,
  "percentage_used": 31.0,
  "blocked": false
}
```

- `monthly_message_limit: int | None` — `null` quando o tenant não tem limite (percentage_used também vem `null` nesse caso).
- `current_month_calls: int` — chamadas de LLM contadas no mês corrente (`chat_token_usage`).
- `percentage_used: float | None` — `round(current_month_calls / monthly_message_limit * 100, 1)`, `null` se sem limite.
- `blocked: bool` — `current_month_calls >= monthly_message_limit` (sempre `false` se sem limite).

**Erros**: `404` se `tenant_id` não existe (mesmo formato de `GET /tenants/{id}`).

## `GET /api/v1/tenants/message-limit-config` (endpoint novo)

Base da calculadora de dimensionamento de plano (FR-013b) — a UI faz a divisão (`chamadas ÷ razão`), este endpoint só expõe as razões vigentes, para não hardcodar o número em dois lugares.

**Response `200`**:

```json
{
  "worst_case_calls_per_message": 3,
  "average_calls_per_message": 3
}
```

Valores vêm de `TENANT_LIMIT_WORST_CASE_CALLS_PER_MESSAGE` / `TENANT_LIMIT_AVERAGE_CALLS_PER_MESSAGE` (env vars, default `3`/`3` — ver research.md §7). Sem autenticação adicional (mesmo padrão dos demais endpoints de `/tenants`).

## `global_notification_recipients` — CRUD (`app/api/v1/endpoints/global_notification_recipients.py`, endpoint novo)

Prefixo: `/api/v1/global-notification-recipients`.

| Método | Path | Body | Response |
| -- | -- | -- | -- |
| `GET` | `/` | — | `200`: `[{"id": 1, "email": "contato@interasisai.com.br", "active": true}]` |
| `POST` | `/` | `{"email": "novo@interasisai.com.br"}` | `201`: item criado (`active` default `true`) |
| `PUT` | `/{id}` | `{"active": false}` | `200`: item atualizado |
| `DELETE` | `/{id}` | — | `200`: `{"id": 1, "message": "Recipient deleted successfully"}` |

**Erros**: `POST` com e-mail duplicado → `409 {"detail": {"code": "EMAIL_ALREADY_EXISTS", ...}}`. `PUT`/`DELETE` com `id` inexistente → `404`.

## Enforcement no request-path (sem endpoint novo — comportamento de `/chat` e do webhook)

`POST /api/v1/chat` e o processamento de mensagens do WhatsApp (`modules/webhook/whatsapp.py`) passam a checar `CheckTenantLimitUseCase` ANTES de invocar o grafo:

- **Bloqueado**: `POST /api/v1/chat` responde `200` normalmente, com `ChatResponse.response = ""` (string vazia) — nenhuma chamada de LLM ocorre, nenhuma mensagem de erro é gerada. O webhook do WhatsApp simplesmente não envia nada ao cliente final (mesmo mecanismo que já existe hoje para `resposta_final` vazio).
- **Não bloqueado**: fluxo idêntico ao atual; depois do `invoke()` bem-sucedido, `NotifyUsageMilestonesUseCase` roda (idempotente, nunca lança exceção).

## Verificação

- [ ] Tenant sem `monthly_message_limit` → `GET /usage` devolve `percentage_used: null`, `blocked: false`; `/chat` nunca bloqueia
- [ ] Tenant no limite (`current_month_calls == monthly_message_limit`) → próxima chamada a `/chat` devolve `response: ""`, sem nenhuma linha nova em `chat_token_usage` para essa tentativa (zero chamadas de LLM)
- [ ] Cruzar 50%/80%/100% em chamadas separadas → 1 e-mail por marco, nunca duplicado num mesmo mês (`tenant_usage_notifications` claim)
- [ ] Cruzar de <50% para >80% numa única chamada → e-mails de 50% E 80% disparam nessa mesma chamada
- [ ] `POST /global-notification-recipients` com e-mail já cadastrado → `409 EMAIL_ALREADY_EXISTS`
- [ ] Tenant A bloqueado não afeta contagem/bloqueio do Tenant B (isolamento multi-tenant)
