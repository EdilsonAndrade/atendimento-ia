# Contrato: `POST /api/v1/tenants/` — prompt obrigatório

**Requisitos**: FR-016, FR-017, FR-018 · Publicado no EDI-44

`TenantCreate` (`app/schemas/tenant.py:13`) ganha o campo **`prompt_id`**, obrigatório. É o prompt de `node_type = "operational"`. Os nós `institutional` e `chitchat` **não** entram no cadastro — resolvem pelas cadeias próprias (FR-008).

## `scheduling_enabled` (novo campo, bug pontual — sem ticket)

`TenantCreate`/`TenantUpdate`/`TenantResponse` ganham **`scheduling_enabled: bool`**, default `true`. Controla se o agente oferece tools de agendamento (agendar/consultar/cancelar) para o tenant, **independente** de `google_calendar_id` estar preenchido.

Por que existe: `get_active_tools` (`modules/ia/agent_graph.py`) antes decidia isso só pela presença de `google_calendar_id` — sem calendário, o tenant ainda assim recebia as tools internas (`static_tools`). Um tenant puramente institucional (ex: um SaaS que só usa o chat pra se vender, sem agendamento nenhum) acabava com tools de agendamento disponíveis e a IA podia tentar usá-las. Isso é INDEPENDENTE do `prompt_id`/EDI-43: mesmo com o prompt certo vinculado, a capacidade de agendar era decidida por um efeito colateral, não por uma configuração explícita.

**O que o EDI-44 precisa expor na tela:**
- Um toggle/checkbox "Agendamento habilitado" no cadastro e na edição do tenant, default marcado.
- Tenants existentes (migration `0004_scheduling_enabled`) todos nascem com `scheduling_enabled = true` — quem não deve ter agendamento (ex: um tenant institucional puro) precisa ser desmarcado manualmente depois do deploy.
- Não há relação com `google_calendar_id`: um tenant pode ter `scheduling_enabled = false` mesmo com `google_calendar_id` preenchido (ex: calendário configurado mas o agendamento via chat está temporariamente desligado).

## Request

```json
{
  "tenant_id": "acme",
  "name": "Acme Ltda",
  "google_calendar_id": "acme@group.calendar.google.com",
  "allowed_domains": ["acme.com"],
  "prompt_id": "3f2a1b4c-...-uuid",
  "scheduling_enabled": true
}
```

Para popular a lista de escolha, o consumidor usa o endpoint já existente: `GET /api/v1/prompt-manager/prompts?node_type=operational`. O seed (FR-011) garante que essa lista **nunca volta vazia**, inclusive em instalação nova.

## Response `201`

`TenantResponse` agora inclui `scheduling_enabled`. O `prompt_id` continua não sendo ecoado porque não é campo do tenant: virou uma linha em `tenant_prompts`.

## Erros

| Situação | HTTP | `code` | Formato |
| -- | -- | -- | -- |
| `prompt_id` ausente ou vazio | `422` | — | lista nativa do Pydantic |
| `prompt_id` não existe | `404` | `PROMPT_NOT_FOUND` | envelope estruturado |
| `prompt_id` não é `operational` | `400` | `PROMPT_NODE_TYPE_INVALID` | envelope estruturado |

```json
{
  "detail": {
    "code": "PROMPT_NODE_TYPE_INVALID",
    "message": "O prompt informado é do tipo 'chitchat'. O cadastro de tenant exige um prompt do tipo 'operational'.",
    "blockers": []
  }
}
```

## Atomicidade

A criação do tenant e do vínculo é **uma única transação** (FR-018). Não existe estado intermediário de tenant criado sem prompt — que é exatamente o estado que esta feature elimina.

Ordem de execução (research.md R6):

1. Validar o prompt — existe? é `operational`? Nenhuma escrita ocorreu ainda, então os erros comuns nunca deixam resíduo.
2. `INSERT INTO tenants` + `INSERT INTO tenant_prompts` na mesma conexão.
3. Um `commit()`. Qualquer exceção no meio → `rollback()`.

## Verificação

- [ ] Criação sem `prompt_id` → `422`, e nenhum tenant é criado
- [ ] Criação com `prompt_id` inexistente → `404 PROMPT_NOT_FOUND`, e nenhum tenant é criado
- [ ] Criação com `prompt_id` de `node_type` errado → `400 PROMPT_NODE_TYPE_INVALID`, e nenhum tenant é criado
- [ ] Criação válida → tenant existe **e** tem vínculo `operational` ativo
- [ ] Falha simulada no `INSERT` do vínculo → nenhum tenant permanece no banco
- [ ] O tenant recém-criado resolve o prompt em runtime sem levantar `PromptConfigurationError`
