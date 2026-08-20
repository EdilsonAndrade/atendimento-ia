# Contract: Prompts com Nó de Destino (`node_type`)

## `GET /api/v1/prompt-manager/prompts` *(existing endpoint — modified)*

**Auth**: none (mantém o padrão hoje já não-autenticado dos demais endpoints de `prompt-manager`)

**Novo query param opcional**: `node_type` (`operational` | `institutional` | `chitchat`). Quando omitido,
retorna prompts de todos os nós (comportamento equivalente ao atual, apenas com o campo `node_type` a mais em
cada item).

**Response `200 OK`**:
```json
[
  {
    "id": "b3f1...",
    "titulo": "Atendimento Barbearia",
    "conteudo": "...",
    "is_default": false,
    "node_type": "operational",
    "guardrail_ids": ["g1", "g2"],
    "created_at": "...",
    "updated_at": "..."
  }
]
```

**Maps to**: FR-001, FR-002, FR-003.

---

## `POST /api/v1/prompt-manager/prompts` *(existing endpoint — modified)*
## `PUT /api/v1/prompt-manager/prompts/{prompt_id}` *(existing endpoint — modified)*

**Auth**: none (mesmo padrão atual)

**Request body** (`PromptCreateSchema`, campo novo em negrito):

```json
{
  "titulo": "Guardrails Chitchat - Barbearia X",
  "conteudo": "...texto com a tag {guardrails}...",
  "is_default": false,
  "node_type": "chitchat",
  "guardrail_ids": ["g1", "g3"]
}
```

- `node_type`: opcional, default `"operational"` (preserva o comportamento atual dos clientes existentes da
  API que não enviam esse campo).
- Validação: apenas os 3 valores conhecidos são aceitos; qualquer outro valor retorna `422` (validação
  Pydantic).

**Response**: igual ao `GET`, incluindo `node_type` no corpo retornado.

**Maps to**: FR-001, FR-002, FR-003, FR-008 (a tag `{guardrails}` é responsabilidade do conteúdo enviado
pelo administrador — o backend não valida a presença da tag, ver Edge Cases do spec).

---

## `POST /api/v1/prompt-manager/link-tenant` *(existing endpoint — modificado internamente, contrato de request/response inalterado)*

**Auth**: none

**Request body**: inalterado (`TenantPromptLinkSchema` — `tenant_id`, `prompt_id`,
`custom_content_override`). O `node_type` do vínculo é **derivado** do `prompt_id` informado (lookup interno),
não é enviado pelo cliente — evita duas fontes de verdade para o nó do vínculo.

**Comportamento alterado**: ao vincular o tenant a um novo prompt, o sistema desativa apenas os vínculos
ativos anteriores do **mesmo `node_type`** desse tenant. Vínculos ativos de outros nós não são afetados.

**Maps to**: FR-009; User Story 3, Acceptance Scenario 1.

---

## `GET /api/v1/prompt-manager/tenant/{tenant_id}` *(existing endpoint — modified)*

**Auth**: none

**Novo query param opcional**: `node_type` (`operational` | `institutional` | `chitchat`), default
`"operational"` — preserva o contrato atual para clientes que não enviam o parâmetro.

**Comportamento**: aplica a cadeia de resolução do nó pedido (ver `data-model.md` — Cadeia de Resolução em
Runtime). Quando o resultado vem de um fallback (ex.: `institutional` sem vínculo próprio, usando o
`operational` do tenant), o campo `is_default_prompt` reflete o prompt efetivamente resolvido, e um novo
campo `node_type` no corpo da resposta indica o nó pedido.

**Response `200 OK`** (exemplo — institutional sem vínculo próprio, caindo no operacional do tenant):
```json
{
  "tenant_id": "1234",
  "node_type": "institutional",
  "prompt_id": "b3f1...",
  "prompt_titulo": "Atendimento Barbearia",
  "prompt_conteudo": "...",
  "custom_content_override": null,
  "is_default_prompt": false,
  "is_active": true,
  "guardrails_associados": [
    {"id": "g1", "titulo": "Confirmação de agenda", "conteudo": "...", "is_global": false}
  ]
}
```

**Errors**: inalterados (`404` tenant inexistente; `500` sem prompt `is_default` configurado para o nó
resolvido).

**Maps to**: FR-004, FR-005; User Story 1 (Acceptance Scenario 2), User Story 2 (Acceptance Scenario 1 e 2).
