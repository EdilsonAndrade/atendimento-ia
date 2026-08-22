# Contrato: envelope de erro estruturado

**Requisitos**: FR-026, FR-027 · Publicado no EDI-44

Erros de **regra de negócio** deixam de usar `detail` como string solta e passam a usar um objeto estruturado:

```json
{
  "detail": {
    "code": "PROMPT_IN_USE_BY_TENANTS",
    "message": "Mensagem pronta para exibição ao administrador.",
    "blockers": []
  }
}
```

## Campos

| Campo | Tipo | Obrigatório | Descrição |
| -- | -- | -- | -- |
| `code` | string | sim | Identificador estável, legível por máquina. **É o contrato.** |
| `message` | string | sim | Texto exibível ao administrador. Pode mudar sem aviso — não é contrato. |
| `blockers` | array | sim (pode ser `[]`) | Itens que impedem a operação, para a UI listar o caminho de saída |

**Regra para o consumidor**: decidir sempre pelo `code`, nunca pelo `message`.

### Formato de `blockers`

Bloqueador do tipo tenant:

```json
{ "type": "tenant", "id": "acme", "name": "Acme Ltda" }
```

Bloqueador do tipo prompt:

```json
{ "type": "prompt", "id": "3f2a...", "name": "Atendimento Clínica", "tenant_count": 4 }
```

## Exceção deliberada: o `422` do Pydantic

Erros de **validação de schema** mantêm o formato nativo do FastAPI, em que `detail` é uma **lista**:

```json
{
  "detail": [
    { "type": "missing", "loc": ["body", "prompt_id"], "msg": "Field required" }
  ]
}
```

Isto é intencional, não uma inconsistência esquecida. Uniformizar o `422` exigiria um exception handler global, que mudaria o formato de erro de **todos** os endpoints do projeto — quebrando consumidores existentes por simetria estética. Ver research.md R8.

**Consequência para o consumidor**: o tratador genérico precisa aguentar `detail` como objeto (regra de negócio) e como lista (validação).

## Códigos

| `code` | HTTP | Origem |
| -- | -- | -- |
| `PROMPT_NOT_FOUND` | 404 | criação de tenant, link em massa |
| `PROMPT_NODE_TYPE_INVALID` | 400 | criação de tenant |
| `PROMPT_IN_USE_BY_TENANTS` | 409 | exclusão de prompt |
| `GUARDRAIL_IS_GLOBAL` | 409 | exclusão de guardrail |
| `GUARDRAIL_IN_USE_BY_TENANTS` | 409 | exclusão de guardrail |
| `TENANT_NOT_FOUND` | 404 | link em massa |

## Implementação

`HTTPException(status_code=..., detail={...})` — o FastAPI serializa `dict` em `detail` sem handler customizado. Os `code` devem ser tipados como `Literal` num schema Pydantic para aparecerem no OpenAPI.

## Verificação

- [ ] Todo erro de regra de negócio retorna `detail` como objeto com as três chaves
- [ ] Nenhum `code` muda de valor entre versões sem nota de quebra de contrato
- [ ] `blockers` vem `[]`, nunca ausente ou `null`, quando não há bloqueadores
- [ ] O `422` de campo obrigatório ausente mantém o formato de lista do Pydantic
