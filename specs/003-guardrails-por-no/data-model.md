# Data Model: Guardrails Independentes por Nó

## Entidades

### Prompt (`prompts`) — ALTERADA

| Campo | Tipo | Observação |
|---|---|---|
| id | uuid | inalterado |
| titulo | text | inalterado |
| conteudo | text | inalterado — pode conter a tag `{guardrails}` |
| is_default | boolean | inalterado no significado, mas passa a ser único **por `node_type`**, não globalmente |
| **node_type** | text | **NOVO**. `'operational' \| 'institutional' \| 'chitchat'`. `NOT NULL DEFAULT 'operational'`. `CHECK` restringindo aos 3 valores. |
| created_at / updated_at | timestamp | inalterado |

**Migração idempotente** (executada no setup do repositório, ver research.md R4):
```sql
ALTER TABLE prompts ADD COLUMN IF NOT EXISTS node_type TEXT NOT NULL DEFAULT 'operational';
ALTER TABLE prompts ADD CONSTRAINT IF NOT EXISTS prompts_node_type_check
  CHECK (node_type IN ('operational', 'institutional', 'chitchat'));
CREATE UNIQUE INDEX IF NOT EXISTS prompts_one_default_per_node
  ON prompts (node_type) WHERE is_default = TRUE;
```

### Guardrail (`guardrails`) — INALTERADA

Sem mudança de schema. `is_global = TRUE` continua sendo aplicado a todos os nós automaticamente
(FR-010), pois `get_guardrails_by_prompt` já faz `WHERE g.is_global = TRUE OR pg.prompt_id = %s`.

### Vínculo Prompt-Guardrail (`prompt_guardrails`) — INALTERADA

N:N entre `guardrails` e `prompts`. Como cada `prompt` agora pertence a um `node_type`, o vínculo já
representa implicitamente "este guardrail se aplica a este nó" — não precisa de coluna própria.

### Vínculo Tenant-Prompt (`tenant_prompts`) — INALTERADA NO SCHEMA, ALTERADA NO COMPORTAMENTO

Sem novas colunas. O que muda é a lógica de `sync_tenant_prompt` (ver research.md R2): a desativação de
vínculos antigos do tenant passa a ser escopada pelo `node_type` do prompt sendo vinculado, via `JOIN` em
`prompts`. Isso garante, por tenant, **um vínculo ativo independente por nó** (até 3 vínculos ativos
simultâneos por tenant — um por `node_type` — em vez de no máximo 1 como hoje).

## Regras de Validação

- `node_type` só aceita os 3 valores conhecidos (`CHECK` no banco + `Literal` no schema Pydantic da API).
- No máximo um prompt com `is_default = TRUE` por `node_type` (índice único parcial).
- `sync_tenant_prompt(tenant_id, prompt_id, ...)` nunca desativa um vínculo ativo de `node_type` diferente do
  prompt informado (FR-009).

## Cadeia de Resolução em Runtime (leitura, não é uma entidade nova)

```
operational_node(tenant)
  1. tenant_prompts ativo com prompts.node_type = 'operational'
  2. prompts.is_default = TRUE AND node_type = 'operational'
  3. arquivo local operactional_prompt.md

institutional_node(tenant)
  1. tenant_prompts ativo com prompts.node_type = 'institutional'
  2. resultado de operational_node(tenant) acima (cadeia completa, reaproveitada)

chitchat_node(tenant)
  1. tenant_prompts ativo com prompts.node_type = 'chitchat'
  2. prompts.is_default = TRUE AND node_type = 'chitchat'
  3. texto fixo hoje embutido em agent_graph.py / guardrails.md
```

Guardrails aplicados em qualquer um dos 3 níveis acima = guardrails vinculados ao prompt resolvido
(`prompt_guardrails`) + todos os guardrails `is_global = TRUE`.
