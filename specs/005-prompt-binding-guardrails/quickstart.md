# Quickstart — validação local

**Feature**: 005-prompt-binding-guardrails · **Plan**: [plan.md](./plan.md)

Comandos para **você executar** (conforme a regra MANDATORY do CLAUDE.md, os testes são passados para execução, não executados por mim).

## Suíte completa

```powershell
.\test.sh
```

ou diretamente:

```powershell
pytest tests/ -v
```

## Só os testes desta feature

```powershell
pytest tests/unit/test_prompt_resolver.py tests/integration/test_prompt_delete_guard_api.py tests/integration/test_guardrail_delete_guard_api.py tests/integration/test_link_tenants_bulk_api.py tests/integration/test_tenant_create_requires_prompt_api.py -v
```

## Os quatro cenários de resolução (SC-011)

```powershell
pytest tests/unit/test_prompt_resolver.py -v
```

| Cenário | Resultado esperado |
| -- | -- |
| Sem vínculo + com guardrail global | `PromptConfigurationError`, **com** os guardrails globais resolvidos |
| Sem vínculo + sem guardrail global | `PromptConfigurationError`, sem guardrails, **sem** ler o `.md` |
| Com vínculo + global | prompt do vínculo + guardrails (próprios ∪ globais), sem duplicação |
| Banco indisponível | conteúdo do `.md` local, **sem** exceção — o atendimento continua |

O quarto é o que impede a correção de virar uma queda de produção. Os dois primeiros são o defeito original.

## Testes de regressão que devem continuar passando

Estes cobrem comportamento que a feature **não pode** quebrar:

```powershell
pytest tests/unit/test_load_prompt_institutional.py tests/unit/test_load_prompt_chitchat.py tests/integration/test_prompt_manager_seed.py tests/integration/test_tenant_prompt_overview_api.py -v
```

Alguns deles **precisam ser alterados** junto com a implementação, porque hoje afirmam o fallback local que a feature elimina. Alterá-los é esperado; o que não pode acontecer é a alteração afrouxar a asserção em vez de trocá-la pelo novo comportamento.

## Validação do seed em banco vazio (FR-011, FR-012, SC-006)

```powershell
docker compose -f docker-compose-local.yml down -v
docker compose -f docker-compose-local.yml up -d
```

Depois, verificar pela API:

```powershell
curl "http://localhost:8000/api/v1/prompt-manager/prompts?node_type=operational"
curl "http://localhost:8000/api/v1/prompt-manager/prompts?node_type=institutional"
curl "http://localhost:8000/api/v1/prompt-manager/prompts?node_type=chitchat"
curl "http://localhost:8000/api/v1/prompt-manager/guardrails"
```

Esperado: cada `node_type` com ao menos um prompt, e ao menos um guardrail com `is_global: true`.

⚠️ O `down -v` **apaga o volume do banco local**. Só rode contra o ambiente de desenvolvimento.

## Idempotência do seed (FR-013, SC-007)

```powershell
docker compose -f docker-compose-local.yml restart api
```

Contar os registros antes e depois: as contagens devem ser idênticas. Depois, editar o conteúdo de um prompt semeado pela API, reiniciar de novo e confirmar que a edição sobreviveu.

## Migration de backfill (FR-028, SC-010)

```powershell
alembic upgrade head
alembic current
```

Verificar que nenhum tenant ficou sem vínculo `operational` ativo. Rodar `alembic upgrade head` duas vezes não deve alterar nada (idempotente).

Caso de borda a testar de propósito: banco **sem** nenhum prompt `is_default` operational. A migration deve passar sem erro e sem criar vínculo — é instalação nova, e falhar aqui derrubaria a subida do container.

## Checagem manual do contrato de erro

```powershell
# 409 com blockers — prompt em uso
curl -i -X DELETE "http://localhost:8000/api/v1/prompt-manager/prompts/<id-em-uso>"

# 409 GUARDRAIL_IS_GLOBAL
curl -i -X DELETE "http://localhost:8000/api/v1/prompt-manager/guardrails/<id-global>"

# 422 — formato de lista do Pydantic, sem prompt_id
curl -i -X POST "http://localhost:8000/api/v1/tenants/" -H "Content-Type: application/json" -d '{\"tenant_id\":\"x\",\"name\":\"X\",\"google_calendar_id\":\"c\",\"allowed_domains\":[]}'
```

O último confirma a assimetria intencional: `detail` como **lista** no `422`, como **objeto** nos erros de regra de negócio.
