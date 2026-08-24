# Data Model: Rastreamento de custo de token por conversa e tenant

## chat_token_usage (nova tabela)

Segue a mesma família de nomenclatura de `chat_thread_sessions`/`chat_thread_summaries` (EDI-59) — não há tabela "conversas" separada: o `base_thread_id` já é o identificador estável de conversa usado por essas tabelas, então a relação 1:N é modelada como "muitos `chat_token_usage` referenciam o mesmo `base_thread_id`", sem precisar de uma tabela pai vazia.

| Coluna | Tipo | Notas |
| --- | --- | --- |
| `id` | `serial primary key` | |
| `tenant_id` | `varchar(50)` | tenant que originou a chamada |
| `base_thread_id` | `varchar(255)` | identificador estável da conversa (não muda ao expirar sessão) |
| `thread_id` | `varchar(255)` | identificador de sessão ativo no momento da chamada (`active_thread_id`), para correlação fina se necessário |
| `node_type` | `varchar(50)` | `routing_agent`, `institutional_node`, `chitchat_node`, `operational_node`, ... — valor de dado, não exige nova coluna/tabela para novos nós (FR-007) |
| `input_tokens` | `integer` | de `usage_metadata.input_tokens` |
| `output_tokens` | `integer` | de `usage_metadata.output_tokens` |
| `total_tokens` | `integer` | de `usage_metadata.total_tokens` (ou soma, se ausente) |
| `estimated_cost_usd` | `numeric(12,6)` | calculado a partir dos tokens e do preço configurável (ver `research.md`) |
| `created_at` | `timestamptz not null default now()` | usado por rotina de purga futura (fora de escopo) |

Índices:
- `CREATE INDEX ON chat_token_usage (base_thread_id)` — somar custo de uma conversa.
- `CREATE INDEX ON chat_token_usage (tenant_id, created_at)` — somar custo por tenant/período.

## Domain

- **`TokenUsageRecord`** (dataclass, `modules/token_usage/domain/token_usage_record.py`): `tenant_id`, `base_thread_id`, `thread_id`, `node_type`, `input_tokens`, `output_tokens`, `total_tokens`, `estimated_cost_usd`. Sem dependência de framework (nem LangChain, nem psycopg).
- **`calculate_cost_usd(input_tokens, output_tokens, price_per_1k_input, price_per_1k_output) -> Decimal`** (função pura, mesmo arquivo ou `modules/token_usage/domain/pricing.py`): regra de negócio do cálculo de custo, testável isoladamente sem banco/LLM.
