# Phase 0 Research: Guardrails Independentes por Nó

## R1 — Como representar o "nó de destino" de um prompt

**Decision**: Adicionar coluna `node_type` à tabela `prompts` (`TEXT NOT NULL DEFAULT 'operational'`, com
`CHECK (node_type IN ('operational', 'institutional', 'chitchat'))`). Cada linha em `prompts` passa a
pertencer a exatamente um nó. A associação guardrail↔nó continua sendo feita através da tabela `prompt_guardrails`
já existente (N:N guardrail↔prompt) — como cada prompt agora tem um nó fixo, vincular um guardrail a um prompt
de um nó específico já resolve o "destino" pedido no ticket, sem precisar de uma coluna nova em
`prompt_guardrails` nem em `guardrails`.

**Rationale**: Reaproveita 100% do modelo N:N já existente e testado (`sync_prompt_guardrails`,
`get_guardrails_by_prompt`). Nenhuma tabela nova é necessária. `is_global = TRUE` continua funcionando sem
alteração — guardrails globais já são resolvidos independente de `prompt_id`, então continuam válidos para
qualquer nó automaticamente (cobre FR-010).

**Alternatives considered**:
- Coluna `destinos` (array) diretamente em `prompt_guardrails`, permitindo 1 prompt servir múltiplos nós
  simultaneamente com guardrails diferentes por nó. Rejeitada: nenhum prompt hoje precisa ser compartilhado
  *literalmente* entre nós com filtragem de guardrail por nó — o próprio ticket e a conversa de esclarecimento
  confirmaram que cada nó passa a ter seu **próprio prompt**, não um prompt compartilhado com guardrails
  filtrados. Mais simples e menos propenso a bugs de filtragem incorreta.
- Nova tabela `node_bindings` desacoplada de `prompts`. Rejeitada: adiciona uma indireção sem benefício, já
  que `prompts.node_type` sozinho já é suficiente para toda a lógica de fallback e de associação.

## R2 — Como isolar o vínculo ativo (`tenant_prompts`) por nó

**Decision**: Manter a tabela `tenant_prompts` com a mesma estrutura (`tenant_id`, `prompt_id`, `is_active`,
`custom_content_override`), mas fazer `sync_tenant_prompt` derivar o `node_type` do `prompt_id` recebido (via
`JOIN prompts`) e escopar a desativação de vínculos antigos **apenas aos prompts do mesmo `node_type`**:

```sql
UPDATE tenant_prompts tp
SET is_active = FALSE, updated_at = NOW()
FROM prompts p
WHERE tp.prompt_id = p.id
  AND tp.tenant_id = %(tenant_id)s
  AND tp.prompt_id != %(prompt_id)s
  AND p.node_type = (SELECT node_type FROM prompts WHERE id = %(prompt_id)s)
```

**Rationale**: Resolve diretamente o bug que a User Story 3 e o FR-009 apontam: hoje `sync_tenant_prompt`
desativa **todos** os vínculos do tenant, então vincular um prompt de chitchat desativaria o vínculo
operacional ativo. Escopar por `node_type` corrige isso sem exigir uma coluna redundante em `tenant_prompts`
(evita duas fontes de verdade para o nó de um vínculo).

**Alternatives considered**: Duplicar `node_type` em `tenant_prompts` também. Rejeitada por agora: exigiria
manter duas colunas sincronizadas sem ganho de correção adicional (o `JOIN` já garante consistência,
`prompt_id` é sempre a fonte de verdade). Pode ser revisitado se o volume de tenants tornar o `JOIN`
custoso — não é o caso aqui (escala pequena/média, conforme Constitution).

## R3 — Cadeia de fallback por nó

**Decision**:
- `operational_node`: **inalterado** — vínculo ativo do tenant → prompt `is_default=TRUE, node_type=operational` → arquivo local `operactional_prompt.md`.
- `institutional_node`: vínculo ativo do tenant (`node_type=institutional`) → **resultado já resolvido do
  `operational_node` para esse tenant** (reaproveita a função existente, não uma tabela `is_default`
  separada para institutional) → (implicitamente já cai no arquivo local via a cadeia operacional).
- `chitchat_node`: vínculo ativo do tenant (`node_type=chitchat`) → prompt `is_default=TRUE, node_type=chitchat`
  (novo, seed único) → texto fixo hoje embutido em `agent_graph.py`/`guardrails.md` (fallback de última
  instância, preserva o comportamento atual mesmo se o seed falhar).

**Rationale**: Reflete exatamente o que foi validado na conversa de esclarecimento com o solicitante:
institutional cai para o *prompt operacional daquele tenant* (não existe um "padrão institucional" genérico
hoje, então não faz sentido inventar um); chitchat, que hoje é 100% global/hardcoded, ganha um único prompt
padrão editável (`is_default`) como próximo nível antes do fallback local, espelhando o padrão já usado pelo
operacional.

**Alternatives considered**: Dar a institutional_node seu próprio prompt `is_default` (padrão institucional
genérico, independente do operacional). Rejeitada: o solicitante confirmou explicitamente que o fallback do
institutional deve ser o operacional do tenant, não um padrão genérico à parte.

## R4 — Como aplicar a mudança de schema (sem framework de migração)

**Decision**: Seguir a convenção já estabelecida no repositório (`chat_thread_sessions` em
`modules/ia/thread_session.py`, `tenant_knowledge_base` na feature 001): DDL idempotente executado no
`__init__`/setup do repositório, usando `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` e
`CREATE UNIQUE INDEX IF NOT EXISTS`. Nenhuma ferramenta de migração (Alembic etc.) é introduzida.

**Rationale**: Este repositório não tem Alembic nem arquivos `.sql` de migração — introduzir um framework de
migração está fora do escopo deste ticket e seria uma mudança estrutural não solicitada.

**Alternatives considered**: Script de migração manual único (`scripts/migrate_xxx.py`) rodado uma vez.
Rejeitada como *único* mecanismo: não seria reexecutável nem auto-aplicado em outros ambientes (dev, homolog);
o padrão idempotente já usado no repo cobre tanto o `ALTER TABLE` quanto o *seed* de dados de forma
consistente com o que já existe.

## R5 — Seed de dados para tenants já configurados

**Decision**: Ao subir a aplicação (mesmo ponto que hoje roda o `CREATE TABLE IF NOT EXISTS`), rodar uma
rotina idempotente de seed:
1. Garante 1 prompt `is_default=TRUE, node_type='chitchat'` (cria apenas se não existir nenhum com esse
   `node_type`), com o texto atualmente fixo em `chitchat_node` como conteúdo inicial.
2. Para cada tenant com vínculo ativo em `tenant_prompts` cujo prompt seja `node_type='operational'` e que
   **ainda não tenha** nenhum vínculo ativo `node_type='institutional'`: cria uma cópia do prompt operacional
   ativo (novo registro em `prompts` com `node_type='institutional'`), copia as associações de
   `prompt_guardrails` desse prompt, e cria o vínculo ativo em `tenant_prompts` para esse tenant no nó
   institutional.

**Rationale**: Atende a FR-006/FR-007 e à SC-003 (nenhuma regressão para tenants já configurados) sem exigir
ação manual do administrador, e é seguro rodar em todo boot porque cada passo verifica existência antes de
inserir (idempotente — mesma filosofia do `CREATE TABLE IF NOT EXISTS` já usado no repo).

**Alternatives considered**: Seed sob demanda (lazy, só na primeira leitura do institutional_node para aquele
tenant). Rejeitada: tornaria o primeiro request de cada tenant mais lento e mais complexo de testar; o seed
no boot é mais simples e o volume de tenants é pequeno/médio (Constitution: "Scale/Scope").
