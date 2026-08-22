# Data Model: Exclusão segura de tenant com cascata de prompts e guardrails

## Alteração de schema

Uma migration (nova, ver `research.md` §2):

| Tabela | Campo | De | Para |
|---|---|---|---|
| `tenant_prompts` | `tenant_id` | `varchar(100)`, sem FK | `varchar(50)`, `FOREIGN KEY REFERENCES tenants(id) ON DELETE CASCADE` |

Nenhuma outra tabela muda de estrutura. `prompts`, `guardrails`, `prompt_guardrails` permanecem como estão (já com as FKs `ON DELETE CASCADE` necessárias entre si, herdadas do EDI-43/EDI-37).

## Entidades (conceituais, sem mudança de forma — já existentes)

- **Tenant** (`tenants`): `id`, `name`, `google_calendar_id`, `allowed_domains`, `active`.
- **Prompt** (`prompts`): `id`, `titulo`, `conteudo`, `is_default`, `node_type` (`operational`/`institutional`/`chitchat`).
- **Guardrail** (`guardrails`): `id`, `titulo`, `conteudo`, `is_global`.
- **Vínculo Tenant↔Prompt** (`tenant_prompts`): `tenant_id`, `prompt_id`, `is_active`, `custom_content_override`. Único por `(tenant_id, prompt_id)`.
- **Vínculo Prompt↔Guardrail** (`prompt_guardrails`): `prompt_id`, `guardrail_id`. PK composta.

## Fluxo de decisão (exclusão de tenant)

```
excluir_tenant(tenant_id):
  abrir 1 conexão, iniciar 1 transação (ver research.md §3/§4)

  prompts_ativos = get_prompts_linked_to_tenant_active(tenant_id)   # novo método

  para cada prompt em prompts_ativos:
      outros_tenants = get_tenants_blocking_prompt(prompt.id) - {tenant_id}
      prompt_exclusivo = (outros_tenants vazio)

      se prompt_exclusivo:
          guardrails = get_guardrail_links_for_prompt(prompt.id)     # novo método
          para cada guardrail em guardrails:
              se guardrail.is_global:
                  preservar (nada a fazer; o vínculo prompt_guardrails
                  some sozinho quando o prompt for apagado)
              senão:
                  outros_prompts = get_prompts_blocking_guardrail(guardrail.id) - {prompt.id}
                  se outros_prompts vazio:
                      delete_guardrail(guardrail.id)   # reaproveita método existente
                  # senão: preservar, vínculo some junto com o prompt

          delete_prompt(prompt.id)   # reaproveita método existente; cascade cuida
                                       # de tenant_prompts e prompt_guardrails restantes

      # se NÃO exclusivo: nada a fazer aqui — a linha de tenant_prompts deste
      # tenant desaparece sozinha quando o tenant for apagado (FK nova, §2)

  delete_tenant(tenant_id)   # cascata remove as linhas remanescentes de tenant_prompts

  commit da transação (ou rollback automático se qualquer passo lançar exceção)
```

## Estrutura de resposta: pré-visualização de impacto

Endpoint `GET /tenants/{tenant_id}/delete-impact` (ver `contracts/tenant-delete-impact.md`):

```json
{
  "tenant_id": "abc123",
  "prompts_to_delete": [
    { "id": "uuid-1", "titulo": "Atendimento Barbearia X", "node_type": "operational" }
  ],
  "prompts_to_unlink_only": [
    { "id": "uuid-2", "titulo": "Institucional Padrão", "node_type": "institutional" }
  ],
  "guardrails_to_delete": [
    { "id": "uuid-3", "titulo": "Guardrail específico do cliente X" }
  ],
  "guardrails_to_unlink_only": [
    { "id": "uuid-4", "titulo": "Guardrail de segurança padrão", "is_global": true }
  ]
}
```

Esta estrutura é calculada pela MESMA lógica de decisão acima, em modo somente-leitura (sem nenhuma escrita) — nenhuma consulta nova além das listadas em `research.md` §6.
