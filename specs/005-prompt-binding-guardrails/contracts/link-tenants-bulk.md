# Contrato: `POST /api/v1/prompt-manager/link-tenants` — associação em massa

**Requisitos**: FR-019, FR-020, FR-021 · Publicado no EDI-44

Endpoint **novo**. O `POST /link-tenant` (singular, `prompt_manager.py:53`) continua existindo e inalterado.

Nenhuma alteração de modelo: `tenant_prompts` já é N:N e suporta isto sem migração.

## Request

```json
{
  "prompt_id": "3f2a1b4c-...-uuid",
  "tenant_ids": ["acme", "beta", "gama"],
  "custom_content_override": null
}
```

`tenant_ids` exige `min_length=1`.

## Response `200`

```json
{
  "prompt_id": "3f2a1b4c-...-uuid",
  "node_type": "operational",
  "linked_count": 3,
  "tenant_ids": ["acme", "beta", "gama"]
}
```

`node_type` é devolvido para a UI confirmar qual nó foi afetado — ele vem do prompt, não do request.

## Semântica

Três propriedades que a UI deve comunicar ao administrador **antes** de confirmar:

1. **All-or-nothing.** Uma transação. Se qualquer tenant da lista não existir, nenhum vínculo é aplicado.
2. **Substitui o vínculo anterior** daquele `node_type` em cada tenant. Mesma regra do `sync_tenant_prompt` atual (`prompt_manager_repository.py:89`): desativa os ativos do mesmo `node_type` antes de ativar o novo.
3. **Não toca outros `node_type`** (FR-021). Aplicar um prompt `operational` em massa não afeta os vínculos `institutional` ou `chitchat` desses tenants.

O `custom_content_override`, quando informado, é aplicado a **todos** os tenants da lista. Para conteúdo distinto por tenant, o endpoint singular continua sendo o caminho.

## Erros

| Situação | HTTP | `code` |
| -- | -- | -- |
| `tenant_ids` vazio | `422` | validação Pydantic (`min_length=1`) |
| `prompt_id` não existe | `404` | `PROMPT_NOT_FOUND` |
| Um ou mais tenants não existem | `404` | `TENANT_NOT_FOUND` |

```json
{
  "detail": {
    "code": "TENANT_NOT_FOUND",
    "message": "2 tenants informados não existem. Nenhum vínculo foi aplicado.",
    "blockers": [
      { "type": "tenant", "id": "inexistente-1" },
      { "type": "tenant", "id": "inexistente-2" }
    ]
  }
}
```

`blockers` lista **apenas** os tenants não encontrados, para o administrador corrigir a lista sem adivinhar quais falharam. Aqui os itens não trazem `name` — o tenant não existe, então não há nome a informar.

## Verificação

- [ ] 3 tenants válidos → `200`, `linked_count: 3`, os 3 com vínculo ativo
- [ ] Lista com 1 tenant inexistente entre 3 → `404 TENANT_NOT_FOUND`, e **nenhum** dos 3 fica vinculado
- [ ] `tenant_ids` vazio → `422`
- [ ] `prompt_id` inexistente → `404 PROMPT_NOT_FOUND`
- [ ] Tenant que já tinha outro prompt `operational` ativo → o antigo fica inativo, o novo ativo
- [ ] Tenant com vínculo `chitchat` ativo → o vínculo `chitchat` permanece intacto após a operação
- [ ] Reaplicar a mesma operação → idempotente, sem duplicar linhas
- [ ] `custom_content_override` informado → aplicado a todos os tenants da lista
