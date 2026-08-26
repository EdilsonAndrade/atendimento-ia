# Data Model — Limite de mensagens por tenant (mensal)

## Schema (migration `0008_tenant_message_limit`)

### `tenants` (colunas novas)

| Coluna | Tipo | Nullable | Default | Notas |
| -- | -- | -- | -- | -- |
| `monthly_message_limit` | INTEGER | sim | NULL | `NULL` = sem limite (comportamento atual preservado, SC-002) |
| `notification_emails` | TEXT[] | sim | NULL / `{}` | e-mails do tenant para os avisos de 50/80/100/reset |

### `global_notification_recipients` (tabela nova)

| Coluna | Tipo | Nullable | Default | Notas |
| -- | -- | -- | -- | -- |
| `id` | SERIAL | não | — | PK |
| `email` | VARCHAR(255) | não | — | UNIQUE |
| `active` | BOOLEAN | não | TRUE | soft-disable sem apagar histórico |
| `created_at` | TIMESTAMPTZ | não | NOW() | |

Fallback `contato@interasisai.com.br` é aplicado em código (Application layer) quando não há nenhum e-mail `active = TRUE`, não persistido como linha "especial".

### `tenant_usage_notifications` (tabela nova — claim idempotente de marco)

| Coluna | Tipo | Nullable | Default | Notas |
| -- | -- | -- | -- | -- |
| `id` | SERIAL | não | — | PK |
| `tenant_id` | VARCHAR(50) | não | — | |
| `year_month` | CHAR(7) | não | — | `'YYYY-MM'`, mês corrente no momento do claim |
| `milestone` | SMALLINT | não | — | `50`, `80` ou `100` |
| `sent_at` | TIMESTAMPTZ | não | NOW() | |

`UNIQUE (tenant_id, year_month, milestone)` — é a constraint que torna o `INSERT ... ON CONFLICT DO NOTHING` um claim atômico (ver research.md §3). Índice implícito da UNIQUE já cobre a consulta de claim; nenhum índice adicional necessário para o volume esperado (no máximo 3 linhas por tenant por mês).

## Entidades (Domain)

- **`TenantLimitConfig`** (não persistida como classe própria — lida via `TenantLimitConfigPort`): `monthly_message_limit: int | None`, `notification_emails: list[str]`.
- **Contagem mensal**: não é uma entidade nova — é uma projeção de `chat_token_usage` (EDI-60), `COUNT(*) WHERE tenant_id = :id AND created_at >= :início_do_mês`.
- **`GlobalRecipient`**: `id`, `email`, `active`.
- **Claim de notificação**: representado pela própria linha de `tenant_usage_notifications`; não precisa de dataclass própria além do que os repositórios devolvem.

## Fila de retry (Redis, não é schema SQL)

- Stream principal: `token_usage_retry` — consumer group `token_usage_retry_workers`. Cada entrada serializa um `TokenUsageRecord` (campos string: `tenant_id`, `base_thread_id`, `thread_id`, `node_type`, `input_tokens`, `output_tokens`, `total_tokens`, `estimated_cost_usd`).
- Stream de dead-letter: `token_usage_retry:dead_letter` — mesma serialização, mais `original_id` (ID da entrada original no stream principal) e `failed_attempts`.

## Relações

```
tenants (1) ──< tenant_usage_notifications (N)   [tenant_id]
tenants (1) ──< chat_token_usage (N)             [tenant_id — já existente, EDI-60]
global_notification_recipients                   [independente, sem FK — global por design]
```

Nenhuma FK física é criada para `tenant_id` em `tenant_usage_notifications` (mesmo padrão de `chat_token_usage`, que também não tem FK para `tenants.id` — ver EDI-60) — mantém consistência com a convenção já estabelecida no projeto para tabelas de fato/evento de alto volume.
