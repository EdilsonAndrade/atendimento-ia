# Contrato: `DELETE /api/v1/prompt-manager/prompts/{id}` — bloqueio por uso

**Requisitos**: FR-022 · Publicado no EDI-44

## Comportamento atual (defeito)

`delete_prompt` (`prompt_manager_repository.py:196-203`) executa:

```sql
DELETE FROM prompt_guardrails WHERE prompt_id = %s;
DELETE FROM tenant_prompts   WHERE prompt_id = %s;   -- ⚠️ orfana todos os tenants
DELETE FROM prompts          WHERE id = %s;
```

Excluir um prompt usado por 10 tenants deixa os 10 sem vínculo, silenciosamente, sem passar por validação alguma. É o que reabre o buraco que o cadastro obrigatório e o backfill fecham (INV-2).

## Comportamento novo

| Situação | HTTP | Corpo |
| -- | -- | -- |
| Sucesso | `204` | vazio (inalterado) |
| Prompt não existe | `404` | inalterado |
| Prompt tem vínculo **ativo** com tenant | `409` | envelope estruturado |

```json
{
  "detail": {
    "code": "PROMPT_IN_USE_BY_TENANTS",
    "message": "Este prompt está em uso por 3 tenants e não pode ser excluído. Vincule outro prompt a esses tenants antes de excluir.",
    "blockers": [
      { "type": "tenant", "id": "acme", "name": "Acme Ltda" },
      { "type": "tenant", "id": "beta", "name": "Beta S.A." },
      { "type": "tenant", "id": "gama", "name": "Gama ME" }
    ]
  }
}
```

## Critério de bloqueio

Existe linha em `tenant_prompts` com esse `prompt_id` e `is_active = TRUE`.

Vínculos **inativos** não bloqueiam — são histórico, não configuração vigente, e a exclusão pode removê-los em cascata como hoje.

## Verificação

- [ ] Prompt com 1 vínculo ativo → `409`, com esse tenant em `blockers`
- [ ] Prompt com N vínculos ativos → `409`, com os N tenants em `blockers`
- [ ] Prompt só com vínculos **inativos** → `204`, exclusão ocorre
- [ ] Prompt sem nenhum vínculo → `204`, exclusão ocorre
- [ ] Após um `409`, o prompt e os vínculos continuam intactos no banco
- [ ] `blockers` traz `id` e `name` de cada tenant, não só o `id`
