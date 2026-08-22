# Contrato: `DELETE /api/v1/prompt-manager/guardrails/{id}` — bloqueio duplo

**Requisitos**: FR-023, FR-024, FR-025 · Publicado no EDI-44

## Comportamento

| Situação | HTTP | `code` |
| -- | -- | -- |
| Sucesso | `204` | — |
| Guardrail não existe | `404` | — |
| `is_global = TRUE` | `409` | `GUARDRAIL_IS_GLOBAL` |
| Associado a prompt com tenant ativo | `409` | `GUARDRAIL_IN_USE_BY_TENANTS` |

São **dois códigos distintos de propósito**: a ação que o administrador precisa tomar é diferente em cada caso, e um código único obrigaria a UI a adivinhar qual.

## Por que o critério precisa dos dois testes

Checar apenas "está associado a algum prompt" **não pega o guardrail global**. Um guardrail `is_global` não tem linha em `prompt_guardrails` — ele alcança os tenants pela cláusula `WHERE g.is_global = TRUE` de `get_guardrails_by_prompt` (`prompt_manager_repository.py:142`).

Ou seja: com um critério só de associação, justamente o guardrail que protege **todos** os tenants seria o mais fácil de apagar.

Segundo motivo: como o seed recria o guardrail global no boot seguinte (cria só se não existir, FR-013), excluí-lo produziria um "apaguei e voltou sozinho" — confuso, e pior que um bloqueio explícito.

## `GUARDRAIL_IS_GLOBAL`

```json
{
  "detail": {
    "code": "GUARDRAIL_IS_GLOBAL",
    "message": "Este guardrail é global e se aplica a todos os tenants. Desmarque 'global' antes de excluir.",
    "blockers": []
  }
}
```

Caminho de saída: `PUT /guardrails/{id}` com `is_global: false`, depois o `DELETE`. Dois passos, sempre explícito. A UI pode oferecer isso como um único botão.

## `GUARDRAIL_IN_USE_BY_TENANTS`

```json
{
  "detail": {
    "code": "GUARDRAIL_IN_USE_BY_TENANTS",
    "message": "Este guardrail está associado a 2 prompts em uso por tenants. Remova a associação antes de excluir.",
    "blockers": [
      { "type": "prompt", "id": "3f2a...", "name": "Atendimento Clínica", "tenant_count": 4 },
      { "type": "prompt", "id": "9b1c...", "name": "Atendimento Padrão",  "tenant_count": 1 }
    ]
  }
}
```

Critério: existe `prompt_guardrails` para esse guardrail cujo prompt tem vínculo ativo em `tenant_prompts`.

Um guardrail associado apenas a prompts **sem** tenant ativo não bloqueia — não há proteção em vigor a perder.

## Precedência

Quando as duas condições coexistem, retornar `GUARDRAIL_IS_GLOBAL` (FR-025). É o bloqueio mais forte e o primeiro que o administrador precisa resolver: enquanto o guardrail for global, desassociá-lo dos prompts não muda nada, porque o alcance global independe da associação.

## Verificação

- [ ] Guardrail `is_global` sem associação → `409 GUARDRAIL_IS_GLOBAL`
- [ ] Guardrail não-global associado a prompt com tenant ativo → `409 GUARDRAIL_IN_USE_BY_TENANTS`, com o prompt e seu `tenant_count` em `blockers`
- [ ] Guardrail `is_global` **e** associado a prompt em uso → `409 GUARDRAIL_IS_GLOBAL` (precedência)
- [ ] Guardrail não-global associado só a prompt **sem** tenant ativo → `204`
- [ ] Guardrail não-global e sem associação → `204`
- [ ] Desmarcar `is_global` e então excluir → `204` (o caminho de saída funciona)
- [ ] Após um `409`, o guardrail continua intacto e ainda aplicado no runtime
